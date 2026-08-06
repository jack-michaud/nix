"""pr-watch: wake this agent when a watched PR gets comments, after a quiet window.

`watch()` registers a PR and an RLM heartbeat; every heartbeat turn calls
`poll()`, which reports only comment activity that has been QUIET for
`quiet_seconds` (default 180). A burst of review comments therefore produces one
wake-up after the reviewer stops typing, not one per comment.

State lives in ~/.prime/agent/pr-watch/state.json so it survives a kernel
restart; the heartbeat lives in the session, so it stops when the session ends.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import shutil
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

def _load() -> dict:
    if not STATE_PATH.exists():
        return {"watches": {}}
    try:
        return json.loads(STATE_PATH.read_text() or '{"watches": {}}')
    except json.JSONDecodeError:
        return {"watches": {}}


def _save(state: dict) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = STATE_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, indent=2, default=str))
    tmp.replace(STATE_PATH)


def _key(repo: str, pr: Any) -> str:
    return f"{Path(repo).resolve()}#{pr}"


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


async def _activity(repo: str, pr: Any) -> list[dict]:
    """Every comment-ish event on a PR, newest last, as flat dicts with an id."""
    raw = await _gh(["pr", "view", str(pr), "--json",
                     "number,url,title,comments,reviews"], repo=repo)
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
    state = _load()
    state["watches"][_key(repo, pr)] = {
        "repo": repo, "pr": pr, "quiet_seconds": quiet_seconds,
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
    now = datetime.now(timezone.utc).timestamp()
    ready_lines: list[str] = []
    holding: list[str] = []
    for key, entry in state["watches"].items():
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
    state = _load()
    keys = list(state["watches"]) if all else [_key(str(Path(repo).resolve()), pr)]
    acked = 0
    for key in keys:
        entry = state["watches"].get(key)
        if entry is None:
            continue
        items = await _activity(entry["repo"], entry["pr"])
        entry["seen"] = sorted({i["id"] for i in items if i.get("id")})
        acked += 1
    _save(state)
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
                notify: bool = True, seed: bool = True) -> str:
    """Block here, polling a PR, and message the PARENT agent when activity settles.

    Meant to be the ONLY call a watcher sub-agent makes: the loop runs inside
    this one tool call, so idle polling consumes no model tokens. Returns when
    `max_hours` elapses so the caller can re-arm.
    """
    import time

    repo = str(Path(repo).resolve())
    if pr is None:
        raise PrWatchError("pass pr=<number>")
    # The seen-set lives in the shared state file, not just in memory: this
    # loop blocks for hours, so the parent agent's own ack() (after it posts a
    # reply of its own) has no other way to reach it - a steering message would
    # queue behind the very cell it needs to influence.
    key = _key(repo, pr)
    state = _load()
    entry = state["watches"].setdefault(key, {"repo": repo, "pr": pr})
    entry["quiet_seconds"] = quiet_seconds
    if seed:
        entry["seen"] = sorted({i["id"] for i in await _activity(repo, pr) if i.get("id")})
    entry.setdefault("seen", [])
    _save(state)

    def _seen_now() -> set:
        return set((_load()["watches"].get(key) or {}).get("seen", []))

    def _mark(ids: set) -> None:
        st = _load()
        e = st["watches"].setdefault(key, {"repo": repo, "pr": pr, "seen": []})
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
            await agent_message.send(message, receiver_role="parent")
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
                               poll_seconds={poll}, max_hours={hours}))

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
    """
    import rlm  # kernel-only

    task = CHILD_TASK.format(repo=str(Path(repo).resolve()), pr=pr,
                             quiet=quiet_seconds, poll=poll_seconds, hours=max_hours)
    handle = await rlm.run(task, name=name)
    return {"child": getattr(handle, "name", name),
            "rlm_child_id": getattr(handle, "rlm_child_id", None),
            "watching": f"{Path(repo).resolve()}#{pr}",
            "note": "The child messages you when activity settles; never poll it."}


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
