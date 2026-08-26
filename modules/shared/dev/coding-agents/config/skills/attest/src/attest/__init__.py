"""attest: signed, diff-bound attestations for the shipping path.

Three verification functions - `design_reviewed()`, `eval_passed()` and
`description_humanized()` - each do real work, bind their result to the exact
diff they inspected, and return an opaque token. `jj_ship.open_pr()` /
`jj_ship.mark_ready()` refuse to create a non-draft PR without all three tokens,
and recompute the diff hash from the tree jj is about to push - and, for the
description claim, the hash of the body it is about to post - before accepting
them.

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
import importlib
import importlib.util
import json
import os
import re
import secrets
import shutil
import time
from datetime import datetime, timezone
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
    # jack-michaud/nix#27 was ~13000 characters and was refused unread.
    "description_chars_max": 6000,
    # The humanizer's own 0..1 score, 1 = worst. Permissive: this gate auto-fixes.
    "description_slop_score_max": 0.5,
    # Below this nothing is scored: a score alone punishes brevity (see SKILL.md).
    "description_short_chars": 800,
    # null = computed and logged but NEVER required. See required_claims().
    "description_claim_required_since": None,
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

BASE_CLAIMS = ("design_reviewed", "eval_passed")
DESCRIPTION_CLAIM = "description_humanized"

# The PRE-epoch set, for callers written before `required_claims()`. Deliberately
# the smaller one: a stale reader under-requires, which cannot refuse a good ship.
REQUIRED_CLAIMS = BASE_CLAIMS


def _as_timestamp(value: Any) -> Optional[float]:
    """A unix timestamp from a number or an ISO-8601 string, or None.

    GitHub hands out `2026-08-25T19:16:12Z`; a caller in-process has a float.
    Both mean the same instant and both have to work, because one of them is
    what decides whether an already-merged PR is still valid.
    """
    if value is None or value == "" or value is False:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip()
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        raise AttestError(
            f"cannot read {text!r} as a time: expected an ISO-8601 instant like "
            f"'2026-09-01T00:00:00Z' or a unix timestamp")
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.timestamp()


def required_claims(at: Any = None) -> tuple[str, ...]:
    """The claims a ship must carry for something that happened at `at`.

    An EPOCH, not a flag day, because `REQUIRED_CLAIMS` is read at call time by
    `jj_ship` and by `ship_check` alike - so adding a claim to a bare tuple
    retroactively invalidates the trailer on every PR already shipped, including
    merged ones. `ship_check` passes the PR's `created_at`, so a PR is judged by
    what was required when it was opened; `verify()` passes nothing and gets
    now, because a ship happening now is happening now.

    `description_claim_required_since` in the thresholds file is that epoch, and
    `null` (the default) means the description claim is never required anywhere:
    it is computed, logged and ignored. See SKILL.md - the scorer's ability to
    tell slop from length is under test, and until that settles this check must
    not be able to block a ship on any machine.
    """
    since = _as_timestamp(thresholds()["description_claim_required_since"])
    if since is None:
        return BASE_CLAIMS
    when = time.time() if at is None else _as_timestamp(at)
    if when is None or when < since:
        return BASE_CLAIMS
    return BASE_CLAIMS + (DESCRIPTION_CLAIM,)


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
           head_sha: Optional[str] = None, body_sha: Optional[str] = None,
           passed: Optional[bool] = None,
           degraded: Optional[bool] = None) -> Token:
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
        # None, not absent, on the other two claims: an audit can then tell
        # "no body was measured" from "this token predates the field".
        "body_sha": body_sha,
        # False = issued while advisory and did not pass; kept as evidence.
        "passed": passed,
        # None = inference never entered the picture; see description_humanized.
        "degraded": degraded,
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
           required: Optional[Iterable[str]] = None,
           body: Optional[str] = None) -> dict[str, dict[str, Any]]:
    """Check `tokens` against the diff - and body - actually about to be shipped.

    Every required claim must be present, every token's HMAC must verify, and
    every token's `diff_sha` must equal `diff_sha`. Returns {claim: payload}.

    `required` defaults to `required_claims()` resolved HERE rather than to a
    tuple bound at import: which claims a ship needs is a runtime question with
    an epoch behind it, and a default argument would freeze the answer at the
    moment this module was first imported.

    `body`, when given, is the PR description about to be posted, and the
    `description_humanized` token's `body_sha` must equal its canonical hash.
    Without it the claim would be a claim about *some* text, which is theatre:
    the caller that posts the body is the only one that knows what it posts, so
    it is the caller that has to hand it over. Passing None skips only that
    comparison; a caller that cannot see the body (an audit reading the log,
    say) still gets the diff binding.
    """
    required = required_claims() if required is None else required
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
    described = payloads.get(DESCRIPTION_CLAIM)
    if body is not None and described:
        posted = body_sha(body)
        if described.get("body_sha") != posted:
            raise AttestError(
                f"the description attestation is bound to a different body - "
                f"the text was edited after it was humanized, so re-run "
                f"attest.description_humanized() on the body you are posting\n"
                f"  attested:  {described.get('body_sha')}\n"
                f"  about to post: {posted}\n"
                f"(the `Shipped-With:` trailer and line endings are excluded "
                f"from this hash; nothing else is)")
    if described is not None and DESCRIPTION_CLAIM in required \
            and described.get("passed") is False:
        raise AttestError(
            "the description attestation was issued while the claim was "
            "advisory and it did NOT pass, so it cannot satisfy the claim now "
            "that it is required. Re-run attest.description_humanized() on the "
            "body you are posting and fix what it reports.")
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


def _read_design_doc_file(source: str) -> dict[str, Any]:
    path = Path(source).expanduser()
    text = path.read_text(encoding="utf-8", errors="replace")
    if not text.strip():
        raise AttestError(f"design_reviewed: design doc {path} is empty")
    return {"id": str(path), "title": path.name,
            "url": path.resolve().as_uri(), "text": text}


async def load_design_doc(source: str) -> dict[str, Any]:
    """Load a design doc from wherever it lives.

    Linear is one place a design doc lives, not the only one: a spec.md in the
    repo, a proposal, or an exported lavish plan is as much the design as a
    tracker issue. A `source` naming an existing file is read from disk;
    anything else is treated as a Linear ID and fetched.
    """
    if Path(source).expanduser().is_file():
        return _read_design_doc_file(source)
    return await fetch_design_doc(source)


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

    1. `design_doc_id` is LOADED - a path to an existing file (spec.md, a
       proposal, an exported lavish plan) is read from disk, anything else is
       fetched from Linear - so the document must exist and be readable.
    2. `quote` appears in the fetched text verbatim modulo whitespace - so the
       document must have been read, not just named.
    3. every `requirements` entry `("requirement text", "path/file.py:LINE")`
       names a path the diff actually touches - so the mapping from requirement
       to code is checked against the code, not asserted.
    """
    doc = await load_design_doc(design_doc_id)
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
# description_humanized
# ---------------------------------------------------------------------------

DISCLOSURE_LINE = "*Authored by an agent on behalf of Jack (@jack-michaud).*"

# Tolerant: the policy fixes that an artifact says an agent wrote it on someone's
# behalf, not the wording (a stricter match would stack a second disclosure).
_DISCLOSURE_RE = re.compile(
    r"agent\b[^\n]{0,80}\bon behalf of\b|\bon behalf of\b[^\n]{0,80}\bagent\b",
    re.IGNORECASE)

_TRAILER_RE = re.compile(r"(?m)^Shipped-With:.*$")

DEFAULT_HUMANIZER_PATH = (Path.home() / ".prime" / "agent" / "ceo-console" /
                          "humanizer" / "humanizer.py")

_DESCRIPTION_THRESHOLDS = ("description_chars_max", "description_slop_score_max",
                           "description_short_chars")


def canonical_body(text: str) -> str:
    """The bytes a body hash is taken over. Three normalisations, each earned:

    * the `Shipped-With:` trailer is removed, because `jj_ship` appends it
      AFTER this token exists - the trailer names the token - so a hash that
      covered it could never match anything;
    * `\r\n` becomes `\n`, because GitHub hands bodies back CRLF-terminated
      and `mark_ready()` re-posts the body it just read;
    * leading and trailing whitespace goes, because `gh` and the REST API
      disagree about the final newline.

    Everything else is content and is hashed exactly as written.
    """
    return _TRAILER_RE.sub("", (text or "").replace("\r\n", "\n")).strip()


def body_sha(text: str) -> str:
    """sha256 of `canonical_body(text)` - what the description claim binds to."""
    return hashlib.sha256(canonical_body(text).encode()).hexdigest()


def preserved_trailers(text: str) -> list[str]:
    """Every `Shipped-With:` line in `text`, byte-exact, in order."""
    return _TRAILER_RE.findall((text or "").replace("\r\n", "\n"))


def has_disclosure(text: str) -> bool:
    return bool(_DISCLOSURE_RE.search(text or ""))


def ensure_disclosure(text: str) -> tuple[str, bool]:
    """`text` with the agent-authorship line prepended if it has none.

    Added, not refused. The line is fixed boilerplate: adding it cannot make the
    description claim anything it did not already claim, and failing a ship over
    a missing constant is friction with no reader on the other end. A missing
    `Shipped-With:` trailer is the opposite case and does raise - that one
    carries token IDs nothing here can regenerate.
    """
    if has_disclosure(text):
        return text, False
    return DISCLOSURE_LINE + "\n\n" + (text or "").lstrip(), True


def _load_module_from_file(path: Path) -> Any:
    spec = importlib.util.spec_from_file_location("attest_humanizer", str(path))
    if spec is None or spec.loader is None:
        raise AttestError(f"{path} is not importable as a python module")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_humanizer() -> tuple[Any, str]:
    """The module providing `humanize()`/`score()`, and where it was found.

    Three places, first hit wins: `ATTEST_HUMANIZER` (a module name or a `.py`
    path), an installed `humanizer` module, then `DEFAULT_HUMANIZER_PATH`.

    Unlike `design_reviewed()`, which deliberately has no injection seam, this
    lookup is a seam and that is fine: the humanizer is a TOOL, not the
    evidence. A stub that rewrites nothing still has to produce text this
    function's caller measures itself - length is counted here, and the hash is
    taken over what will actually be posted.

    Every failed candidate is reported, because "the humanizer is missing" and
    "the humanizer is broken" need different fixes and look identical otherwise.
    """
    override = os.environ.get("ATTEST_HUMANIZER", "").strip()
    sources = ([(f"ATTEST_HUMANIZER={override}", override)] if override else
               [("import humanizer", "humanizer"),
                (str(DEFAULT_HUMANIZER_PATH), str(DEFAULT_HUMANIZER_PATH))])
    tried: list[str] = []
    for how, source in sources:
        try:
            module = (_load_module_from_file(Path(source).expanduser())
                      if source.endswith(".py")
                      else importlib.import_module(source))
        except Exception as exc:
            tried.append(f"{how}: {type(exc).__name__}: {exc}")
            continue
        absent = [name for name in ("humanize", "score")
                  if not callable(getattr(module, name, None))]
        if absent:
            tried.append(f"{how}: loaded, but no callable {', '.join(absent)}()")
            continue
        return module, how
    raise AttestError("no humanizer with humanize()/score() could be loaded:\n  "
                      + "\n  ".join(tried))


def _measure(module: Any, text: str) -> dict[str, Any]:
    """`score()`'s whole dict for `text`: slop_score AND every signal behind it.

    The full vector is kept, not just the number, because the number is what is
    under question - see SKILL.md. A row that records only `slop_score: 0.76`
    cannot later answer "was that a length detector wearing a slop costume?",
    and answering that is the point of logging an advisory claim at all.
    """
    try:
        result = module.score(text)
        return dict(result) if isinstance(result, dict) else {}
    except Exception as exc:
        return {"error": f"{type(exc).__name__}: {exc}"}


def _slop_score(module: Any, text: str) -> Optional[float]:
    """`score()`'s slop_score for `text`, or None if it could not produce one.

    None is not zero. It means "not measured", and every caller reports it as
    that rather than letting an unscored description read as a clean one.
    """
    value = _measure(module, text).get("slop_score")
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def humanize_body(body: str, context: Optional[dict] = None,
                  enforce: Optional[bool] = None) -> dict:
    """Score the description, rewrite it if it needs it, return what to post.

    The policy in one sentence: **rewrite and proceed; refuse only when a
    description needs a rewrite and cannot get one.** The other two claims have
    no choice but to refuse - nothing here can review a design or delete a
    patching call for you - but slop has a mechanical fix, and a gate that
    blocks shipping over a fixable defect it could have fixed is a gate agents
    learn to route around. So a refusal is kept for the two cases where
    proceeding would be a lie: the rewrite could not run, or it ran and the
    result is still over the line.

    `enforce` decides whether such a case RAISES or is merely RECORDED, and
    defaults to whether `required_claims()` currently demands this claim. While
    the claim is advisory the work still happens in full - scored, rewritten,
    logged with the whole signal vector - and only the refusal is withheld. A
    silent advisory check would generate no evidence, and evidence is the only
    thing that can ever justify turning the epoch on.

    The measurements this function reports are its OWN, not the humanizer's.
    `chars_after` is counted here from the text that will be posted; the
    humanizer's `metrics` are carried through beside them, unaudited, for
    comparison. That is what stops a stub humanizer from asserting its way past
    the length limit.

    Three degraded cases, all decided rather than left to chance:

    * **short** - under `description_short_chars` the description is not scored,
      not rewritten, not flagged. A score alone punishes brevity, which is the
      thing this check is supposed to be encouraging.
    * **no humanizer** - length is still checked here, and the report says the
      claim covers length only. Over the length limit with no humanizer fails:
      there is nothing left that could fix it.
    * **humanizer raises** (no inference, network down) - fails only if the
      description was flagged. An unflagged description never needed it.

    A rewriter that degrades to "returned the input unchanged, inference
    unavailable" rather than raising - the sane thing for a rewriter to do - is
    indistinguishable here from one that tried and could not compress, so the
    failure quotes the humanizer's own `reason` instead of guessing between them.

    `humanizer_run` is the rewriter's own record of that: `{attempts, succeeded,
    degraded, failures, duration_ms, attempted_at}`, copied through whole and
    unaudited. `None` means `humanize()` was never called - under the floor, no
    humanizer, or already within the limits - which is NOT degradation and must
    not be logged as any. Only keys this function names are read, so a rewriter
    may add its own without breaking the gate.
    """
    limits = thresholds()
    enforced = (DESCRIPTION_CLAIM in required_claims()) if enforce is None else enforce
    text, disclosure_added = ensure_disclosure(body or "")
    canon = canonical_body(text)
    report: dict[str, Any] = {
        "chars_before": len(canonical_body(body or "")),
        "chars_after": len(canon),
        "slop_score_before": None,
        "slop_score_after": None,
        "signals_before": None,
        "signals_after": None,
        "flagged": False,
        "humanized": False,
        "passed": True,
        "enforced": enforced,
        "failures": [],
        "disclosure_added": disclosure_added,
        "preserved": preserved_trailers(text),
        "humanizer": None,
        "humanizer_metrics": None,
        "humanizer_run": None,
        "reason": "",
        "body": text,
        "thresholds": {key: limits[key] for key in _DESCRIPTION_THRESHOLDS},
        "thresholds_file": str(thresholds_path()) if thresholds_path().is_file() else None,
    }

    def fail(message: str) -> dict:
        """Record a failure - and raise it too, but only where it can block."""
        report["failures"].append(message)
        report["passed"] = False
        if enforced:
            raise AttestError("description_humanized: " + message)
        report["reason"] = message
        return report

    if len(canon) < limits["description_short_chars"]:
        report["reason"] = (
            f"{len(canon)} characters is under the "
            f"{limits['description_short_chars']}-character floor: not scored, "
            f"not rewritten, not flagged")
        return report
    try:
        module, how = load_humanizer()
    except AttestError as exc:
        report["humanizer"] = f"unavailable: {str(exc).splitlines()[0]}"
        if len(canon) > limits["description_chars_max"]:
            return fail(
                f"the description is {len(canon)} characters, over the "
                f"{limits['description_chars_max']}-character limit, and no "
                f"humanizer is available to cut it. Shorten it by hand and "
                f"re-run.\n  {exc}")
        report["reason"] = (
            f"no humanizer available; {len(canon)} characters is under the "
            f"{limits['description_chars_max']}-character limit, so this claim "
            f"covers LENGTH ONLY - the description was not scored for slop")
        return report
    report["humanizer"] = how
    signals = _measure(module, canon)
    before = _slop_score(module, canon)
    report["signals_before"] = signals
    report["slop_score_before"] = before
    over_length = len(canon) > limits["description_chars_max"]
    over_slop = before is not None and before > limits["description_slop_score_max"]
    report["flagged"] = over_length or over_slop
    if not report["flagged"]:
        report["slop_score_after"] = before
        report["signals_after"] = signals
        report["reason"] = (
            f"{len(canon)} characters and slop_score {before} are both within "
            f"the limits; left alone")
        return report
    try:
        result = module.humanize(text, dict(context or {})) or {}
    except Exception as exc:
        return fail(
            f"the description is over the limits ({len(canon)} chars, slop_score "
            f"{before}) and the humanizer could not run: {type(exc).__name__}: "
            f"{exc}. Cut it by hand and re-run - this is the one case where "
            f"proceeding would attest to work that did not happen.")
    run = result.get("run")
    report["humanizer_run"] = dict(run) if isinstance(run, dict) else None
    rewritten = result.get("text")
    if not isinstance(rewritten, str) or not rewritten.strip():
        return fail(
            f"the humanizer returned no usable text ({type(rewritten).__name__}), "
            f"so there is nothing to attest to.")
    for trailer in report["preserved"]:
        if trailer not in rewritten:
            # report["body"] stays the INPUT: a trailer-losing rewrite must
            # never become the text somebody posts.
            return fail(
                f"the rewrite dropped the attestation trailer {trailer!r}. "
                f"ship-check reads the PR body and nothing else, so a lost "
                f"trailer silently breaks the chain. Refusing rather than "
                f"re-attaching it: a humanizer that drops the one block it was "
                f"told to carry through verbatim is broken, and quietly "
                f"repairing it hides that.")
    rewritten, added_late = ensure_disclosure(rewritten)
    report["disclosure_added"] = disclosure_added or added_late
    canon_after = canonical_body(rewritten)
    after_signals = _measure(module, canon_after)
    after = _slop_score(module, canon_after)
    report.update({
        "body": rewritten,
        "chars_after": len(canon_after),
        "slop_score_after": after,
        "signals_after": after_signals,
        "humanized": True,
        "humanizer_metrics": result.get("metrics"),
        "reason": str(result.get("reason") or "").strip() or "rewritten by the humanizer",
    })
    still: list[str] = []
    if len(canon_after) > limits["description_chars_max"]:
        still.append(f"{len(canon_after)} characters after the rewrite, limit "
                     f"{limits['description_chars_max']}")
    if after is not None and after > limits["description_slop_score_max"]:
        still.append(f"slop_score {after} after the rewrite, limit "
                     f"{limits['description_slop_score_max']}")
    if still:
        return fail(
            "; ".join(still) +
            f". The humanizer said: {report['reason']}. Editing it by hand is "
            f"the way past this, not moving the threshold (thresholds live in "
            f"{thresholds_path()}).")
    return report


async def description_humanized(repo: str, base: str, head: str, body: str,
                                context: Optional[dict] = None,
                                enforce: Optional[bool] = None) -> Token:
    """Attest that the PR description was scored, and rewritten if it needed it.

    `tok.report["body"]` is the text to post - that exact text, because the
    token binds its hash and `jj_ship` recomputes that hash from the body it is
    about to send. Post anything else and the ship refuses.

    **Run this even when the claim is not required.** While
    `required_claims()` leaves it out, a failure is recorded in the payload
    (`passed: false`) and in the report instead of raising, and the token is
    issued anyway - so `attest.log.jsonl` accumulates one row per real PR
    description carrying the body hash, the verdict and the whole signal vector.
    That log is the only thing that can ever settle whether the scorer measures
    slop or merely length, and `verify()` refuses a `passed: false` token the
    moment the epoch turns the claim on, so recording one cannot let anything
    through.

    The payload also carries `degraded`, signed: True only when inference was
    ATTEMPTED and every attempt FAILED, False when it ran or was not needed, and
    None when `humanize()` was never called at all. A degraded run and an
    "already clean" judgement produce identical text and mean opposite things,
    so the flag-day decision needs that difference on the record rather than
    guessed from the text afterwards. The rewriter's whole `run` block is kept
    in the report, which is logged beside the payload.

    Ordering, stated plainly: this runs BEFORE the body is posted, and a body
    can be edited on github.com a minute after the PR opens. Nothing signed on
    this machine can prevent that. What the binding buys is that the text that
    went THROUGH the gate is pinned - `body_sha` is in the payload and in
    `attest.log.jsonl` - so a later edit is a hash mismatch away from being
    visible (`body_matches()`). Detection, not prevention, exactly like the
    diff binding.
    """
    report = humanize_body(body, context, enforce=enforce)
    resolved = await resolve_diff(repo, base, head)
    report["revisions"] = {key: resolved[key] for key in
                           ("base", "base_sha", "base_how", "head", "head_sha",
                            "merge_base")}
    report["body_sha"] = body_sha(report["body"])
    run = report.get("humanizer_run") or {}
    return _issue("description_humanized", resolved["diff_sha"],
                  repo, base, head, None, None, 0, report,
                  base_sha=resolved["base_sha"], merge_base=resolved["merge_base"],
                  head_sha=resolved["head_sha"], body_sha=report["body_sha"],
                  passed=report["passed"],
                  degraded=run.get("degraded") if run else None)


def body_matches(token: str, body: str) -> bool:
    """True if `body` is the description `token` was issued over.

    The after-the-fact half of the binding, for auditing a live PR: fetch the
    body, canonicalise, compare. The trailer and line endings are excluded (see
    `canonical_body`); every other edit shows up.
    """
    return decode(token).get("body_sha") == body_sha(body)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _cli_body(body: str) -> str:
    """A `--body` that names an existing file is that file. A PR description is
    long enough, and quoted enough, that passing it as an argv word is a
    mangling waiting to happen."""
    path = Path(body).expanduser()
    return path.read_text() if body and path.is_file() else body


async def run(action: str = "report", repo: str = ".", base: str = "main",
              head: str = "@", doc: str = "", quote: str = "",
              requirements: str = "", token: str = "", body: str = "",
              context: str = "") -> str:
    """action: report | diff-sha | eval-passed | design-reviewed |
    humanize-report | description-humanized | check-body | decode | thresholds |
    required-claims

    `requirements` is JSON: [["requirement text", "path/file.py:12"], ...].
    `body` is the PR description, or a path to a file holding it; `context` is
    JSON passed through to the humanizer.
    """
    if action == "humanize-report":
        return json.dumps(humanize_body(_cli_body(body),
                                        json.loads(context or "{}")), indent=2)
    if action == "description-humanized":
        tok = await description_humanized(repo, base, head, _cli_body(body),
                                          json.loads(context or "{}"))
        return json.dumps({"token": str(tok), "report": tok.report}, indent=2)
    if action == "check-body":
        return json.dumps({"matches": body_matches(token, _cli_body(body)),
                           "body_sha": body_sha(_cli_body(body))}, indent=2)
    if action == "thresholds":
        return json.dumps(thresholds(), indent=2)
    if action == "required-claims":
        return json.dumps({"now": list(required_claims()),
                           "base": list(BASE_CLAIMS),
                           "epoch": thresholds()["description_claim_required_since"]},
                          indent=2)
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
