"""attest: signed, diff-bound attestations for the shipping path.

Two verification functions - `design_reviewed()` and `eval_passed()` - each do
real work, bind their result to the exact diff they inspected, and return an
opaque token. `jj_ship.open_pr()` / `jj_ship.mark_ready()` refuse to create a
non-draft PR without both tokens, and recompute the diff hash from the tree jj
is about to push before accepting them.

What the signature buys, precisely (see SKILL.md for the long version):

* BINDING - the payload carries `diff_sha`, computed here from the real diff and
  never accepted from the caller, so a token stops verifying the moment the code
  changes. That is the property that makes "I reviewed the design" mean "I
  reviewed *this* code".
* AUDITABILITY - every issued token is appended to `attest.log.jsonl`, so a
  claim that was made and then quietly abandoned is still on the record.

It is NOT secrecy. The agent runs as the same user as the key file and can read
it, so this is tamper-EVIDENT, not tamper-PROOF. The real defence is that
`design_reviewed()` fetches the design document and matches the quote and the
requirement paths against the diff - work that cannot be skipped without being
detected, regardless of who can sign what.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import json
import os
import re
import secrets
import shutil
import time
from pathlib import Path
from typing import Any, Iterable, Optional

import httpx


class AttestError(RuntimeError):
    """A verification failed, or an attestation does not hold."""


# ---------------------------------------------------------------------------
# on-disk state: ATTEST_HOME redirects all three files, so a test never writes
# into the real ones
# ---------------------------------------------------------------------------

def _home() -> Path:
    return Path(os.environ.get("ATTEST_HOME") or (Path.home() / ".prime" / "agent"))


def key_path() -> Path:
    return _home() / "attest.key"


def log_path() -> Path:
    return _home() / "attest.log.jsonl"


def thresholds_path() -> Path:
    return _home() / "attest-thresholds.json"


# Overridden per-key by attest-thresholds.json, whose unknown keys are rejected:
# a silently ignored threshold reads as "I relaxed the gate" while it never moved.
DEFAULT_THRESHOLDS: dict[str, Any] = {
    "comment_ratio_max_pct": 3.0,
    # A ratio alone punishes small changes: a 38-line type-level diff scores 10.5%
    # for four defensible comments, which 400 lines would hide at 1%. Both must hold.
    "comment_lines_floor": 6,
    # Zero: a test that reaches inside the unit it tests goes stale silently.
    "patching_calls_max": 0,
}


def thresholds() -> dict[str, Any]:
    """DEFAULT_THRESHOLDS overlaid with attest-thresholds.json, if it exists."""
    path = thresholds_path()
    if not path.is_file():
        return dict(DEFAULT_THRESHOLDS)
    try:
        override = json.loads(path.read_text())
    except ValueError as exc:
        raise AttestError(f"{path} is not valid JSON: {exc}")
    if not isinstance(override, dict):
        raise AttestError(f"{path} must contain a JSON object, got {type(override).__name__}")
    unknown = set(override) - set(DEFAULT_THRESHOLDS)
    if unknown:
        raise AttestError(
            f"{path} sets unknown threshold(s) {sorted(unknown)}; "
            f"known thresholds are {sorted(DEFAULT_THRESHOLDS)}")
    return {**DEFAULT_THRESHOLDS, **override}


def _key() -> bytes:
    """The HMAC key, generated on first use with 0600 permissions."""
    path = key_path()
    if not path.is_file():
        path.parent.mkdir(parents=True, exist_ok=True)
        # Created with the final mode, never briefly world-readable.
        fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "wb") as fh:
            fh.write(secrets.token_bytes(32))
    os.chmod(path, 0o600)
    return path.read_bytes()


# ---------------------------------------------------------------------------
# tokens
# ---------------------------------------------------------------------------

REQUIRED_CLAIMS = ("design_reviewed", "eval_passed")


class Token(str):
    """The token string, carrying its decoded payload and its evidence.

    A plain `str` subclass so it can be dropped straight into
    `attestations=[...]`, while `tok.report` still shows what the verification
    counted and what it deliberately excluded.
    """

    payload: dict[str, Any]
    report: dict[str, Any]

    def __new__(cls, value: str, payload: dict[str, Any], report: dict[str, Any]):
        self = super().__new__(cls, value)
        self.payload = payload
        self.report = report
        return self


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def _sign(payload_b64: str) -> str:
    return hmac.new(_key(), payload_b64.encode("ascii"), hashlib.sha256).hexdigest()


def _issue(claim: str, diff_sha: str, repo: str, base: str, head: str,
           doc_id: Optional[str], quote_sha: Optional[str],
           requirements_n: int, report: dict[str, Any], *,
           base_sha: Optional[str] = None, merge_base: Optional[str] = None,
           head_sha: Optional[str] = None) -> Token:
    # base_sha/merge_base/head_sha are recorded, not just used: `base` is a
    # branch NAME, and a name is not evidence of what was measured. An audit of
    # attest.log.jsonl can now tell whether a claim was bound to the merge base
    # of the remote base branch or to something else.
    payload = {
        "claim": claim,
        "diff_sha": diff_sha,
        "repo": str(Path(repo).resolve()),
        "base": base,
        "base_sha": base_sha,
        "merge_base": merge_base,
        "head_sha": head_sha,
        "head": head,
        "doc_id": doc_id,
        "quote_sha": quote_sha,
        "requirements_n": requirements_n,
        "agent": agent_id(),
        "ts": time.time(),
        "nonce": secrets.token_hex(8),
    }
    payload_b64 = _b64(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode())
    token = Token(f"{payload_b64}.{_sign(payload_b64)}", payload, report)
    _append_log(token)
    return token


def agent_id() -> str:
    """Best-effort identity of the issuing agent, recorded in the payload/log."""
    for var in ("RLM_AGENT_NAME", "PRIME_AGENT_NAME", "AGENT_NAME"):
        value = os.environ.get(var, "").strip()
        if value:
            return value
    session = os.environ.get("RLM_SESSION_DIR", "").strip()
    if session:
        return f"session:{Path(session).name}"
    return os.environ.get("USER", "unknown")


def token_id(token: str) -> str:
    """The short public handle for a token: first 12 hex of its sha256.

    This, not the token, is what goes in the PR body - the token itself is a
    bearer credential and belongs nowhere public.
    """
    return hashlib.sha256(token.encode()).hexdigest()[:12]


def decode(token: str) -> dict[str, Any]:
    """Verify the HMAC and return the payload. Raises on any tampering."""
    payload_b64, _, signature = str(token).partition(".")
    if not payload_b64 or not signature:
        raise AttestError(
            "malformed attestation: expected '<base64url payload>.<hmac>', got "
            f"{str(token)[:60]!r}")
    if not hmac.compare_digest(signature, _sign(payload_b64)):
        raise AttestError(
            "attestation signature does not verify - the payload was edited "
            "after signing, or it was signed with a different key "
            f"({key_path()})")
    try:
        payload = json.loads(_unb64(payload_b64))
    except (ValueError, TypeError) as exc:
        raise AttestError(f"attestation payload is not valid JSON: {exc}")
    if not isinstance(payload, dict) or "claim" not in payload:
        raise AttestError("attestation payload is not a claim object")
    return payload


def verify(tokens: Iterable[str], diff_sha: str,
           required: Iterable[str] = REQUIRED_CLAIMS) -> dict[str, dict[str, Any]]:
    """Check `tokens` against the diff that is actually about to be shipped.

    Every required claim must be present, every token's HMAC must verify, and
    every token's `diff_sha` must equal `diff_sha`. Returns {claim: payload}.
    """
    payloads: dict[str, dict[str, Any]] = {}
    for token in tokens or []:
        payload = decode(token)
        if payload["diff_sha"] != diff_sha:
            raise AttestError(
                f"attestation is bound to a different diff - re-run the "
                f"verification after your last edit\n"
                f"  claim:      {payload['claim']}\n"
                f"  attested:   {payload['diff_sha']}\n"
                f"  about to push: {diff_sha}")
        payloads[payload["claim"]] = payload
    missing = [claim for claim in required if claim not in payloads]
    if missing:
        raise AttestError(
            "missing attestation(s): " + ", ".join(missing) +
            ". Produce them with " +
            ", ".join(f"attest.{claim}(...)" for claim in missing) +
            " and pass attestations=[...]")
    return payloads


def _append_log(token: Token) -> None:
    """Append an issuance record. Never raises into the caller: the log is an
    audit aid, and losing it must not fail a verification that really passed.
    """
    try:
        path = log_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        record = {**token.payload, "token_id": token_id(token), "report": token.report}
        with path.open("a") as fh:
            fh.write(json.dumps(record, sort_keys=True, default=str) + "\n")
    except OSError:
        pass


# ---------------------------------------------------------------------------
# the diff: one canonical command, shared with jj_ship, whose flags keep a user's
# git config out of the hashed bytes so any machine hashes the same commits alike
# ---------------------------------------------------------------------------

_DIFF_FLAGS = ["--no-color", "--no-ext-diff", "--no-textconv", "--unified=3",
               "--find-renames"]


async def _exec(argv: list[str], cwd: str = ".", check: bool = True,
                timeout: float = 300) -> dict:
    if shutil.which(argv[0]) is None:
        raise AttestError(f"binary not found on PATH: {argv[0]}")
    proc = await asyncio.create_subprocess_exec(
        *argv, cwd=cwd,
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    try:
        out, err = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        proc.kill()
        raise AttestError(f"timed out after {timeout}s: {' '.join(argv)}")
    res = {"code": proc.returncode,
           "out": out.decode("utf-8", "replace"),
           "err": err.decode("utf-8", "replace").strip()}
    if check and proc.returncode != 0:
        raise AttestError(f"{' '.join(argv)} exited {proc.returncode}\n"
                          f"{res['err'] or res['out']}")
    return res


def _resolve_from(base: Path, target: str) -> Path:
    candidate = Path(target)
    return candidate.resolve() if candidate.is_absolute() else (base / candidate).resolve()


async def _git_dir(repo: str) -> str:
    """The git directory to run `git diff` against, which `repo` may not contain.

    A `jj workspace add` directory has a `.jj` but NO `.git` at all, so plain
    `git -C <workspace>` dies with "not a git repository" - exactly the failure
    mode jj-ship documents for `gh`, hit here live from a real workspace. jj
    stores the workspace's repo pointer in `.jj/repo` and the colocated git dir
    behind `.jj/repo/store/git_target`, so follow those two hops rather than
    falling back to `jj diff`: a second diff implementation would produce a
    different hash for the same commits, and every mismatch would read as
    tampering.
    """
    path = Path(repo).resolve()
    if (path / ".git").exists():
        return str(path / ".git")
    pointer = path / ".jj" / "repo"
    if pointer.is_file():
        # Relative pointers resolve against the file holding them.
        repo_dir = _resolve_from(pointer.parent, pointer.read_text().strip())
        target = repo_dir / "store" / "git_target"
        if target.is_file():
            return str(_resolve_from(target.parent, target.read_text().strip()))
    raise AttestError(
        f"{path} is not a git checkout and no colocated git store could be found "
        f"through .jj/repo, so there is no diff to hash.")


async def _git(repo: str, *args: str, check: bool = True) -> dict:
    return await _exec(["git", "--git-dir", await _git_dir(repo), *args], check=check)


async def _rev(repo: str, name: str) -> str:
    """Resolve a revision to a commit id, falling back to its remote-tracking ref.

    The fallback matters for the shipping path: a bookmark that has been pushed
    but whose local git ref jj has not exported yet still resolves as
    `origin/<name>`.
    """
    for candidate in (name, f"origin/{name}"):
        r = await _git(repo, "rev-parse", "--verify", f"{candidate}^{{commit}}",
                       check=False)
        if r["code"] == 0:
            return r["out"].strip()
    raise AttestError(
        f"cannot resolve revision {name!r} in {repo} (tried {name!r} and "
        f"'origin/{name}'). Attest AFTER committing, so the bookmark points at "
        f"a real commit.")


def _looks_like_sha(name: str) -> bool:
    return bool(re.fullmatch(r"[0-9a-f]{7,40}", name or ""))


async def _base_anchor(repo: str, base: str) -> tuple[str, str]:
    """Resolve a PR's base to a commit, anchored on the REMOTE. Returns (sha, how).

    Resolving a base branch by name against whatever the local ref happens to
    point at is a false-attestation bug, not an inconvenience. A local `main`
    that is behind the remote is an ancestor of the feature branch, so
    `merge-base(local main, head)` is the OLD tip, and the "diff of my change"
    silently grows every commit other people merged in between. Seen for real on
    fayhealthinc/fay-service#7373: an eval scored 136 comment lines and 7
    patching calls out of strangers' merged tests, and signed the result. The
    signature is what everything downstream trusts, so this must not guess.

    Therefore: a hex sha is taken as given, and a NAME resolves only through
    `refs/remotes/origin/<name>` (refreshed with a single-ref fetch first, since
    a stale remote-tracking ref reproduces the same bug one step removed). If
    only a local ref of that name exists, or the local ref has commits the
    remote does not, this raises instead of choosing - the failing direction has
    to be loud, because the alternative failure is a confident wrong number.
    """
    if _looks_like_sha(base):
        r = await _git(repo, "rev-parse", "--verify", f"{base}^{{commit}}", check=False)
        if r["code"] == 0:
            return r["out"].strip(), "explicit sha"
    fetch = await _git(repo, "fetch", "--quiet", "origin", base, check=False)
    remote = await _git(repo, "rev-parse", "--verify",
                        f"refs/remotes/origin/{base}^{{commit}}", check=False)
    local = await _git(repo, "rev-parse", "--verify", f"refs/heads/{base}^{{commit}}",
                       check=False)
    if remote["code"] != 0:
        origin = await _git(repo, "remote", "get-url", "origin", check=False)
        if origin["code"] != 0:
            # No remote at all: the local ref is the only thing this base could
            # mean, and there is nothing for it to be stale against.
            if local["code"] != 0:
                raise AttestError(
                    f"cannot resolve the base {base!r} in {repo}: neither "
                    f"'refs/heads/{base}' nor an 'origin' remote exists.")
            return local["out"].strip(), f"local {base} (no origin remote)"
        raise AttestError(
            f"cannot anchor the base {base!r} on the remote in {repo}: "
            f"'refs/remotes/origin/{base}' does not resolve, and origin is "
            f"configured ({origin['out'].strip()}), so falling back to a local ref "
            f"would risk measuring the wrong diff"
            + (f" (local {base!r} is at {local['out'].strip()[:12]})"
               if local["code"] == 0 else "")
            + f". Fetch it (`jj git fetch` / `git fetch origin {base}`; this run's "
            f"fetch said: {(fetch['err'] or fetch['out'] or 'nothing').splitlines()[:1]}"
            f"), or pass base='<sha>'.")
    remote_sha = remote["out"].strip()
    if local["code"] == 0 and local["out"].strip() != remote_sha:
        local_sha = local["out"].strip()
        ancestor = await _git(repo, "merge-base", "--is-ancestor", local_sha,
                              remote_sha, check=False)
        if ancestor["code"] != 0:
            raise AttestError(
                f"the base {base!r} is ambiguous in {repo}: local {local_sha[:12]} "
                f"is not an ancestor of origin/{base} ({remote_sha[:12]}), so the "
                f"two disagree about what this change is measured against. "
                f"Reconcile them, or pass base='<sha>'.")
    return remote_sha, f"origin/{base}"


async def resolve_diff(repo: str, base: str, head: str) -> dict[str, Any]:
    """The diff a PR shows, with every revision it was computed from.

    `{base, base_sha, base_how, head, head_sha, merge_base, diff, diff_sha}`.
    The merge base is computed and passed to `git diff` explicitly rather than
    left implicit in `base...head`, so the value that was actually measured is
    recorded in the token and can be audited afterwards.
    """
    base_sha, base_how = await _base_anchor(repo, base)
    head_sha = await _rev(repo, head)
    merge_base = (await _git(repo, "merge-base", base_sha, head_sha))["out"].strip()
    diff = (await _git(repo, "diff", *_DIFF_FLAGS, merge_base, head_sha))["out"]
    return {"base": base, "base_sha": base_sha, "base_how": base_how, "head": head,
            "head_sha": head_sha, "merge_base": merge_base, "diff": diff,
            "diff_sha": hashlib.sha256(diff.encode()).hexdigest()}


async def diff_text(repo: str, base: str, head: str) -> str:
    """The canonical merge-base diff text that gets hashed."""
    return (await resolve_diff(repo, base, head))["diff"]


async def diff_sha(repo: str, base: str, head: str) -> str:
    """sha256 of the canonical diff. Computed here, never taken from a caller.

    This is the whole binding mechanism: attest, then edit the code, and every
    token issued against the old diff stops verifying.
    """
    return hashlib.sha256((await diff_text(repo, base, head)).encode()).hexdigest()


# ---------------------------------------------------------------------------
# diff parsing
# ---------------------------------------------------------------------------

_FILE_RE = re.compile(r"^\+\+\+ b/(.*)$")

# Test files are exempt from the budget and from "production lines".
_TEST_PATH_RE = re.compile(
    r"(^|/)(tests?|__tests__|spec)/|(^|/)conftest\.py$|(^|/)test_[^/]+$"
    r"|_test\.[^/]+$|\.(test|spec)\.[jt]sx?$")

_HASH_EXTS = {"py", "nix", "yml", "yaml", "sh", "bash", "zsh", "toml", "cfg", "ini"}
_SLASH_EXTS = {"ts", "tsx", "js", "jsx", "mjs", "cjs", "css", "scss", "go", "rs",
               "java", "c", "h", "cc", "cpp", "hpp", "kt", "swift", "proto"}

# chdir/syspath_prepend change where a test runs, not what it tests: EXCLUDED.
_PATCH_RE = re.compile(
    r"monkeypatch\.(?:setattr|setenv|delattr|delitem)\b"
    r"|mock\.patch\("
    r"|\bMagicMock\b")
_PATCH_EXCLUDED_RE = re.compile(r"monkeypatch\.chdir\b|\bsyspath_prepend\b")


def code_text(path: str, line: str) -> str:
    """`line` with its comment and its string literals removed.

    The patterns above are matched against THIS, not against the raw line,
    because a scanner that cannot tell a call from a mention flags exactly the
    code most worth having: its own documentation, its own pattern literals, and
    the tests that prove the detection works. Measured on this skill's first
    diff, all 12 "violations" were mentions and none was a call.

    Dropping string literals is honest rather than lenient: a banned call cannot
    hide inside a string and still execute. `r"..."`/`f"..."` prefixes need no
    special case, since it is the quote character that opens the string.

    A backtick counts as a quote too: in every language scored here it is either
    prose notation (`mock.patch(` inside a docstring or a nix comment) or a JS
    template literal, which is a string anyway. That is what stops a docstring
    that NAMES a banned call from being read as making one.

    The one thing a per-line scan cannot see is a plain triple-quoted string, so
    an unbackticked pattern inside a docstring still counts. Left visible on
    purpose - the alternative is parsing every language in a diff.
    """
    comment_starts = ("#",) if path.rsplit(".", 1)[-1].lower() in _HASH_EXTS \
        else ("//", "/*")
    out: list[str] = []
    quote = ""
    index = 0
    while index < len(line):
        char = line[index]
        if quote:
            if char == "\\":
                index += 2
                continue
            if char == quote:
                quote = ""
                out.append(char)
            index += 1
            continue
        if char in "\"'`":
            quote = char
            out.append(char)
            index += 1
            continue
        if any(line.startswith(start, index) for start in comment_starts):
            break
        out.append(char)
        index += 1
    return "".join(out)


def is_test_path(path: str) -> bool:
    return bool(_TEST_PATH_RE.search(path))


def is_code_path(path: str) -> bool:
    """True if the file has a comment syntax this scorer understands.

    Everything else - markdown, JSON, lockfiles, fixtures - is left out of both
    sides of the comment ratio and out of the patching scan. Measured live on
    this skill's own first diff: counting SKILL.md's prose as "production lines"
    quietly diluted the ratio, and a sentence in SKILL.md *describing*
    `mock.patch(` was reported as a patching violation.
    """
    ext = path.rsplit(".", 1)[-1].lower() if "." in path else ""
    return ext in _HASH_EXTS or ext in _SLASH_EXTS


def is_separator_comment(stripped: str) -> bool:
    """True for a comment line with no words in it, e.g. `# -----------`.

    A section rule is typography, not narration, so counting it as a comment
    penalises layout rather than the thing the ratio is trying to catch.
    """
    body = stripped.lstrip("#/*").strip()
    return not any(ch.isalnum() for ch in body)


def is_comment_line(path: str, stripped: str) -> bool:
    """True if `stripped` is a comment line in the language `path` implies.

    `#` for py/nix/yml/sh/toml; `//` and `/*` for the C-family languages, plus a
    block-comment continuation line - which is why the check is `"* "` and not
    bare `"*"`: `*ptr = value;` is code, not a comment.
    """
    ext = path.rsplit(".", 1)[-1].lower() if "." in path else ""
    if ext in _HASH_EXTS:
        return stripped.startswith("#")
    if ext in _SLASH_EXTS:
        return (stripped.startswith(("//", "/*"))
                or stripped == "*" or stripped.startswith("* ")
                or stripped.startswith("*/"))
    return False


def added_lines(diff: str) -> list[tuple[str, str]]:
    """[(path, added line without its '+')] for every added line in `diff`."""
    out: list[tuple[str, str]] = []
    path = ""
    for line in diff.split("\n"):
        match = _FILE_RE.match(line)
        if match:
            path = match.group(1)
            continue
        if line.startswith("+++") or line.startswith("---"):
            continue
        if line.startswith("+") and path:
            out.append((path, line[1:]))
    return out


def touched_paths(diff: str) -> set[str]:
    """Every path the diff touches, from its `+++ b/...` headers.

    Deletions show as `+++ /dev/null`, which is dropped: a requirement citing a
    file the change deletes should cite something that still exists.
    """
    paths = {m.group(1) for m in
             (_FILE_RE.match(line) for line in diff.split("\n")) if m}
    return {p for p in paths if p != "/dev/null"}


def eval_report(diff: str) -> dict[str, Any]:
    """Score `diff` against the thresholds, reporting exclusions beside counts.

    Two measurements, both computed from added lines only (what the change
    introduces, not what it happened to sit next to) and only in files with a
    comment syntax this scorer understands (see `is_code_path`):

    * `comment_ratio_pct` - comment lines added in PRODUCTION files over
      production lines added. Shebangs and word-less separator comments
      (`# -----`) are excluded and counted separately.
    * `patching_calls` - patch-the-world calls added in code. `monkeypatch.chdir`
      and `syspath_prepend` are cwd/import plumbing and are excluded.
    """
    limits = thresholds()
    production_added = 0
    comment_added = 0
    excluded_shebangs = 0
    excluded_separators = 0
    excluded_non_code = 0
    comment_examples: list[str] = []
    patching: list[str] = []
    excluded_patching: list[str] = []
    for path, line in added_lines(diff):
        stripped = line.strip()
        if not is_code_path(path):
            excluded_non_code += 1
            continue
        # Comments and string literals removed: a mention is not a call.
        code = code_text(path, line)
        if _PATCH_EXCLUDED_RE.search(code):
            excluded_patching.append(f"{path}: {stripped}")
        elif _PATCH_RE.search(code):
            patching.append(f"{path}: {stripped}")
        if is_test_path(path):
            continue
        production_added += 1
        if stripped.startswith("#!"):
            excluded_shebangs += 1
            continue
        if is_comment_line(path, stripped):
            if is_separator_comment(stripped):
                excluded_separators += 1
                continue
            comment_added += 1
            if len(comment_examples) < 5:
                comment_examples.append(f"{path}: {stripped[:80]}")
    ratio = (100.0 * comment_added / production_added) if production_added else 0.0
    failures: list[str] = []
    if (ratio > limits["comment_ratio_max_pct"]
            and comment_added > limits["comment_lines_floor"]):
        failures.append(
            f"comment ratio {ratio:.2f}% of production lines added exceeds "
            f"{limits['comment_ratio_max_pct']}% "
            f"({comment_added} comment / {production_added} production lines, "
            f"over the {limits['comment_lines_floor']}-line floor); "
            f"e.g. " + "; ".join(comment_examples))
    if len(patching) > limits["patching_calls_max"]:
        failures.append(
            f"{len(patching)} patch-the-world call(s) added, limit "
            f"{limits['patching_calls_max']}: " + "; ".join(patching[:5]))
    return {
        "production_lines_added": production_added,
        "comment_lines_added": comment_added,
        "comment_ratio_pct": round(ratio, 3),
        "comment_examples": comment_examples,
        "patching_calls": patching,
        "excluded": {
            "shebangs": excluded_shebangs,
            "separator_comments": excluded_separators,
            "non_code_lines": excluded_non_code,
            "cwd_and_syspath_plumbing": excluded_patching,
        },
        "thresholds": limits,
        "thresholds_file": str(thresholds_path()) if thresholds_path().is_file() else None,
        "failures": failures,
    }


async def eval_passed(repo: str, base: str, head: str) -> Token:
    """Attest that the diff `base...head` passes the thresholds. Raises if not.

    The returned token is a `str`; `tok.report` carries the counts and the
    exclusions, so the numbers can go in the PR body.
    """
    resolved = await resolve_diff(repo, base, head)
    report = eval_report(resolved["diff"])
    report["revisions"] = {key: resolved[key] for key in
                           ("base", "base_sha", "base_how", "head", "head_sha",
                            "merge_base")}
    if report["failures"]:
        raise AttestError("eval_passed: " + "\n".join(report["failures"]))
    return _issue("eval_passed", resolved["diff_sha"],
                  repo, base, head, None, None, 0, report,
                  base_sha=resolved["base_sha"], merge_base=resolved["merge_base"],
                  head_sha=resolved["head_sha"])


# ---------------------------------------------------------------------------
# design_reviewed
# ---------------------------------------------------------------------------
# Duplicated from the linear-query skill, not imported: skills install
# independently. There is deliberately no `doc_fetcher=` seam - a seam for
# injecting the document is a seam for fabricating the review.

LINEAR_ENDPOINT = "https://api.linear.app/graphql"
_LINEAR_KEY_PATHS = [
    Path.home() / ".config" / "linear" / "api_key",
    Path.home() / ".prime" / "agent" / "skills" / "linear-query" / ".api_key",
]

_ISSUE_QUERY = """
query($id: String!) {
  issue(id: $id) { id identifier title url description
    comments { nodes { body } } }
}
"""


def _linear_key() -> str:
    key = os.environ.get("LINEAR_API_KEY", "").strip()
    if key:
        return key
    for path in _LINEAR_KEY_PATHS:
        if path.is_file() and (key := path.read_text().strip()):
            return key
    raise AttestError(
        "no Linear API key, so the design document cannot be fetched and "
        f"design_reviewed() cannot be honest. Set LINEAR_API_KEY or write "
        f"{_LINEAR_KEY_PATHS[0]} (chmod 600).")


async def fetch_design_doc(doc_id: str) -> dict[str, Any]:
    """Fetch a Linear issue and return {id, title, url, text}.

    `text` concatenates the description and every comment: a design decision is
    as often in the discussion as in the body, and a quote from either is a
    quote from the design.
    """
    endpoint = os.environ.get("ATTEST_LINEAR_ENDPOINT") or LINEAR_ENDPOINT
    async with httpx.AsyncClient(timeout=45.0) as client:
        resp = await client.post(
            endpoint,
            json={"query": _ISSUE_QUERY, "variables": {"id": doc_id}},
            headers={"Authorization": _linear_key(),
                     "Content-Type": "application/json"})
    try:
        payload = resp.json()
    except ValueError:
        raise AttestError(
            f"Linear returned non-JSON ({resp.status_code}): {resp.text[:300]}")
    if payload.get("errors"):
        raise AttestError(f"Linear rejected the query for {doc_id!r}: "
                          f"{json.dumps(payload['errors'])[:600]}")
    issue = (payload.get("data") or {}).get("issue")
    if not issue:
        raise AttestError(f"Linear has no issue {doc_id!r}")
    bodies = [issue.get("description") or ""]
    bodies += [c.get("body") or "" for c in
               ((issue.get("comments") or {}).get("nodes") or [])]
    return {"id": issue.get("identifier") or doc_id,
            "title": issue.get("title"),
            "url": issue.get("url"),
            "text": "\n\n".join(bodies)}


def _squash(text: str) -> str:
    """Collapse all whitespace, so a quote matches across rewrapping."""
    return " ".join(text.split())


async def design_reviewed(repo: str, base: str, head: str, design_doc_id: str,
                          quote: str, requirements: Iterable[tuple[str, str]]
                          ) -> Token:
    """Attest that the diff implements a design that was actually read.

    Three things are checked, and any failure raises instead of returning a
    token:

    1. `design_doc_id` is FETCHED from Linear - so the document must exist and
       be readable.
    2. `quote` appears in the fetched text verbatim modulo whitespace - so the
       document must have been read, not just named.
    3. every `requirements` entry `("requirement text", "path/file.py:LINE")`
       names a path the diff actually touches - so the mapping from requirement
       to code is checked against the code, not asserted.
    """
    doc = await fetch_design_doc(design_doc_id)
    needle = _squash(quote)
    if not needle:
        raise AttestError("design_reviewed: `quote` is empty; quote the "
                          "sentence of the design this change implements")
    if needle not in _squash(doc["text"]):
        raise AttestError(
            f"design_reviewed: the quote does not appear in {doc['id']} "
            f"({doc.get('url')}) even ignoring whitespace. Quote the design "
            f"you actually read.\n  looked for: {needle[:200]!r}")
    resolved = await resolve_diff(repo, base, head)
    diff = resolved["diff"]
    touched = touched_paths(diff)
    entries = [tuple(r) for r in requirements]
    if not entries:
        raise AttestError("design_reviewed: `requirements` is empty; cite at "
                          "least one requirement and the line that implements it")
    problems: list[str] = []
    for entry in entries:
        if len(entry) != 2:
            raise AttestError(
                f"design_reviewed: each requirement must be "
                f"('requirement text', 'path/file.py:LINE'), got {entry!r}")
        text, citation = entry
        path = str(citation).rsplit(":", 1)[0]
        if path not in touched:
            problems.append(f"{text!r} cites {citation!r}, but the diff does "
                            f"not touch {path!r}")
    if problems:
        raise AttestError(
            "design_reviewed: requirement(s) cite code this diff does not "
            "contain:\n  " + "\n  ".join(problems) +
            "\n  diff touches: " + ", ".join(sorted(touched)))
    report = {
        "doc": {k: doc[k] for k in ("id", "title", "url")},
        "quote_matched": needle[:300],
        "requirements": [{"requirement": t, "citation": c} for t, c in entries],
        "touched_paths": sorted(touched),
        "revisions": {key: resolved[key] for key in
                      ("base", "base_sha", "base_how", "head", "head_sha",
                       "merge_base")},
    }
    return _issue("design_reviewed", resolved["diff_sha"],
                  repo, base, head, doc["id"],
                  hashlib.sha256(needle.encode()).hexdigest(), len(entries), report,
                  base_sha=resolved["base_sha"], merge_base=resolved["merge_base"],
                  head_sha=resolved["head_sha"])


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

async def run(action: str = "report", repo: str = ".", base: str = "main",
              head: str = "@", doc: str = "", quote: str = "",
              requirements: str = "", token: str = "") -> str:
    """action: report | diff-sha | eval-passed | design-reviewed | decode | thresholds

    `requirements` is JSON: [["requirement text", "path/file.py:12"], ...].
    """
    if action == "thresholds":
        return json.dumps(thresholds(), indent=2)
    if action == "decode":
        return json.dumps(decode(token), indent=2)
    if action == "diff-sha":
        return await diff_sha(repo, base, head)
    if action == "report":
        return json.dumps(eval_report(await diff_text(repo, base, head)), indent=2)
    if action == "eval-passed":
        tok = await eval_passed(repo, base, head)
        return json.dumps({"token": str(tok), "report": tok.report}, indent=2)
    if action == "design-reviewed":
        tok = await design_reviewed(repo, base, head, doc, quote,
                                    json.loads(requirements or "[]"))
        return json.dumps({"token": str(tok), "report": tok.report}, indent=2)
    raise AttestError(f"unknown action {action!r}")
