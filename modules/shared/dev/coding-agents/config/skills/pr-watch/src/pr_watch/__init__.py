"""pr-watch: wake this agent when a watched PR gets comments or CI fails, after a quiet window.

`watch()` registers a PR and an RLM heartbeat; every heartbeat turn calls
`poll()`, which reports only activity that has been QUIET for `quiet_seconds`
(default 180). A burst of review comments therefore produces one wake-up after
the reviewer stops typing, not one per comment. Failing CI check-runs are
folded into the same activity stream (see `_check_runs`), because GitHub
Actions failures do not post PR comments on their own - a watcher that only
looked at comments would sit there reporting "quiet" while CI was red, which
is exactly what happened live before this was added.

State lives in ~/.prime/agent/pr-watch/state.json so it survives a kernel
restart; the heartbeat lives in the session, so it stops when the session ends.
"""

from __future__ import annotations

import asyncio
import fcntl
import json
import os
import re
import shutil
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

GH_BIN = os.environ.get("GH_BIN", "gh")
STATE_PATH = Path(os.environ.get(
    "PR_WATCH_STATE", str(Path.home() / ".prime/agent/pr-watch/state.json")))
DEFAULT_QUIET_SECONDS = 180.0
HEARTBEAT_LABEL = "pr-watch"
HEARTBEAT_INSTRUCTION = (
    "pr-watch: run `print(await pr_watch.poll())`. If it reports READY items, "
    "read each one and respond on the PR (reply with `gh pr comment` / "
    "`gh api` on the thread, push a fix with the jj-ship skill if the comment "
    "asks for a change), then continue. If it reports nothing ready, end the "
    "turn immediately with no commentary - a quiet poll is not worth a message."
)

_ANSI_RE = re.compile(r"\x1b\[[0-9;]*[a-zA-Z]")
_PLAIN_ENV = {"NO_COLOR": "1", "CLICOLOR": "0", "GH_FORCE_TTY": "", "GH_PAGER": "cat"}


class PrWatchError(RuntimeError):
    """A gh call failed, or the watchlist was used incorrectly."""


# ---------------------------------------------------------------- state ----

def _owner(owner: Optional[str] = None) -> str:
    """Who a watch belongs to: the AGENT SESSION that owns it.

    Watchers in different sessions must keep independent seen-sets, or the first
    one to mark an item seen silently swallows the other's notification. The
    watcher CHILD inherits its parent's owner (watch_via_child passes it in), so
    a parent's ack() still reaches its own blocked child.
    """
    if owner:
        return owner
    env = os.environ.get("PR_WATCH_OWNER") or os.environ.get(
        "PRIME_AGENT_INTERNAL_DAEMON_WORKER_ACTIVE_SESSION_ID")
    if env:
        return env
    session_dir = os.environ.get("RLM_SESSION_DIR")
    return Path(session_dir).name if session_dir else "default"


@contextmanager
def _locked():
    """Hold an flock around a read-modify-write of the shared state file.

    Several watchers on one machine write this file concurrently; without the
    lock a read-modify-write loses the other's seen-set updates.
    """
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    lock = STATE_PATH.with_suffix(".lock")
    with open(lock, "w") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)


def _load() -> dict:
    if not STATE_PATH.exists():
        return {"watches": {}}
    try:
        return json.loads(STATE_PATH.read_text() or '{"watches": {}}')
    except json.JSONDecodeError:
        return {"watches": {}}


def _save(state: dict) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    # A per-process temp name: a shared one would let two writers interleave
    # into the same file before either rename lands.
    tmp = STATE_PATH.with_suffix(f".{os.getpid()}.tmp")
    tmp.write_text(json.dumps(state, indent=2, default=str))
    tmp.replace(STATE_PATH)


def _key(repo: str, pr: Any, owner: Optional[str] = None) -> str:
    return f"{Path(repo).resolve()}#{pr}@{_owner(owner)}"


# ------------------------------------------------------------------ gh ----

async def _gh(args: list[str], repo: str, check: bool = True) -> str:
    if shutil.which(GH_BIN) is None:
        raise PrWatchError(f"binary not found on PATH: {GH_BIN}")
    proc = await asyncio.create_subprocess_exec(
        GH_BIN, *args, cwd=repo, env={**os.environ, **_PLAIN_ENV},
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    out, err = await proc.communicate()
    out_s = _ANSI_RE.sub("", out.decode("utf-8", "replace")).strip()
    err_s = _ANSI_RE.sub("", err.decode("utf-8", "replace")).strip()
    if check and proc.returncode != 0:
        raise PrWatchError(f"gh {' '.join(args)} exited {proc.returncode}: {err_s or out_s}")
    return out_s


_THREAD_QUERY = """
query($owner:String!, $name:String!, $number:Int!) {
  repository(owner:$owner, name:$name) {
    pullRequest(number:$number) {
      reviewThreads(last:50) {
        nodes { id isResolved path
          comments(last:20) { nodes { author { login } body createdAt url } } }
      }
    }
  }
}
"""


def _ts(value: Optional[str]) -> float:
    if not value:
        return 0.0
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return 0.0


# Conclusions GitHub considers a failed check-run. `neutral` and `skipped` are
# deliberately excluded - they are not failures, just non-outcomes. `cancelled`
# is excluded too: confirmed live on fayhealthinc/fay-ui#3732, where two
# `cancelled` CodeQL runs were just superseded by a later push, not real
# failures. The check-run API gives no reliable way to tell "cancelled because
# a newer commit superseded it" apart from "cancelled because someone manually
# killed it", so rather than guess, treat all cancellations as non-actionable.
_FAILING_CONCLUSIONS = {"failure", "timed_out", "action_required"}


async def _check_run_failures(repo: str, owner: str, name: str,
                              sha: Optional[str]) -> list[dict]:
    """Failing check-runs for a commit SHA, as GitHub's raw check-run dicts.

    Mirrors the check-run query in jj_ship.checks() (see
    modules/shared/dev/coding-agents/config/skills/jj-ship/src/jj_ship/__init__.py)
    but goes straight at `gh api .../check-runs` instead of `gh pr checks`,
    because `gh pr checks` collapses each check-run's identity into a name -
    there is no run/job id to key a "have I already reported this failure"
    seen-set on. Paginated with `per_page=100`: the default page size silently
    truncates on repos with many checks (confirmed live - fay-service had 43
    check-runs on one commit and an unpaged call missed several, including the
    one that had actually failed).
    """
    if not sha:
        return []
    failures: list[dict] = []
    page = 1
    while True:
        raw = await _gh(["api", f"repos/{owner}/{name}/commits/{sha}/check-runs",
                         "-F", "per_page=100", "-F", f"page={page}"],
                        repo=repo, check=False)
        try:
            data = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            # No CI configured, sha not found, auth hiccup, etc: degrade to
            # "no failures" rather than raising - a PR with no CI is not an
            # error condition for a comment-watching skill that now also
            # looks at CI.
            break
        runs = data.get("check_runs", [])
        if not runs:
            break
        failures.extend(r for r in runs if r.get("conclusion") in _FAILING_CONCLUSIONS)
        if len(runs) < 100:
            break
        page += 1
        if page > 10:  # safety cap: no repo legitimately has 1000+ check-runs
            break
    return failures


async def _activity(repo: str, pr: Any) -> list[dict]:
    """Every comment-ish or CI-failure event on a PR, newest last, as flat dicts with an id."""
    raw = await _gh(["pr", "view", str(pr), "--json",
                     "number,url,title,comments,reviews,headRefOid"], repo=repo)
    view = json.loads(raw)
    items: list[dict] = []
    for c in view.get("comments", []):
        items.append({"kind": "comment", "id": c.get("url"),
                      "author": (c.get("author") or {}).get("login"),
                      "body": c.get("body"), "url": c.get("url"),
                      "at": _ts(c.get("createdAt"))})
    for rv in view.get("reviews", []):
        if not (rv.get("body") or "").strip():
            continue
        items.append({"kind": f"review:{rv.get('state','')}", "id": rv.get("url"),
                      "author": (rv.get("author") or {}).get("login"),
                      "body": rv.get("body"), "url": rv.get("url"),
                      "at": _ts(rv.get("submittedAt"))})
    ident = json.loads(await _gh(["repo", "view", "--json", "owner,name"], repo=repo))
    graph = await _gh(["api", "graphql",
                       "-F", f"owner={ident['owner']['login']}",
                       "-F", f"name={ident['name']}",
                       "-F", f"number={view['number']}",
                       "-f", f"query={_THREAD_QUERY}"], repo=repo, check=False)
    if graph:
        try:
            nodes = (json.loads(graph)["data"]["repository"]["pullRequest"]
                     ["reviewThreads"]["nodes"])
        except (KeyError, TypeError, json.JSONDecodeError):
            nodes = []
        for node in nodes:
            # A resolved thread needs no answer; an unresolved one does.
            if node.get("isResolved"):
                continue
            for c in node["comments"]["nodes"]:
                items.append({"kind": "review-thread", "id": c.get("url"),
                              "thread": node["id"], "path": node.get("path"),
                              "author": (c.get("author") or {}).get("login"),
                              "body": c.get("body"), "url": c.get("url"),
                              "at": _ts(c.get("createdAt"))})
    # CI failures fold into the SAME items list, keyed by (run id, conclusion),
    # so they ride the exact debounce/seen-tracking/ack machinery below that
    # comments already use - not a second reporting channel. A check that
    # fails, is fixed, and fails again for a different reason gets a new id
    # (the conclusion changed) and is reported again; the same failure is not.
    for run in await _check_run_failures(repo, ident["owner"]["login"], ident["name"],
                                         view.get("headRefOid")):
        conclusion = run.get("conclusion") or "unknown"
        items.append({
            "kind": f"check-run:{conclusion}",
            "id": f"checkrun:{run.get('id')}:{conclusion}",
            "author": None,
            "body": f"{run.get('name')} - {conclusion}",
            "url": run.get("html_url"),
            "at": _ts(run.get("completed_at") or run.get("started_at")),
        })
    items.sort(key=lambda i: i["at"])
    return items


# --------------------------------------------------------------- public ----

async def watch(repo: str = ".", pr: Optional[Any] = None,
                quiet_seconds: float = DEFAULT_QUIET_SECONDS,
                interval: str = "3m", seed: bool = True,
                heartbeat: bool = True) -> dict:
    """Start watching a PR's comments and (re)arm the wake-up heartbeat.

    seed=True marks everything already on the PR as seen, so only NEW activity
    wakes the agent. Pass seed=False to be handed the existing backlog too.
    """
    repo = str(Path(repo).resolve())
    if pr is None:
        raise PrWatchError("pass pr=<number>")
    items = await _activity(repo, pr) if seed else []
    with _locked():
        state = _load()
        state["watches"][_key(repo, pr)] = {
            "repo": repo, "pr": pr, "quiet_seconds": quiet_seconds,
            "owner": _owner(),
            "seen": [i["id"] for i in items if i.get("id")],
            "added_at": datetime.now(timezone.utc).isoformat(),
        }
        _save(state)
    hb = await _ensure_heartbeat(interval) if heartbeat else None
    return {"watching": _key(repo, pr), "seeded": len(items),
            "quiet_seconds": quiet_seconds, "heartbeat": hb}


async def _ensure_heartbeat(interval: str = "3m") -> dict:
    import rlm_heartbeat  # kernel-only

    existing = await rlm_heartbeat.list()
    jobs = existing.get("heartbeats", existing) if isinstance(existing, dict) else existing
    for job in jobs or []:
        if isinstance(job, dict) and job.get("label") == HEARTBEAT_LABEL:
            return {"reused": job.get("id"), "interval": job.get("interval")}
    created = await rlm_heartbeat.create(
        HEARTBEAT_INSTRUCTION, interval=interval, label=HEARTBEAT_LABEL,
        delivery_mode="follow_up")
    return {"created": created}


async def poll(mark_seen: bool = True) -> str:
    """Report watched-PR activity that has been quiet for the debounce window.

    New activity is held until nothing newer has arrived for `quiet_seconds`
    (default 180), so one burst of review comments produces one wake-up.
    """
    state = _load()
    mine = _owner()
    now = datetime.now(timezone.utc).timestamp()
    ready_lines: list[str] = []
    holding: list[str] = []
    for key, entry in list(state["watches"].items()):
        if entry.get("owner", mine) != mine:
            continue   # another session's watcher reports to its own agent
        try:
            items = await _activity(entry["repo"], entry["pr"])
        except PrWatchError as exc:
            holding.append(f"{key}: poll failed ({exc})")
            continue
        seen = set(entry.get("seen", []))
        fresh = [i for i in items if i.get("id") and i["id"] not in seen]
        if not fresh:
            continue
        newest = max(i["at"] for i in fresh)
        quiet_for = now - newest
        window = float(entry.get("quiet_seconds", DEFAULT_QUIET_SECONDS))
        if quiet_for < window:
            holding.append(
                f"{key}: {len(fresh)} new item(s), still settling "
                f"({int(window - quiet_for)}s of quiet left)")
            continue
        ready_lines.append(f"READY {key} - {len(fresh)} new item(s):")
        for i in fresh:
            where = f" [{i.get('path')}]" if i.get("path") else ""
            ready_lines.append(
                f"  - {i['kind']}{where} by {i.get('author')}: "
                f"{(i.get('body') or '').strip()}\n    {i.get('url')}")
        if mark_seen:
            entry["seen"] = sorted(seen | {i["id"] for i in fresh})
    if mark_seen:
        _save(state)
    if not state["watches"]:
        return "pr-watch: nothing is being watched."
    if not ready_lines:
        return "pr-watch: nothing ready." + ("\n  " + "\n  ".join(holding) if holding else "")
    return "\n".join(ready_lines + (["", "still settling:"] + holding if holding else []))


async def ack(repo: str = ".", pr: Optional[Any] = None, all: bool = False) -> str:
    """Mark everything currently on a PR as seen, without reporting it.

    Call this right after you post a reply. The agent comments through the same
    GitHub account as its human, so its OWN reply would otherwise read as new
    activity and wake it up to answer itself.
    """
    mine = _owner()
    state = _load()
    # Only this session's own watches: acking another session's watcher would
    # silence a notification its own agent never saw.
    keys = [k for k, v in state["watches"].items() if v.get("owner", mine) == mine] \
        if all else [_key(str(Path(repo).resolve()), pr)]
    current: dict[str, list] = {}
    for key in keys:
        entry = state["watches"].get(key)
        if entry is not None:
            current[key] = sorted({i["id"] for i in await _activity(entry["repo"], entry["pr"])
                                   if i.get("id")})
    with _locked():
        state = _load()
        for key, ids in current.items():
            state["watches"].setdefault(key, {})["seen"] = ids
        _save(state)
    acked = len(current)
    return f"pr-watch: acknowledged current activity on {acked} watch(es)."


async def watching() -> str:
    """List the watched PRs and their debounce windows."""
    state = _load()
    if not state["watches"]:
        return "pr-watch: nothing is being watched."
    return "\n".join(
        f"{k}  quiet={v.get('quiet_seconds')}s  seen={len(v.get('seen', []))}"
        for k, v in state["watches"].items())


async def unwatch(repo: str = ".", pr: Optional[Any] = None, all: bool = False) -> str:
    """Stop watching one PR, or every PR (`all=True`) and cancel the heartbeat."""
    state = _load()
    if all:
        state["watches"] = {}
        _save(state)
        try:
            import rlm_heartbeat
            jobs = await rlm_heartbeat.list()
            entries = jobs.get("heartbeats", jobs) if isinstance(jobs, dict) else jobs
            for job in entries or []:
                if isinstance(job, dict) and job.get("label") == HEARTBEAT_LABEL:
                    await rlm_heartbeat.delete(job["id"])
        except Exception as exc:  # heartbeat teardown must not lose the state write
            return f"pr-watch: cleared watchlist; heartbeat cleanup failed: {exc}"
        return "pr-watch: cleared watchlist and cancelled the heartbeat."
    key = _key(str(Path(repo).resolve()), pr)
    state["watches"].pop(key, None)
    _save(state)
    return f"pr-watch: no longer watching {key}"


# ------------------------------------------------------- push (no polling
# turns) ----
# A heartbeat costs one model turn per interval even when nothing happened.
# A child agent costs one turn TOTAL: it starts `serve()` in a single tool call
# that blocks for hours, polls inside that call (zero tokens), and calls
# agent_message.send() from inside the still-running cell when activity settles.

async def serve(repo: str = ".", pr: Optional[Any] = None,
                quiet_seconds: float = DEFAULT_QUIET_SECONDS,
                poll_seconds: float = 30.0, max_hours: float = 6.0,
                notify: bool = True, seed: bool = True,
                owner: Optional[str] = None,
                notify_role: str = "parent",
                notify_name: Optional[str] = None) -> str:
    """Block here, polling a PR, and message an agent when activity settles.

    Meant to be the ONLY call a watcher sub-agent makes: the loop runs inside
    this one tool call, so idle polling consumes no model tokens. Returns when
    `max_hours` elapses so the caller can re-arm.

    `notify_role`/`notify_name` default to messaging this watcher's own
    PARENT, which is correct for a `watch_via_child()`-spawned watcher (the
    caller IS its parent). A watcher spawned on someone else's behalf - see
    `watch_via_sibling()`, where the watcher's parent and the original caller
    are different sessions - must override these to reach the right session,
    e.g. `notify_role="sibling", notify_name=<original caller>`.
    """
    import time

    repo = str(Path(repo).resolve())
    if pr is None:
        raise PrWatchError("pass pr=<number>")
    # The seen-set lives in the shared state file, not just in memory: this
    # loop blocks for hours, so the parent agent's own ack() (after it posts a
    # reply of its own) has no other way to reach it - a steering message would
    # queue behind the very cell it needs to influence.
    key = _key(repo, pr, owner)
    seeded = sorted({i["id"] for i in await _activity(repo, pr) if i.get("id")}) if seed else None
    with _locked():
        state = _load()
        entry = state["watches"].setdefault(key, {"repo": repo, "pr": pr,
                                                  "owner": _owner(owner)})
        entry["quiet_seconds"] = quiet_seconds
        if seeded is not None:
            entry["seen"] = seeded
        entry.setdefault("seen", [])
        _save(state)

    def _seen_now() -> set:
        with _locked():
            return set((_load()["watches"].get(key) or {}).get("seen", []))

    def _mark(ids: set) -> None:
        with _locked():
            st = _load()
            e = st["watches"].setdefault(key, {"repo": repo, "pr": pr,
                                              "owner": _owner(owner), "seen": []})
            e["seen"] = sorted(set(e.get("seen", [])) | ids)
            _save(st)
    deadline = time.time() + max_hours * 3600.0
    sent = errors = 0
    pending: dict[str, dict] = {}
    while time.time() < deadline:
        await asyncio.sleep(poll_seconds)
        try:
            items = await _activity(repo, pr)
        except PrWatchError:
            errors += 1
            continue
        seen = _seen_now()
        for i in items:
            if i.get("id") and i["id"] not in seen:
                pending[i["id"]] = i
        for gone in [k for k in pending if k in seen]:   # acked while pending
            pending.pop(gone)
        if not pending:
            continue
        newest = max(i["at"] for i in pending.values())
        if time.time() - newest < quiet_seconds:
            continue  # still arriving - hold the whole burst
        lines = [f"pr-watch: {len(pending)} new item(s) on {repo}#{pr} "
                 f"(quiet for {int(quiet_seconds)}s):"]
        for i in sorted(pending.values(), key=lambda x: x["at"]):
            where = f" [{i.get('path')}]" if i.get("path") else ""
            lines.append(f"  - {i['kind']}{where} by {i.get('author')}: "
                         f"{(i.get('body') or '').strip()}\n    {i.get('url')}")
        message = "\n".join(lines)
        if notify:
            import agent_message  # kernel-only; delivered while this cell runs
            await agent_message.send(message, receiver_role=notify_role,
                                     receiver_name=notify_name)
        else:
            print(message)
        sent += 1
        _mark(set(pending))
        pending.clear()
    return (f"pr-watch serve finished after {max_hours}h: "
            f"{sent} notification(s), {errors} poll error(s). Re-arm to keep watching.")


CHILD_TASK = """You are a PR watcher. Make exactly ONE tool call and nothing else:

    import pr_watch
    print(await pr_watch.serve(repo={repo!r}, pr={pr!r}, quiet_seconds={quiet}, \
                               poll_seconds={poll}, max_hours={hours},
                               owner={owner!r}))

That call BLOCKS for up to {hours} hours by design - this is expected, not a
hang. It polls the PR inside that single cell and messages your parent itself
whenever comment activity settles, so you must NOT poll it, print progress, or
send any message of your own. When the call finally returns, call it again with
the same arguments unless your parent told you to stop."""


async def watch_via_child(repo: str = ".", pr: Optional[Any] = None,
                          quiet_seconds: float = DEFAULT_QUIET_SECONDS,
                          poll_seconds: float = 30.0, max_hours: float = 6.0,
                          name: str = "pr-watcher") -> dict:
    """Spawn a watcher sub-agent that pushes wake-ups instead of being polled.

    Costs one model turn to start; idle polling afterwards is free. Use instead
    of watch()'s heartbeat when the PR may sit quiet for a long time.

    Requires RLM depth headroom: this spawns a CHILD of the calling session
    (depth+1). If the caller is already at max RLM recursion depth, `rlm.run`
    has nowhere to go and this cannot be used - see `watch_via_sibling()`.
    """
    import rlm  # kernel-only

    # The child inherits THIS session's owner id, so the seen-set it shares is
    # the one this agent's ack() writes to - and a watcher in another session
    # keeps its own.
    task = CHILD_TASK.format(repo=str(Path(repo).resolve()), pr=pr,
                             quiet=quiet_seconds, poll=poll_seconds,
                             hours=max_hours, owner=_owner())
    handle = await rlm.run(task, name=name)
    return {"child": getattr(handle, "name", name), "owner": _owner(),
            "rlm_child_id": getattr(handle, "rlm_child_id", None),
            "watching": f"{Path(repo).resolve()}#{pr}",
            "note": "The child messages you when activity settles; never poll it."}


# --------------------------------------------------- sibling watcher (depth
# cap) ----
# `rlm.run` (used by watch_via_child) is the only spawn primitive the kernel
# exposes to a running agent's own code, and the host always admits its result
# one RLM depth below the CALLER - there is no "spawn at my own depth"
# primitive available from inside a session, only from whatever orchestrated
# that session in the first place. So a session already at max RLM recursion
# depth cannot call `rlm.run` at all: there is no depth left to spawn into,
# and calling `serve()` directly in its own kernel just blocks the very
# session that needed to stay free (the bug this module exists to avoid).
#
# The fix is to have this session's OWN PARENT do the spawning on its behalf.
# A child spawned BY THE PARENT lands at the same depth as this session - a
# real sibling, not a grandchild - which is exactly the depth-same
# relationship the caller needs. This session cannot call `rlm.run` in the
# parent's kernel directly, so it asks via
# `agent_message.send(..., receiver_role="parent")` with a fully literal task
# string (mirroring CHILD_TASK) naming this session as the watcher's
# report-to target. `serve()`'s `notify_role`/`notify_name` let that spawned
# watcher report with `receiver_role="sibling"` straight back to this session,
# rather than to its own parent (which is a different session - the common
# parent - not the original caller).
#
# This is honest about the mechanism but not fully synchronous the way
# watch_via_child() is: the actual `rlm.run` call happens on the PARENT's next
# turn, not inside this function, so it depends on the parent noticing and
# acting on the steering message (exactly like any other steering message).
# What this function guarantees is the part under this session's own control:
# it returns immediately without blocking, and once the parent spawns the
# watcher, that watcher reports directly back to THIS session by name - never
# routing the notification through the parent's own turn, so the parent does
# not end up making decisions that were this session's job.
SIBLING_TASK = """You are a PR watcher, spawned on behalf of your PARENT's own
sibling session {caller!r} (that session is at max RLM recursion depth and
could not spawn this watcher itself). Make exactly ONE tool call and nothing
else:

    import pr_watch
    print(await pr_watch.serve(repo={repo!r}, pr={pr!r}, quiet_seconds={quiet}, \
                               poll_seconds={poll}, max_hours={hours},
                               owner={owner!r}, notify_role="sibling",
                               notify_name={caller!r}))

That call BLOCKS for up to {hours} hours by design - this is expected, not a
hang. It polls the PR inside that single cell and messages session {caller!r}
directly (via receiver_role="sibling") whenever activity settles - NOT your
own parent, which is a different session than the one that asked for this
watch. You must NOT poll it, print progress, or send any message of your own.
When the call finally returns, call it again with the same arguments unless
{caller!r} told you to stop."""


async def watch_via_sibling(repo: str = ".", pr: Optional[Any] = None,
                            quiet_seconds: float = DEFAULT_QUIET_SECONDS,
                            poll_seconds: float = 30.0, max_hours: float = 6.0,
                            name: str = "pr-watcher") -> dict:
    """Ask THIS session's parent to spawn a watcher that reports back here.

    Use `watch_via_child()` normally; use `watch_via_sibling()` instead ONLY
    when this session is already at max RLM recursion depth and cannot spawn
    a child of its own (`rlm.run` would have no depth left to spawn into).

    Unlike `watch_via_child()`, the actual spawn does not happen inside this
    call: there is no "spawn at my own depth" primitive exposed to a running
    session's own code, only to whatever orchestrated THIS session in the
    first place - which, from here, is reachable only as "my parent". This
    function sends the parent a literal, fully-specified task (mirroring
    `CHILD_TASK`) asking it to spawn a watcher child of ITS OWN; that child
    lands at the same depth as this session (a true sibling) rather than one
    depth below it. The spawned sibling reports settled activity directly
    back to this session via `receiver_role="sibling"`, never through the
    parent's own turn - so the parent does not end up making decisions that
    were this session's job, and this session stays completely free the
    entire time.

    Because the request only takes effect once the parent acts on it, this is
    less immediate than `watch_via_child()` (which spawns synchronously). It
    is the best available fallback given the depth cap: this session cannot
    call `rlm.run` at all in that situation.
    """
    import agent_message  # kernel-only

    agents = await agent_message.list_agents()
    caller = agents["current"]["name"]
    task = SIBLING_TASK.format(repo=str(Path(repo).resolve()), pr=pr,
                               quiet=quiet_seconds, poll=poll_seconds,
                               hours=max_hours, owner=_owner(), caller=caller)
    request = (
        f"pr-watch: I am at max RLM recursion depth and cannot spawn my own "
        f"watcher child. Please spawn a sub-agent named {name!r} with this "
        f"exact task (a single literal `rlm.run` call is enough - do not "
        f"paraphrase the task text):\n\n{task}"
    )
    receipt = await agent_message.send(request, receiver_role="parent")
    return {"caller": caller, "owner": _owner(),
            "watching": f"{Path(repo).resolve()}#{pr}",
            "requested_via": "parent", "receipt": receipt,
            "note": "Spawn happens on the parent's next turn, not synchronously; "
                    "the sibling it creates reports back to THIS session "
                    "directly, never through the parent."}


async def stop_watchers(name: str = "pr-watcher", exact: bool = False) -> str:
    """Delete watcher sub-agents by SESSION NAME, matching by prefix unless exact.

    Sharp edge this exists for: an `RLMSubagent` from `rlm.list_subagents()`
    exposes `session_name`, and its `name` attribute is None. Matching on `name`
    silently selects nothing, so a "delete the old watcher" step no-ops and
    leaves a stale child running - observed live, as duplicate notifications
    from a watcher that was believed deleted.
    """
    import rlm  # kernel-only

    stopped = []
    for sub in await rlm.list_subagents():
        session_name = getattr(sub, "session_name", None) or ""
        hit = session_name == name if exact else session_name.startswith(name)
        if hit and getattr(sub, "status", None) == "running":
            await rlm.delete_subagent(sub)
            stopped.append(f"{session_name} ({getattr(sub, 'rlm_child_id', '?')})")
    return ("pr-watch: stopped " + ", ".join(stopped)) if stopped else \
        f"pr-watch: no running sub-agent whose session_name matches {name!r}"


async def run(action: str = "poll", repo: str = ".", pr: str = "",
              quiet_seconds: float = DEFAULT_QUIET_SECONDS,
              interval: str = "3m", seed: bool = True) -> str:
    """Watch PR comments and wake the agent once activity goes quiet.

    action: watch | poll | watching | unwatch | unwatch-all
    """
    if action == "watch":
        return json.dumps(await watch(repo=repo, pr=pr or None,
                                      quiet_seconds=quiet_seconds,
                                      interval=interval, seed=seed), indent=2)
    if action == "poll":
        return await poll()
    if action == "watching":
        return await watching()
    if action == "unwatch":
        return await unwatch(repo=repo, pr=pr or None)
    if action == "ack":
        return await ack(repo=repo, pr=pr or None)
    if action == "unwatch-all":
        return await unwatch(all=True)
    raise PrWatchError(f"unknown action {action!r}")
