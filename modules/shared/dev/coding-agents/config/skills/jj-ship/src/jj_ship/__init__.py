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
from pathlib import Path
from typing import Any, Optional

JJ_BIN = os.environ.get("JJ_BIN", "jj")
GH_BIN = os.environ.get("GH_BIN", "gh")

# Stamped into the PR body trailer; bump it when the attestation contract changes.
VERSION = "0.2.0"


class JjShipError(RuntimeError):
    """A jj/gh command failed, or a precondition was not met."""


_ANSI_RE = re.compile(r"\x1b\[[0-9;]*[a-zA-Z]")

# --------------------------------------------------------------------------
# markdown hard-wrap detection
# --------------------------------------------------------------------------
#
# GFM (what GitHub renders PR bodies as) treats a single "\n" inside a
# paragraph as a hard line break (<br>), unlike strict CommonMark's soft
# break. An LLM's habit of hard-wrapping prose at ~80-100 columns therefore
# renders as a paragraph visibly chopped into short lines on github.com. This
# bit real PRs (fayhealthinc/fay-ui#3732, #3743, #3745,
# fayhealthinc/fay-service#7207) and had to be manually rewrapped after the
# fact each time - catch it before `gh pr create` ever runs instead.

_STRUCTURAL_LINE_RE = re.compile(r"^\s*([-*+]\s|\d+[.)]\s|#{1,6}\s|>|\|)")
_SENTENCE_END_CHARS = ".:!?"
_TRAILING_CLOSERS = "\"'`)]"


def _ends_sentence(line: str) -> bool:
    """True if `line` looks like the end of a sentence/clause, not mid-wrap.

    Strips trailing closing quotes/parens/backticks first so both orderings
    ("...done.\"" and "...done)." ) are recognised.
    """
    s = line.rstrip()
    while s and s[-1] in _TRAILING_CLOSERS:
        s = s[:-1]
    return bool(s) and s[-1] in _SENTENCE_END_CHARS


def find_hard_wrapped_lines(body: str) -> list[tuple[int, str, str]]:
    """Flag every `\n` inside `body` that looks like an LLM hard-wrap rather
    than real markdown structure.

    Returns a list of `(line_number, line, next_line)` triples, 1-indexed by
    `line_number` (the line the suspicious break follows). A break is flagged
    when both lines are non-blank prose (not inside a fenced code block, not
    a list item/header/table row/blockquote on either side) and `line` does
    not end with sentence/clause-ending punctuation (`.`, `:`, `!`, `?`, or
    one of those immediately followed by a closing quote/paren/backtick).

    False positives are avoided by leaving fenced code blocks, list items,
    headers, table rows, and blockquotes untouched - those legitimately use
    single newlines as real structure.
    """
    lines = body.split("\n")
    hits: list[tuple[int, str, str]] = []
    in_fence = False
    for i in range(len(lines) - 1):
        line, nxt = lines[i], lines[i + 1]
        stripped = line.strip()
        if stripped.startswith("```") or stripped.startswith("~~~"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        if not line.strip() or not nxt.strip():
            continue
        if _STRUCTURAL_LINE_RE.match(line) or _STRUCTURAL_LINE_RE.match(nxt):
            continue
        if _ends_sentence(line):
            continue
        hits.append((i + 1, line, nxt))
    return hits


def normalize_markdown_body(body: str) -> str:
    """Fix what `find_hard_wrapped_lines` flags: join each hard-wrapped line
    pair into one line (a single space in place of the offending `\n`).

    Legitimate structure (blank-line paragraph breaks, lists, headers, code
    fences, tables, blockquotes) is left byte-for-byte untouched, since
    `find_hard_wrapped_lines` never flags a break there.
    """
    lines = body.split("\n")
    hit_lines = {h[0] - 1 for h in find_hard_wrapped_lines(body)}
    out: list[str] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        while i in hit_lines:
            line = line + " " + lines[i + 1].lstrip()
            i += 1
        out.append(line)
        i += 1
    return "\n".join(out)

# gh honours a user's `color: always` config even when its stdout is a pipe,
# which puts ANSI escapes inside --json output and breaks json.loads. Force
# plain output for every child, and strip escapes defensively on the way back.
_PLAIN_ENV = {"NO_COLOR": "1", "CLICOLOR": "0", "GH_FORCE_TTY": "", "GH_PAGER": "cat"}


# ---------------------------------------------------------------------------
# repo identity (GH_REPO)
# ---------------------------------------------------------------------------
# `gh` has to be told which repository it is about. Left to itself it infers
# that from the git remote of its cwd, which fails outright in the directory
# layout these agents actually work in: a `jj workspace add` directory has no
# `.git` at all, so every gh call there dies with "failed to run git: fatal:
# not a git repository". Confirmed live from a real workspace - `checks()`,
# `find_pr()`, `comments()` and therefore `open_pr()`/`ship()`/`watch()` all
# raised, while `current_bookmark()` worked because it shells out to `jj`.
# `_default_branch()` was worse than a raise: it swallows failure and returns
# None, silently disabling open_pr()'s "refusing to open a PR from the default
# branch" guard.
#
# So resolve owner/name ourselves and hand it to gh as GH_REPO in the
# subprocess env. GH_REPO rather than a `--repo` flag because `_gh` serves both
# `gh pr ...` (accepts --repo) and `gh api graphql` (does NOT), so a flag would
# have to know which subcommand it is running; the env var applies uniformly.
#
# This logic is deliberately DUPLICATED from the pr-watch skill's
# `pr_watch._resolve_slug` (see ../../pr-watch/src/pr_watch/__init__.py) rather
# than imported. jj-ship and pr-watch are separately packaged, independently
# installed skills with their own pyproject.toml; importing one from the other
# would make jj-ship unusable wherever pr-watch is not installed, to save ~30
# lines. Keep the two in sync by hand - the ordering decisions below are load
# bearing and are pinned by the same unit tests in both skills' test suites.

# Resolution shells out, so cache it per repo path: watch() polls up to 40
# times and the answer cannot change for a given path.
_SLUG_CACHE: dict[str, str] = {}

# Only GitHub remotes are usable by gh, and this must be strict: fay-service
# carries a `bitbucket` remote and a local `no-mistakes` remote alongside
# `origin`, so "take the first remote" would silently target Bitbucket.
_GITHUB_URL_RE = re.compile(
    r"^(?:git@github\.com:|ssh://git@github\.com/|https://(?:[^@/]+@)?github\.com/)"
    r"(?P<owner>[^/]+)/(?P<name>.+?)(?:\.git)?$")


def _parse_github_url(url: str) -> Optional[str]:
    match = _GITHUB_URL_RE.match(url.strip())
    return f"{match['owner']}/{match['name']}" if match else None


async def _resolve_slug(repo: str = ".") -> str:
    """`owner/name` for the GitHub repo that `repo` (a path) belongs to.

    Works in a plain git checkout, in a colocated jj repo, and - the case this
    exists for - in a `jj workspace add` directory with no `.git`. Raises
    rather than returning None: this runs before the gh subprocess, so it
    raises even for `check=False` callers, which is what stops a resolution
    failure from being swallowed into an empty result.
    """
    path = str(Path(repo).resolve())
    if path in _SLUG_CACHE:
        return _SLUG_CACHE[path]
    tried: list[str] = []
    r = await _exec(["git", "-C", path, "remote", "get-url", "origin"],
                    cwd=path, check=False)
    if r["code"] == 0 and (slug := _parse_github_url(r["out"])):
        _SLUG_CACHE[path] = slug
        return slug
    tried.append(f"git remote get-url origin -> {r['out'] or r['err']}")
    # jj's own view of the remotes: this is what still works in a workspace.
    r = await _exec([JJ_BIN, "--no-pager", "git", "remote", "list"],
                    cwd=path, check=False)
    if r["code"] == 0:
        for line in r["out"].splitlines():
            name, _, url = line.partition(" ")
            # `origin` specifically - see _GITHUB_URL_RE on why "the first
            # GitHub-looking remote" is not a safe rule here.
            if name == "origin" and (slug := _parse_github_url(url)):
                _SLUG_CACHE[path] = slug
                return slug
        tried.append(f"jj git remote list -> no GitHub `origin` in: {r['out']!r}")
    else:
        tried.append(f"jj git remote list -> {r['err']}")
    # An ambient GH_REPO is honoured only as a LAST resort: it used to be the
    # only reason a workspace ever worked, so ignoring it would regress - but
    # preferring it would let one exported GH_REPO silently mistarget every
    # other repo this process touches.
    override = os.environ.get("GH_REPO", "").strip()
    if override:
        _SLUG_CACHE[path] = override
        return override
    raise JjShipError(
        f"cannot determine the GitHub repo for {path!r}, so gh has nothing to "
        f"talk to. Set GH_REPO=owner/name, or point repo= at a checkout with a "
        f"GitHub `origin` remote. Tried: " + "; ".join(tried))


async def _exec(argv: list[str], cwd: str = ".", check: bool = True,
                timeout: float = 600, env: Optional[dict] = None) -> dict:
    """Run a command, capture stdout/stderr, return {argv, code, out, err}."""
    if shutil.which(argv[0]) is None:
        raise JjShipError(f"binary not found on PATH: {argv[0]}")
    proc = await asyncio.create_subprocess_exec(
        *argv, cwd=cwd, env={**os.environ, **_PLAIN_ENV, **(env or {})},
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
    # GH_REPO is what makes this work from a jj workspace: gh no longer has to
    # infer the repo from a git remote in cwd, which there is not one of.
    return await _exec([GH_BIN, *args], cwd=repo,
                       env={"GH_REPO": await _resolve_slug(repo)}, **kw)


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
    # `.map(|b| b.name())` rather than a bare `bookmarks.join(",")`: jj's default
    # formatting of a bookmark appends a `*` sync marker when the local bookmark
    # differs from its remote, so the bare template yields "my-branch*" as soon
    # as the bookmark has been pushed once and then moved. That string was fed
    # straight into `jj git push --bookmark`, which failed with "No such
    # bookmark: my-branch*" - so the SECOND push to an existing PR's bookmark
    # broke while the first one worked.
    names = 'bookmarks.map(|b| b.name()).join(",")'
    bookmarks = await _template("@", names, repo=repo)
    parent_bookmarks = await _template("@-", names, repo=repo)
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


async def _default_branch(repo: str = ".") -> Optional[str]:
    """The repo's default branch per `gh`, or None when it cannot be determined.

    `gh repo view` is the one subcommand here that does NOT honour GH_REPO - it
    takes the repository as a positional argument and otherwise insists on
    inferring it from cwd's git remote. So pass the resolved slug explicitly.
    Verified by hand from a jj workspace: with GH_REPO set but no argument it
    still fails with "failed to run git: fatal: not a git repository", and
    because this function swallows failure into None it did so silently -
    quietly disabling open_pr()'s "refusing to open a PR from the default
    branch" guard rather than reporting anything.
    """
    r = await _gh(["repo", "view", await _resolve_slug(repo), "--json",
                   "defaultBranchRef", "-q", ".defaultBranchRef.name"],
                  repo=repo, check=False)
    name = (r["out"] or "").strip()
    return name or None


# --------------------------------------------------------------------------
# attestations (contract and rationale: SKILL.md, "Attestations")
# --------------------------------------------------------------------------
# Unlike pr-watch's slug resolution (duplicated above, on purpose), attest is
# IMPORTED: a second copy of the diff hash would drift and read as tampering.


def _attest():
    try:
        import attest
    except ImportError as exc:
        raise JjShipError(
            "the `attest` skill is not installed, so a non-draft PR cannot be "
            "verified. Install it (it lives beside this skill in "
            "config/skills/attest) or open the PR as draft=True."
        ) from exc
    return attest


async def _verify_attestations(attestations: Optional[list[str]], repo: str,
                               base: Optional[str], head: str,
                               what: str) -> list[str]:
    """Verify `attestations` against the diff about to be pushed; return token ids.

    `base` defaults to the repo's default branch, matching what GitHub will diff
    the PR against.
    """
    attest = _attest()
    base = base or await _default_branch(repo=repo)
    if not base:
        raise JjShipError(
            f"cannot verify attestations for {what}: the PR's base branch could "
            f"not be determined, so there is no diff to bind them to. Pass "
            f"base='<branch>'.")
    try:
        sha = await attest.diff_sha(repo, base, head)
        payloads = attest.verify(attestations or [], sha)
    except attest.AttestError as exc:
        raise JjShipError(f"refusing {what}: {exc}") from exc
    return [attest.token_id(t) for t in (attestations or [])]


def attestation_trailer(token_ids: list[str]) -> str:
    """The `Shipped-With:` line appended to an attested PR body.

    It carries token IDs (sha256 prefixes), never the tokens: a token is a
    bearer credential. Its purpose is detection - a PR opened outside this path
    has no trailer, which is visible from GitHub alone.
    """
    return f"Shipped-With: jj_ship/{VERSION} attest=" + ",".join(token_ids)


def _with_trailer(body: str, token_ids: list[str]) -> str:
    trailer = attestation_trailer(token_ids)
    if trailer in body:
        return body
    return (body.rstrip() + "\n\n" + trailer + "\n") if body.strip() else trailer + "\n"


async def open_pr(title: str, body: str = "", repo: str = ".",
                  head: Optional[str] = None, base: Optional[str] = None,
                  draft: bool = False, skip_wrap_check: bool = False,
                  attestations: Optional[list[str]] = None) -> dict:
    """Open a PR for the pushed bookmark, or return the existing one (idempotent).

    A non-draft PR requires `attestations=[...]` carrying every claim in
    `attest.REQUIRED_CLAIMS` (`design_reviewed` and `eval_passed`), each bound
    to the diff being pushed; see the "attestations" section above. `draft=True`
    requires none.

    Before submitting, `body` is checked with `find_hard_wrapped_lines()` and
    rejected with `JjShipError` if it finds any hard-wrapped prose (see that
    function's docstring for why: GFM renders a single `\n` inside a
    paragraph as a real line break, not a soft one, so hand-wrapped text
    renders visibly broken on github.com). Call `normalize_markdown_body(body)`
    and retry rather than working around this.

    `skip_wrap_check=True` is an explicit opt-in escape hatch for a body that
    legitimately needs unusual line breaks the heuristic cannot tell from a
    hard-wrap; it is not a silent default and should be a deliberate,
    reasoned choice at the call site, not a routine one.
    """
    if not skip_wrap_check:
        wrapped = find_hard_wrapped_lines(body)
        if wrapped:
            offenders = "\n".join(
                f"  line {n}: {line!r}\n         -> {nxt!r}"
                for n, line, nxt in wrapped
            )
            raise JjShipError(
                "PR body has hard-wrapped prose that GitHub will render as "
                "literal line breaks (GFM treats a single '\\n' inside a "
                "paragraph as <br>, not a soft break):\n"
                f"{offenders}\n"
                "Call jj_ship.normalize_markdown_body(body) and retry - or, "
                "if this break is deliberate, pass skip_wrap_check=True."
            )
    head = head or await current_bookmark(repo=repo)
    if not head:
        raise JjShipError("no bookmark to open a PR for - pass head= explicitly")
    # `current_bookmark` reads the bookmark on `@` or `@-`, so after a
    # `jj new main` (the usual "start something else" move) it resolves to the
    # DEFAULT branch and `gh pr create --head main` fails with the unhelpful
    # "GraphQL: No commits between main and main". Catch it here and say what
    # to do about it.
    default = await _default_branch(repo=repo)
    if default and head == default and not base:
        raise JjShipError(
            f"refusing to open a PR from {head!r}, the repo's default branch - "
            f"the working copy has probably moved off the feature bookmark "
            f"(e.g. after `jj new {default}`). Pass head='<bookmark>' explicitly.")
    # Before the idempotent early return, so a second call is held to the same bar.
    if not draft:
        token_ids = await _verify_attestations(
            attestations, repo, base, head, "to open a non-draft PR")
        body = _with_trailer(body, token_ids)
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


async def mark_ready(pr: Optional[Any] = None, repo: str = ".",
                     head: Optional[str] = None, base: Optional[str] = None,
                     attestations: Optional[list[str]] = None) -> dict:
    """Take a draft PR out of draft, which requires the same attestations as
    opening a non-draft one: draft -> ready is the moment a human is asked to
    read it, and that is what the claims are about.

    The `Shipped-With:` trailer is appended to the existing body here rather
    than at draft time, because a draft's diff is expected to keep moving and a
    trailer naming a stale token would be worse than none.
    """
    view = await _gh(["pr", "view", *_pr_arg(pr), "--json",
                      "number,url,body,headRefName,baseRefName,isDraft"], repo=repo)
    info = json.loads(view["out"])
    token_ids = await _verify_attestations(
        attestations, repo, base or info.get("baseRefName"),
        head or info.get("headRefName"), "to mark a PR ready for review")
    number = str(info["number"])
    body = _with_trailer(info.get("body") or "", token_ids)
    await _gh(["pr", "edit", number, "--body", body], repo=repo)
    r = await _gh(["pr", "ready", number], repo=repo, check=False)
    if r["code"] != 0 and "already" not in (r["err"] + r["out"]).lower():
        raise JjShipError(f"gh pr ready failed: {r['err'] or r['out']}")
    return {"number": info["number"], "url": info["url"], "ready": True,
            "attestations": token_ids}


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
    # _THREAD_QUERY needs owner/name explicitly, and _resolve_slug already had
    # to work them out to make gh usable at all - so reuse that rather than
    # spend another `gh repo view` round trip on every call.
    slug_owner, _, slug_name = (await _resolve_slug(repo)).partition("/")
    threads: list[dict] = []
    g = await _gh(["api", "graphql",
                   "-F", f"owner={slug_owner}",
                   "-F", f"name={slug_name}",
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
               remote: str = "origin", draft: bool = False,
               skip_wrap_check: bool = False, *,
               attestations: Optional[list[str]] = None) -> dict:
    """commit -> push -> open PR, in one call. Returns each step's result.

    The signature is unchanged for every existing caller: `attestations` is
    keyword-only and defaults to None, which only raises on the non-draft path
    (`open_pr` does the raising). `ship(..., draft=True)` still needs nothing,
    so a mid-flight agent can keep drafting while it learns the new contract.

    Inherits `open_pr()`'s hard-wrap check on `body` (see its docstring) -
    `skip_wrap_check` is threaded through for the same rare opt-in escape
    hatch, not a routine default.
    """
    c = await commit(message, repo=repo, bookmark=bookmark)
    p = await push(repo=repo, bookmark=bookmark, remote=remote)
    pr = await open_pr(title or message.splitlines()[0], body, repo=repo,
                       head=bookmark, base=base, draft=draft,
                       skip_wrap_check=skip_wrap_check,
                       attestations=attestations)
    return {"commit": c, "push": p, "pr": pr}


_ACTIONS = {
    "status": status, "commit": commit, "push": push, "open-pr": open_pr,
    "checks": checks, "comments": comments, "watch": watch, "ship": ship,
    "find-pr": find_pr, "mark-ready": mark_ready,
}


async def run(action: str = "status", repo: str = ".", message: str = "",
              bookmark: str = "", title: str = "", body: str = "",
              base: str = "", pr: str = "", interval: float = 30,
              max_polls: int = 40, attestations: str = "") -> str:
    """Drive the jj -> push -> PR -> CI loop.

    action: status | commit | push | open-pr | find-pr | checks | comments |
            watch | ship | mark-ready
    Only the arguments an action needs are used; the result is returned as JSON.
    `attestations` is a comma-separated list of tokens from the attest skill,
    required for a non-draft open-pr / for mark-ready.
    """
    tokens = [t.strip() for t in attestations.split(",") if t.strip()]
    kw: dict[str, Any] = {"repo": repo}
    if action in ("commit", "ship"):
        kw["message"] = message
    if action in ("commit", "push", "ship"):
        kw["bookmark"] = bookmark or None
    if action in ("open-pr", "ship"):
        kw["title"] = title or message.splitlines()[0] if (title or message) else ""
        kw["body"] = body
        kw["base"] = base or None
    if action in ("open-pr", "ship", "mark-ready"):
        kw["attestations"] = tokens or None
    if action in ("checks", "comments", "watch", "mark-ready"):
        kw["pr"] = pr or None
    if action == "mark-ready":
        kw["base"] = base or None
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
