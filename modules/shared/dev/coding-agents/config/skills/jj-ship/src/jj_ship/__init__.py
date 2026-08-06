"""jj-ship: commit with jj, push a bookmark, open a PR, and monitor CI + PR comments.

A small VCS/PR loop for agent sessions, modelled on agent-harness's own
`default` workflow ship stage but usable directly from the IPython kernel.
Every function shells out to the real `jj` and `gh` binaries.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import shutil
from typing import Any, Optional

JJ_BIN = os.environ.get("JJ_BIN", "jj")
GH_BIN = os.environ.get("GH_BIN", "gh")


class JjShipError(RuntimeError):
    """A jj/gh command failed, or a precondition was not met."""


_ANSI_RE = re.compile(r"\x1b\[[0-9;]*[a-zA-Z]")

# gh honours a user's `color: always` config even when its stdout is a pipe,
# which puts ANSI escapes inside --json output and breaks json.loads. Force
# plain output for every child, and strip escapes defensively on the way back.
_PLAIN_ENV = {"NO_COLOR": "1", "CLICOLOR": "0", "GH_FORCE_TTY": "", "GH_PAGER": "cat"}


async def _exec(argv: list[str], cwd: str = ".", check: bool = True,
                timeout: float = 600) -> dict:
    """Run a command, capture stdout/stderr, return {argv, code, out, err}."""
    if shutil.which(argv[0]) is None:
        raise JjShipError(f"binary not found on PATH: {argv[0]}")
    proc = await asyncio.create_subprocess_exec(
        *argv, cwd=cwd, env={**os.environ, **_PLAIN_ENV},
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
    )
    try:
        out, err = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        proc.kill()
        raise JjShipError(f"timed out after {timeout}s: {' '.join(argv)}")
    res = {
        "argv": argv,
        "code": proc.returncode,
        "out": _ANSI_RE.sub("", out.decode("utf-8", "replace")).strip(),
        "err": _ANSI_RE.sub("", err.decode("utf-8", "replace")).strip(),
    }
    if check and proc.returncode != 0:
        raise JjShipError(
            f"{' '.join(argv)} exited {proc.returncode}\n{res['err'] or res['out']}"
        )
    return res


async def _jj(args: list[str], repo: str = ".", **kw) -> dict:
    return await _exec([JJ_BIN, "--no-pager", *args], cwd=repo, **kw)


async def _gh(args: list[str], repo: str = ".", **kw) -> dict:
    return await _exec([GH_BIN, *args], cwd=repo, **kw)


async def _template(revset: str, template: str, repo: str = ".") -> str:
    r = await _jj(["log", "--no-graph", "-r", revset, "-T", template], repo=repo)
    return r["out"]


# --------------------------------------------------------------------------
# status
# --------------------------------------------------------------------------

async def status(repo: str = ".") -> dict:
    """Report the working copy: change id, description, dirty files, bookmarks."""
    st = await _jj(["status"], repo=repo)
    desc = await _template("@", 'description', repo=repo)
    change = await _template("@", 'change_id.short() ++ " " ++ commit_id.short()', repo=repo)
    empty = await _template("@", 'if(empty, "true", "false")', repo=repo)
    bookmarks = await _template("@", 'bookmarks.join(",")', repo=repo)
    parent_bookmarks = await _template("@-", 'bookmarks.join(",")', repo=repo)
    return {
        "change": change,
        "description": desc,
        "empty": empty == "true",
        "bookmarks": [b for b in bookmarks.split(",") if b],
        "parent_bookmarks": [b for b in parent_bookmarks.split(",") if b],
        "status": st["out"],
    }


# --------------------------------------------------------------------------
# commit / push
# --------------------------------------------------------------------------

async def commit(message: str, repo: str = ".", bookmark: Optional[str] = None,
                 new: bool = True, allow_empty: bool = False) -> dict:
    """Describe the working-copy change, point `bookmark` at it, and start a new change.

    jj has no staging area: whatever is in the working copy is already the
    change `@`. This describes it, moves/creates the bookmark, and (by default)
    leaves a fresh empty `@` on top so later edits do not silently amend it.
    """
    before = await status(repo=repo)
    if before["empty"] and not allow_empty:
        raise JjShipError(
            "working copy change is empty - nothing to commit "
            "(pass allow_empty=True to override)"
        )
    await _jj(["describe", "-m", message], repo=repo)
    committed = await _template("@", 'commit_id.short()', repo=repo)
    if bookmark:
        await _jj(["bookmark", "set", bookmark, "-r", "@"], repo=repo)
    if new:
        await _jj(["new"], repo=repo)
    return {
        "commit": committed,
        "message": message,
        "bookmark": bookmark,
        "files": before["status"],
    }


async def current_bookmark(repo: str = ".") -> Optional[str]:
    """The bookmark on `@` or, failing that, on `@-` (jj's usual post-commit shape)."""
    st = await status(repo=repo)
    for key in ("bookmarks", "parent_bookmarks"):
        if st[key]:
            return st[key][0]
    return None


async def push(repo: str = ".", bookmark: Optional[str] = None,
               remote: str = "origin", allow_new: bool = True) -> dict:
    """Push one bookmark to a git remote (`jj git push --bookmark ...`)."""
    bookmark = bookmark or await current_bookmark(repo=repo)
    if not bookmark:
        raise JjShipError("no bookmark on @ or @- - pass bookmark= explicitly")
    argv = ["git", "push", "--remote", remote, "--bookmark", bookmark]
    if allow_new:
        argv.append("--allow-new")
    r = await _jj(argv, repo=repo)
    return {"bookmark": bookmark, "remote": remote, "output": r["err"] or r["out"]}


# --------------------------------------------------------------------------
# pull requests
# --------------------------------------------------------------------------

async def find_pr(repo: str = ".", head: Optional[str] = None) -> Optional[dict]:
    """Return the open PR for `head` (default: the current bookmark), or None."""
    head = head or await current_bookmark(repo=repo)
    if not head:
        return None
    r = await _gh(["pr", "list", "--head", head, "--state", "all", "--limit", "5",
                   "--json", "number,url,state,title,headRefName"], repo=repo)
    prs = json.loads(r["out"] or "[]")
    open_prs = [p for p in prs if p.get("state") == "OPEN"]
    return (open_prs or prs or [None])[0]


async def open_pr(title: str, body: str = "", repo: str = ".",
                  head: Optional[str] = None, base: Optional[str] = None,
                  draft: bool = False) -> dict:
    """Open a PR for the pushed bookmark, or return the existing one (idempotent)."""
    head = head or await current_bookmark(repo=repo)
    if not head:
        raise JjShipError("no bookmark to open a PR for - pass head= explicitly")
    existing = await find_pr(repo=repo, head=head)
    if existing and existing.get("state") == "OPEN":
        return {**existing, "created": False}
    argv = ["pr", "create", "--head", head, "--title", title, "--body", body]
    if base:
        argv += ["--base", base]
    if draft:
        argv.append("--draft")
    r = await _gh(argv, repo=repo, check=False)
    if r["code"] != 0:
        again = await find_pr(repo=repo, head=head)
        if again:
            return {**again, "created": False}
        raise JjShipError(f"gh pr create failed: {r['err'] or r['out']}")
    url = r["out"].strip().splitlines()[-1]
    pr = await find_pr(repo=repo, head=head) or {}
    return {**pr, "url": url, "created": True}


def _pr_arg(pr: Optional[Any]) -> list[str]:
    return [str(pr)] if pr not in (None, "") else []


async def checks(pr: Optional[Any] = None, repo: str = ".") -> dict:
    """CI check runs for a PR: {state, checks:[{name,state,link}], raw}.

    `state` is one of pending | passing | failing | none.
    """
    r = await _gh(["pr", "checks", *_pr_arg(pr), "--json",
                   "name,state,bucket,link,description"], repo=repo, check=False)
    text = (r["err"] or "") + (r["out"] or "")
    if r["code"] != 0 and "no checks" in text.lower():
        return {"state": "none", "checks": [], "raw": text.strip()}
    if r["code"] != 0 and not r["out"]:
        raise JjShipError(f"gh pr checks failed: {text.strip()}")
    rows = json.loads(r["out"] or "[]")
    buckets = {row.get("bucket") for row in rows}
    if not rows:
        state = "none"
    elif "fail" in buckets or "cancel" in buckets:
        state = "failing"
    elif "pending" in buckets:
        state = "pending"
    else:
        state = "passing"
    return {"state": state, "checks": rows, "raw": text.strip()}


_THREAD_QUERY = """
query($owner:String!, $name:String!, $number:Int!) {
  repository(owner:$owner, name:$name) {
    pullRequest(number:$number) {
      reviewThreads(last:50) {
        nodes {
          id isResolved isOutdated path
          comments(last:20) { nodes { author { login } body createdAt url } }
        }
      }
    }
  }
}
"""


async def comments(pr: Optional[Any] = None, repo: str = ".",
                   unresolved_only: bool = True) -> dict:
    """PR conversation: issue comments, reviews, and (un)resolved review threads."""
    r = await _gh(["pr", "view", *_pr_arg(pr), "--json",
                   "number,url,title,state,comments,reviews,headRefName,baseRefName"],
                  repo=repo)
    view = json.loads(r["out"])
    owner_repo = await _gh(["repo", "view", "--json", "owner,name"], repo=repo)
    ident = json.loads(owner_repo["out"])
    threads: list[dict] = []
    g = await _gh(["api", "graphql",
                   "-F", f"owner={ident['owner']['login']}",
                   "-F", f"name={ident['name']}",
                   "-F", f"number={view['number']}",
                   "-f", f"query={_THREAD_QUERY}"], repo=repo, check=False)
    if g["code"] == 0 and g["out"]:
        nodes = (json.loads(g["out"])["data"]["repository"]["pullRequest"]
                 ["reviewThreads"]["nodes"])
        for node in nodes:
            if unresolved_only and node.get("isResolved"):
                continue
            threads.append({
                "id": node["id"],
                "path": node.get("path"),
                "resolved": node.get("isResolved"),
                "comments": [
                    {"author": (c.get("author") or {}).get("login"),
                     "body": c.get("body"), "url": c.get("url")}
                    for c in node["comments"]["nodes"]
                ],
            })
    return {
        "number": view["number"],
        "url": view["url"],
        "title": view["title"],
        "state": view["state"],
        "head": view.get("headRefName"),
        "base": view.get("baseRefName"),
        "comments": [{"author": (c.get("author") or {}).get("login"),
                      "body": c.get("body"), "url": c.get("url")}
                     for c in view.get("comments", [])],
        "reviews": [{"author": (rv.get("author") or {}).get("login"),
                     "state": rv.get("state"), "body": rv.get("body")}
                    for rv in view.get("reviews", []) if rv.get("body") or rv.get("state")],
        "threads": threads,
    }


async def watch(pr: Optional[Any] = None, repo: str = ".", interval: float = 30,
                max_polls: int = 40, verbose: bool = True) -> dict:
    """Poll a PR until its checks settle, reporting new comments as they arrive.

    Returns {checks, comments, polls, settled}. Never merges anything: this is a
    monitor, not a lander.
    """
    seen: set[str] = set()
    new_activity: list[dict] = []
    result: dict = {}
    for poll in range(1, int(max_polls) + 1):
        result = await checks(pr, repo=repo)
        convo = await comments(pr, repo=repo)
        for item in convo["comments"] + [c for t in convo["threads"] for c in t["comments"]]:
            key = item.get("url") or json.dumps(item, sort_keys=True)
            if key not in seen:
                seen.add(key)
                if poll > 1:
                    new_activity.append(item)
                    if verbose:
                        print(f"[new comment] {item.get('author')}: "
                              f"{(item.get('body') or '')[:200]}")
        if verbose:
            print(f"[poll {poll}] checks={result['state']} "
                  f"unresolved_threads={len(convo['threads'])}")
        if result["state"] in ("passing", "failing", "none"):
            return {"checks": result, "comments": convo, "polls": poll,
                    "settled": True, "new_activity": new_activity}
        await asyncio.sleep(interval)
    return {"checks": result, "comments": await comments(pr, repo=repo),
            "polls": max_polls, "settled": False, "new_activity": new_activity}


async def ship(message: str, bookmark: str, title: Optional[str] = None,
               body: str = "", repo: str = ".", base: Optional[str] = None,
               remote: str = "origin", draft: bool = False) -> dict:
    """commit -> push -> open PR, in one call. Returns each step's result."""
    c = await commit(message, repo=repo, bookmark=bookmark)
    p = await push(repo=repo, bookmark=bookmark, remote=remote)
    pr = await open_pr(title or message.splitlines()[0], body, repo=repo,
                       head=bookmark, base=base, draft=draft)
    return {"commit": c, "push": p, "pr": pr}


_ACTIONS = {
    "status": status, "commit": commit, "push": push, "open-pr": open_pr,
    "checks": checks, "comments": comments, "watch": watch, "ship": ship,
    "find-pr": find_pr,
}


async def run(action: str = "status", repo: str = ".", message: str = "",
              bookmark: str = "", title: str = "", body: str = "",
              base: str = "", pr: str = "", interval: float = 30,
              max_polls: int = 40) -> str:
    """Drive the jj -> push -> PR -> CI loop.

    action: status | commit | push | open-pr | find-pr | checks | comments | watch | ship
    Only the arguments an action needs are used; the result is returned as JSON.
    """
    kw: dict[str, Any] = {"repo": repo}
    if action in ("commit", "ship"):
        kw["message"] = message
    if action in ("commit", "push", "ship"):
        kw["bookmark"] = bookmark or None
    if action in ("open-pr", "ship"):
        kw["title"] = title or message.splitlines()[0] if (title or message) else ""
        kw["body"] = body
        kw["base"] = base or None
    if action in ("checks", "comments", "watch"):
        kw["pr"] = pr or None
    if action == "watch":
        kw["interval"] = interval
        kw["max_polls"] = max_polls
    if action == "ship":
        kw.pop("head", None)
    fn = _ACTIONS.get(action)
    if fn is None:
        raise JjShipError(f"unknown action {action!r}; try one of {sorted(_ACTIONS)}")
    out = await fn(**kw)
    return json.dumps(out, indent=2, default=str)
