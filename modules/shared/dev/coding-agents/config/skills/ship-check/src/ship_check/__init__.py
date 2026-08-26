"""ship-check: does a pull request carry attestations that actually validate?

Answers one question about a PR, from its URL alone: is there a
`Shipped-With:` trailer in its BODY whose attestation ids resolve to real
issued claims, covering every required claim, bound to the diff that PR
currently shows? A matching string is not enough - a forged id, an id issued
for another branch, and a trailer left behind after another push all fail here.

Two deliberate restrictions, each of which a looser check would get wrong:

* The trailer is read from the pull request BODY only, never from comments. An
  agent that quotes the trailer format in a review comment - or writes the
  literal string in prose to explain it - must not thereby pass. `jj_ship`
  writes the trailer into the body and nowhere else, so the body is the whole
  universe of legitimate trailers.
* Anything that cannot be established is a FAILURE with a reason, not a pass.
  The point of the check is to notice a PR whose gate was skipped; a check that
  shrugs when the evidence is missing notices nothing.

`check_message()` adds the interception policy on top: extract every PR URL in
an inbound agent message, check each at most once ever (the record is on disk
and survives restarts), and render the verdict text that the caller shows to
the reader of that message.
"""

from __future__ import annotations

import asyncio
import fcntl
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Iterable, Optional

GH_BIN = os.environ.get("GH_BIN", "gh")

_ANSI_RE = re.compile(r"\x1b\[[0-9;]*[a-zA-Z]")

_TRAILER_RE = re.compile(
    r"^[ \t]*Shipped-With:[ \t]+jj_ship/(?P<version>[^\s]+)[ \t]+"
    r"attest=(?P<ids>[0-9a-f]{6,}(?:,[0-9a-f]{6,})*)[ \t]*$",
    re.MULTILINE,
)

_PR_URL_RE = re.compile(
    r"https?://(?:www\.)?github\.com/"
    r"(?P<owner>[A-Za-z0-9](?:[A-Za-z0-9._-]*[A-Za-z0-9])?)/"
    r"(?P<name>[A-Za-z0-9](?:[A-Za-z0-9._-]*[A-Za-z0-9])?)/pull/(?P<number>\d+)"
)

_FROM_RELATIONSHIP_RE = re.compile(r"^\[from (?P<role>parent|sibling|child)(?::(?P<name>.*))?\]$",
                                   re.MULTILINE)
_FROM_RE = re.compile(r"^From: (?P<rest>.*)$", re.MULTILINE)
_FROM_ACTIVE_RE = re.compile(r"active (?P<active>[0-9a-f]{6,})")


class ShipCheckError(RuntimeError):
    """The check could not be performed at all (bad input, missing tooling)."""


# ---------------------------------------------------------------------------
# on-disk state: SHIP_CHECK_HOME redirects it, so a test never writes the real one
# ---------------------------------------------------------------------------

def _home() -> Path:
    return Path(os.environ.get("SHIP_CHECK_HOME")
                or os.environ.get("ATTEST_HOME")
                or (Path.home() / ".prime" / "agent"))


def state_path() -> Path:
    return _home() / "ship-check.state.json"


def _with_state(mutate) -> Any:
    """Read-modify-write the dedupe record under an exclusive lock.

    Locked and atomic because the interceptor can run twice concurrently (two
    messages naming the same PR arriving together), and "at most once per PR
    URL" has to hold across processes, not just within one.
    """
    path = state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    lock = path.with_suffix(".lock")
    with lock.open("a+") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        try:
            try:
                state = json.loads(path.read_text())
            except (OSError, ValueError):
                state = {}
            if not isinstance(state, dict):
                state = {}
            state.setdefault("prs", {})
            result = mutate(state)
            tmp = path.with_suffix(".json.tmp")
            tmp.write_text(json.dumps(state, indent=2, sort_keys=True))
            os.replace(tmp, path)
            return result
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)


def checked_prs() -> dict[str, Any]:
    return _with_state(lambda state: dict(state["prs"]))


def forget(url: str) -> None:
    """Drop the record for `url`, so the next message naming it is checked again."""
    _with_state(lambda state: state["prs"].pop(url, None))


# ---------------------------------------------------------------------------
# parsing
# ---------------------------------------------------------------------------

def canonical_pr_url(owner: str, name: str, number: Any) -> str:
    return f"https://github.com/{owner}/{name}/pull/{int(number)}"


def find_pr_urls(text: str) -> list[dict[str, Any]]:
    """Every GitHub PR URL in `text`, deduplicated, in order of appearance."""
    found: dict[str, dict[str, Any]] = {}
    for match in _PR_URL_RE.finditer(text or ""):
        owner, name, number = match["owner"], match["name"], int(match["number"])
        url = canonical_pr_url(owner, name, number)
        found.setdefault(url, {"url": url, "slug": f"{owner}/{name}", "number": number})
    return list(found.values())


def parse_trailer(body: str) -> list[str]:
    """Attestation ids from the LAST `Shipped-With:` line in a PR body.

    The last one, because a body that was stamped twice (reopened, re-shipped)
    ends with the current claim set, and an earlier line describes a diff that
    has since moved.
    """
    matches = list(_TRAILER_RE.finditer(body or ""))
    if not matches:
        return []
    return [part for part in matches[-1]["ids"].split(",") if part]


def find_sender(text: str) -> dict[str, Any]:
    """Who sent this agent message: {role, name, active_session_id} as available."""
    sender: dict[str, Any] = {}
    relationship = _FROM_RELATIONSHIP_RE.search(text or "")
    if relationship:
        sender["role"] = relationship["role"]
        name = (relationship["name"] or "").strip()
        if name:
            sender["name"] = name
    line = _FROM_RE.search(text or "")
    if line:
        active = _FROM_ACTIVE_RE.search(line["rest"])
        if active:
            sender["active_session_id"] = active["active"]
    return sender


# ---------------------------------------------------------------------------
# the issuance log
# ---------------------------------------------------------------------------

def _attest():
    try:
        import attest
    except ImportError as exc:  # pragma: no cover - deployment error, not logic
        raise ShipCheckError(
            "the `attest` skill is not importable, so no attestation can be "
            "validated. It lives beside this skill in config/skills/attest."
        ) from exc
    return attest


def issued_claims(token_ids: Iterable[str]) -> dict[str, dict[str, Any]]:
    """Issuance records for `token_ids`, read from attest's append-only log.

    The log is the only place an id can be resolved back to what was claimed:
    the PR body carries ids precisely because the tokens themselves are bearer
    credentials. An id absent from the log therefore never had a token behind
    it on this machine - which is exactly the forgery case.
    """
    wanted = {str(t) for t in token_ids}
    if not wanted:
        return {}
    path = _attest().log_path()
    records: dict[str, dict[str, Any]] = {}
    try:
        lines = path.read_text().splitlines()
    except OSError:
        return {}
    for line in lines:
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except ValueError:
            continue
        token_id = record.get("token_id")
        if token_id in wanted:
            records[token_id] = record
    return records


# ---------------------------------------------------------------------------
# GitHub
# ---------------------------------------------------------------------------

def _gh_json(args: list[str], timeout: float = 60) -> Any:
    """Run `gh` and parse its JSON, stripping ANSI escapes first.

    A user with `color: always` gets escapes even when stdout is a pipe, which
    breaks json.loads - the first real call this module made reported a perfectly
    good API response as "non-JSON output".
    """
    if shutil.which(GH_BIN) is None:
        raise ShipCheckError(f"binary not found on PATH: {GH_BIN}")
    proc = subprocess.run([GH_BIN, *args], capture_output=True, text=True,
                          timeout=timeout,
                          env={**os.environ, "NO_COLOR": "1", "CLICOLOR": "0",
                               "GH_PAGER": "cat", "GH_FORCE_TTY": ""})
    if proc.returncode != 0:
        raise ShipCheckError(
            f"gh {' '.join(args)} exited {proc.returncode}: "
            f"{(proc.stderr or proc.stdout).strip()}")
    try:
        return json.loads(_ANSI_RE.sub("", proc.stdout))
    except ValueError as exc:
        raise ShipCheckError(f"gh {' '.join(args)} returned non-JSON output") from exc


def pull_request(slug: str, number: Any) -> dict[str, Any]:
    """The PR as the REST API sees it: body, base ref, head ref and head sha.

    REST, not `gh pr view`: the `pr` subcommands ask GraphQL for fields GitHub
    has begun rejecting (`projectCards`), and this check must not inherit that
    fragility - see jj_ship.set_pr_body.
    """
    raw = _gh_json(["api", f"repos/{slug}/pulls/{int(number)}"])
    return {
        "body": raw.get("body") or "",
        # When the PR was opened: it decides which claims it had to carry.
        "created_at": raw.get("created_at") or "",
        "base": ((raw.get("base") or {}).get("ref") or ""),
        "head": ((raw.get("head") or {}).get("ref") or ""),
        "head_sha": ((raw.get("head") or {}).get("sha") or ""),
        "state": raw.get("state") or "",
        "draft": bool(raw.get("draft")),
        "url": raw.get("html_url") or "",
    }


# ---------------------------------------------------------------------------
# verification
# ---------------------------------------------------------------------------

def _run_async(coro) -> Any:
    """Run an attest coroutine from synchronous code.

    A separate thread when a loop is already running, because this module is
    called both from a plain CLI process (the interceptor) and from an agent's
    kernel, where `asyncio.run` would refuse.
    """
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    import threading
    box: dict[str, Any] = {}

    def target() -> None:
        try:
            box["value"] = asyncio.run(coro)
        except BaseException as exc:  # re-raised on the calling thread
            box["error"] = exc

    thread = threading.Thread(target=target)
    thread.start()
    thread.join()
    if "error" in box:
        raise box["error"]
    return box["value"]


def _fetch_pr_refs(repo: str, base: str, head: str) -> None:
    """Best effort: make the PR's base and head reachable locally.

    The binding check compares against what the PR shows NOW, so the local
    clone has to know those commits. A failure here is not fatal by itself -
    the commits may already be present - so it is left to the diff to complain.
    """
    attest = _attest()
    try:
        git_dir = _run_async(attest._git_dir(repo))
    except Exception:
        return
    refs = [ref for ref in (base, head) if ref]
    if not refs:
        return
    subprocess.run(["git", "--git-dir", git_dir, "fetch", "--quiet", "origin", *refs],
                   capture_output=True, text=True, timeout=120, check=False)


def _binding_failure(record: dict[str, Any], pr: dict[str, Any]) -> Optional[str]:
    """Why `record` does not attest THIS pull request, or None when it does."""
    attest = _attest()
    claim = record.get("claim")
    if pr["head"] and record.get("head") not in (pr["head"], pr["head_sha"]) \
            and record.get("head_sha") != pr["head_sha"]:
        return (f"the {claim} attestation was issued for head {record.get('head')!r}, "
                f"but the PR's head branch is {pr['head']!r}")
    # A base recorded as a SHA is not compared by name - passing the merge-base
    # sha is the recommended way to attest, and rejecting it failed a correctly
    # attested PR live (jack-michaud/nix#20). The diff binding below is the check.
    recorded_base = str(record.get("base") or "")
    base_is_sha = bool(re.fullmatch(r"[0-9a-f]{7,40}", recorded_base))
    if pr["base"] and not base_is_sha \
            and recorded_base not in (pr["base"], f"origin/{pr['base']}"):
        return (f"the {claim} attestation was issued against base "
                f"{recorded_base!r}, but the PR's base branch is {pr['base']!r}")
    repo = record.get("repo") or ""
    if not repo or not Path(repo).exists():
        return (f"the {claim} attestation names the checkout {repo!r}, which is not "
                f"present here, so it cannot be re-bound to the PR's diff")
    _fetch_pr_refs(repo, pr["base"], pr["head"])
    head = pr["head_sha"] or pr["head"]
    try:
        current = _run_async(attest.diff_sha(repo, pr["base"], head))
    except Exception as exc:
        return (f"the {claim} attestation could not be re-bound to the PR's diff "
                f"({type(exc).__name__}: {exc})")
    if current != record.get("diff_sha"):
        return (f"the {claim} attestation is bound to a different diff than the PR "
                f"now shows (attested {str(record.get('diff_sha'))[:12]}, PR is "
                f"{current[:12]}), so the trailer is stale")
    return None


def verify_pr(slug: str, number: Any, pr: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    """Does this PR carry valid attestations? Returns a verdict dict.

    `{"url", "slug", "number", "ok", "reason", "token_ids", "claims"}`. `ok` is
    True only when a trailer in the BODY names ids that all resolve to issued
    claims, those claims cover the set `attest.required_claims()` demanded when
    this PR was OPENED, and every one of them still binds to the diff the PR
    shows.

    The required set is resolved from the PR's `created_at`, not from now. Both
    this module and `jj_ship` read it at call time, so a claim added to the
    tuple would otherwise fail every trailer already stamped - merged PRs
    included - the moment the new code deployed. That is a fleet outage with a
    delay fuse, and it is the reason the epoch exists.
    """
    attest = _attest()
    owner, _, name = slug.partition("/")
    verdict: dict[str, Any] = {
        "url": canonical_pr_url(owner, name, number),
        "slug": slug,
        "number": int(number),
        "ok": False,
        "reason": "",
        "token_ids": [],
        "claims": [],
    }
    try:
        pr = pr if pr is not None else pull_request(slug, number)
    except ShipCheckError as exc:
        verdict["reason"] = f"the PR could not be read: {exc}"
        return verdict
    verdict["state"] = pr.get("state")
    verdict["draft"] = pr.get("draft")
    token_ids = parse_trailer(pr["body"])
    verdict["token_ids"] = token_ids
    if not token_ids:
        verdict["reason"] = ("the PR body carries no `Shipped-With:` trailer, so no "
                             "attestation was ever stamped on it")
        return verdict
    records = issued_claims(token_ids)
    unknown = [token_id for token_id in token_ids if token_id not in records]
    if unknown:
        verdict["reason"] = (
            "the trailer names attestation id(s) with no issuance record: "
            + ", ".join(unknown)
            + f" (searched {attest.log_path()}). An id that was never issued here "
              "cannot be honoured - the trailer is forged or was written by hand")
        return verdict
    verdict["claims"] = sorted({str(record.get("claim")) for record in records.values()})
    required = attest.required_claims(at=pr.get("created_at") or None)
    verdict["required"] = list(required)
    missing = [claim for claim in required if claim not in verdict["claims"]]
    if missing:
        verdict["reason"] = ("the trailer's attestations do not cover the claim(s) "
                             "required when this PR was opened"
                             + (f" ({pr['created_at']})" if pr.get("created_at") else "")
                             + ": " + ", ".join(missing))
        return verdict
    for token_id in token_ids:
        failure = _binding_failure(records[token_id], pr)
        if failure:
            verdict["reason"] = failure
            return verdict
    verdict["ok"] = True
    verdict["reason"] = ("every attestation id in the body resolves to an issued claim "
                         "bound to the diff this PR shows")
    return verdict


# ---------------------------------------------------------------------------
# the interception policy
# ---------------------------------------------------------------------------

NOTICE_HEADER = "SHIP-CHECK: attestations DO NOT validate"
OK_HEADER = "SHIP-CHECK: attestations validate"


def render_notice(verdicts: list[dict[str, Any]], sender: dict[str, Any]) -> str:
    """The text shown to whoever reads the intercepted message.

    Written as an instruction with the remediation already spelled out, because
    the mechanism that performs the check cannot itself send an agent message -
    see SKILL.md, "What this is and is not".
    """
    failures = [verdict for verdict in verdicts if not verdict["ok"]]
    if not failures:
        return ""
    role = sender.get("role") or "child"
    name = sender.get("name")
    target = (f'receiver_role="{role}"'
              + (f', receiver_name="{name}"' if name and role != "parent" else ""))
    lines = [NOTICE_HEADER, ""]
    for verdict in failures:
        lines.append(f"* {verdict['url']} - {verdict['reason']}.")
    lines += [
        "",
        "This check ran on the message above before you read it, once for this PR "
        "URL, against the PR body only (never its comments).",
        "",
        "Required next action, before you act on the PR itself: ask the worker that "
        "sent this message to ship it through `jj_ship`, so the body carries a "
        "`Shipped-With:` trailer whose attestations bind to the pushed diff:",
        "",
        "```python",
        "await agent_message.send(",
        '    "ship-check: your PR is not attested. Re-run the gate and stamp the '
        'trailer: produce attest.design_reviewed(...) and attest.eval_passed(...) '
        'against the diff you pushed, then call jj_ship.mark_ready(<pr>, '
        'attestations=[...]) (or jj_ship.open_pr(..., attestations=[...])). Reply '
        'when the trailer is on the body.",',
        f"    {target},",
        ")",
        "```",
    ]
    return "\n".join(lines)


def check_message(text: str, *, force: bool = False) -> dict[str, Any]:
    """Check every PR URL in an inbound agent message, at most once per URL.

    Returns `{"sender", "verdicts", "skipped", "failures", "notice"}`.
    `verdicts` holds the PRs checked on this call; `skipped` the URLs already on
    record from an earlier call (that record survives restarts, which is what
    "maximum 1 time for each PR URL" requires).
    """
    sender = find_sender(text)
    prs = find_pr_urls(text)
    already = checked_prs()
    verdicts: list[dict[str, Any]] = []
    skipped: list[str] = []
    for pr in prs:
        if not force and pr["url"] in already:
            skipped.append(pr["url"])
            continue
        verdict = verify_pr(pr["slug"], pr["number"])
        verdicts.append(verdict)
        _with_state(lambda state, verdict=verdict: state["prs"].__setitem__(
            verdict["url"], {"at": time.time(), "ok": verdict["ok"],
                             "reason": verdict["reason"]}))
    failures = [verdict for verdict in verdicts if not verdict["ok"]]
    return {
        "sender": sender,
        "verdicts": verdicts,
        "skipped": skipped,
        "failures": failures,
        "notice": render_notice(verdicts, sender),
    }


def main(argv: Optional[list[str]] = None) -> int:
    """CLI: `--message-file <path>` / `--message-stdin`, or `--pr <url>` by hand.

    A file as well as stdin because the caller that matters - a `pi` extension -
    executes commands through `pi.exec`, whose `ExecOptions` has no stdin.

    Prints one JSON object on stdout. Exit status is 0 whenever the check ran,
    including when it failed the PR: the caller reads `failures`.
    """
    argv = list(sys.argv[1:] if argv is None else argv)
    force = "--force" in argv
    argv = [arg for arg in argv if arg != "--force"]
    try:
        if argv[:1] == ["--pr"]:
            found = find_pr_urls(argv[1] if len(argv) > 1 else "")
            if not found:
                raise ShipCheckError(f"not a GitHub PR URL: {argv[1:2]}")
            result = {"verdicts": [verify_pr(found[0]["slug"], found[0]["number"])]}
            result["failures"] = [v for v in result["verdicts"] if not v["ok"]]
        elif argv[:1] == ["--message-file"]:
            if len(argv) < 2:
                raise ShipCheckError("--message-file needs a path")
            result = check_message(Path(argv[1]).read_text(), force=force)
        elif argv[:1] == ["--message-stdin"] or not argv:
            result = check_message(sys.stdin.read(), force=force)
        else:
            raise ShipCheckError(f"unknown arguments: {argv}")
    except ShipCheckError as exc:
        json.dump({"error": str(exc)}, sys.stdout)
        sys.stdout.write("\n")
        return 2
    json.dump(result, sys.stdout, default=str)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
