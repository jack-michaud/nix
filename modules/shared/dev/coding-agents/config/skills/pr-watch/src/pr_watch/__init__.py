"""pr-watch: wake this agent when a watched PR gets comments or CI fails, after a quiet window.

`watch()` registers a PR and an RLM heartbeat; every heartbeat turn calls
`poll()`, which reports only activity that has been QUIET for `quiet_seconds`
(default 180). A burst of review comments therefore produces one wake-up after
the reviewer stops typing, not one per comment. Failing CI check-runs are
folded into the same activity stream (see `_check_runs`), because GitHub
Actions failures do not post PR comments on their own - a watcher that only
looked at comments would sit there reporting "quiet" while CI was red, which
is exactly what happened live before this was added.

Merge/close detection rides the same stream (see `_lifecycle_items`): a
watcher that only looked at comments would poll a merged PR for the rest of its
`max_hours` window and never say the one thing the caller was waiting for.
Observing a merge or an unmerged close ends the watch - a terminal PR cannot
produce more review activity - and `serve()` returns a summary naming the
terminal state so the caller can trigger downstream work (e.g. evaluation on
merge) from it.

Every newly observed transition is also appended to a durable JSONL event log
(~/.prime/agent/pr-watch/events.jsonl, overridable with PR_WATCH_EVENTS).
Notifications are only as durable as the session that owns them: on 2026-08-13
a worker interruption killed ten of eleven live watchers, taking their
unreported activity with them. An append-only log makes a PR's lifecycle
reconstructible after the fact by anyone, which is what makes
evaluation-on-merge deterministic instead of dependent on some session being
awake at the moment GitHub flipped the bit. Logging is best-effort by
construction: `_log_event` swallows its own failures, because losing a log line
must never kill a watch.

State lives in ~/.prime/agent/pr-watch/state.json so it survives a kernel
restart; the heartbeat lives in the session, so it stops when the session ends.
State (and the log) are keyed by the repo SLUG, not the local checkout path -
see `_slug_key`.
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
from typing import Any, Optional, Sequence

GH_BIN = os.environ.get("GH_BIN", "gh")
STATE_PATH = Path(os.environ.get(
    "PR_WATCH_STATE", str(Path.home() / ".prime/agent/pr-watch/state.json")))
EVENTS_PATH = Path(os.environ.get(
    "PR_WATCH_EVENTS", str(Path.home() / ".prime/agent/pr-watch/events.jsonl")))
DEFAULT_QUIET_SECONDS = 180.0

# Bumped whenever a watch ENTRY gains a field or an ownership rule changes.
# Stamped into every entry at arm time and compared on every poll, because a
# long-lived kernel that imported an older `pr_watch` keeps running it: an agent
# re-armed a watch to pick up session fingerprints, the already-imported module
# had no `_session_fingerprint`, so the entry was written with `session: None`
# AND under a third ledger key - the agent believed it was covered and was not.
# `importlib.reload(pr_watch)` fixes it, but a false belief in coverage has to be
# DETECTED rather than documented, so poll() reports a mismatch in both
# directions: older entries than this module mean re-arm them, newer entries than
# this module mean THIS kernel is the stale one.
ENTRY_VERSION = 3

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


# Item kinds that describe the PR itself rather than something somebody wrote.
# They have no body to sign, so `ignore_signatures` must never apply to them
# (see `_has_ignored_signature`): a merge that got filtered out as "one of my
# own signed comments" is exactly the notification nobody would ever miss on
# purpose.
LIFECYCLE_KINDS = frozenset({
    "merged", "closed_unmerged", "ready_for_review", "converted_to_draft"})

# Kinds after which there is nothing left to watch: GitHub will not add review
# activity to a merged or closed PR, so a watcher that keeps polling one is
# burning its whole window on a dead PR.
TERMINAL_KINDS = frozenset({"merged", "closed_unmerged"})


# ----------------------------------------------------------- event log ----

# `owner/name`, the only shape a log entry's `repo` may take. Checked on write
# rather than trusted, because this log is meant to become the TRIGGER for
# automated evaluation: a line naming something that is not a repository would
# make an eval fire against nothing, and the failure would read as data rather
# than as a bug. Deliberately narrow - exactly one slash, no path separators
# either side - so a local checkout path (the pre-slug key format) is rejected.
_SLUG_RE = re.compile(r"^[A-Za-z0-9._-]+/[A-Za-z0-9._-]+$")


def _events_path() -> Path:
    """Where to append events, re-read from the environment on every call.

    Not just the module-level `EVENTS_PATH` constant: that is resolved at import
    time, so a test (or a caller) that sets `PR_WATCH_EVENTS` afterwards would
    still write the real log. This module's own tests hit exactly that - five
    fixture lines landed in the production log, in a file whose whole purpose is
    to be trustworthy enough to trigger automation off.
    """
    return Path(os.environ.get("PR_WATCH_EVENTS") or EVENTS_PATH)


def _log_event(slug: str, pr: Any, item: dict) -> None:
    """Append one observed transition to the durable JSONL event log.

    Why a log at all, when the point of this module is notifications: a
    notification only exists inside the session that receives it. When a
    worker interruption killed ten of eleven live watchers on 2026-08-13,
    everything they had seen died with them, and no later session could
    reconstruct even whether a PR had merged. The log is append-only and
    owner-agnostic, so any process - a different agent, a script, a human -
    can replay a PR's lifecycle afterwards. That is what makes
    evaluation-on-merge deterministic rather than contingent on someone being
    awake when GitHub flipped the bit.

    Atomic-ish on purpose: one `open(..., "a")` and exactly one `write` of a
    single line, which POSIX keeps intact for concurrent appenders at this
    size - hence no lock, so a watcher never blocks another to log. Every
    failure is swallowed: a full disk, a read-only home, a bad path must not
    take down a watch that is otherwise working.
    """
    if not _SLUG_RE.match(str(slug or "")):
        # Refuse rather than write a line nothing downstream could act on. Not
        # raising: the caller is a poll loop, and a malformed slug is a bug to
        # find in the log's ABSENCE, not a reason to kill a working watch.
        return
    try:
        path = _events_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps({
            "at": datetime.now(timezone.utc).isoformat(),
            "repo": slug,
            "pr": pr,
            "kind": item.get("kind"),
            "id": item.get("id"),
            "author": item.get("author"),
            "url": item.get("url"),
        }, default=str) + "\n"
        with open(path, "a") as handle:
            handle.write(line)
    except Exception:
        pass


# ---------------------------------------------------------------- state ----

# A sub-agent kernel's RLM_SESSION_DIR basename looks like `sub-4685289e`,
# while a top-level session's is the session UUID. That distinction is the only
# cheap, local way to tell whether
# PRIME_AGENT_INTERNAL_DAEMON_WORKER_ACTIVE_SESSION_ID names THIS session or an
# ancestor: the daemon exports it into the environment, and a spawned sub-agent
# INHERITS the value, so inside a child it names the parent. Verified live -
# in a sub-agent kernel whose own active session id was 31b2e6874fba, that
# variable read 1d0df30d0658, its parent's.
_SUBAGENT_SESSION_DIR_RE = re.compile(r"^sub-[0-9a-f]+$")

# How an owner id was established, worst-case first. `inherited` means the id
# came from the ambient daemon variable inside a sub-agent kernel, so it
# probably names an ANCESTOR; `default` means nothing identified this session at
# all. Neither may be trusted to authorise a WRITE to somebody's seen-set - see
# `_require_unambiguous_owner` and poll()'s read-only fallback.
AMBIGUOUS_OWNER_SOURCES = frozenset({"inherited", "default"})


def _owner_provenance(owner: Optional[str] = None) -> tuple[str, str]:
    """`(owner id, how it was established)`.

    Resolution order is deliberately UNCHANGED from the version that wrote the
    state file: explicit argument, `PR_WATCH_OWNER`, the ambient daemon session
    id, then the session-dir name. Reordering this to prefer `RLM_SESSION_DIR`
    - the obvious-looking fix for the mis-attribution below - would orphan every
    watch already on disk: all 57 live entries are owned by 12-hex daemon
    session ids (e.g. `1d0df30d0658`), and a session-dir name is `sub-4685289e`,
    so not one of them would match its owner's next poll. Silently losing every
    live watcher is a worse failure than the one being fixed.

    What changes is that the answer now carries its PROVENANCE, so a caller can
    refuse to destroy state it cannot prove is its own.
    """
    if owner:
        return owner, "explicit"
    if env := os.environ.get("PR_WATCH_OWNER"):
        return env, "PR_WATCH_OWNER"
    session_dir = os.environ.get("RLM_SESSION_DIR")
    dir_name = Path(session_dir).name if session_dir else ""
    daemon = os.environ.get("PRIME_AGENT_INTERNAL_DAEMON_WORKER_ACTIVE_SESSION_ID")
    if daemon:
        # In a sub-agent kernel this value was inherited from an ancestor, so it
        # identifies that ancestor's ledger, not this session's.
        return daemon, ("inherited" if _SUBAGENT_SESSION_DIR_RE.match(dir_name)
                        else "daemon")
    if dir_name:
        return dir_name, "session_dir"
    return "default", "default"


def _session_fingerprint() -> Optional[str]:
    """A unique, stable id for THIS session, or None if it cannot be known.

    `RLM_SESSION_DIR` is per-session by construction - `.../<uuid>` for a
    top-level session, `.../<uuid>/sub-<hex>` for a sub-agent - so unlike the
    ambient daemon session id it is NOT shared with an ancestor. That is what
    makes it usable as the thing captured at ARM time, which is the only way two
    sessions with identical ambient environments can ever be told apart in the
    ledger: an owner id re-derived at poll time is by definition the same string
    for both of them, so no amount of read-side filtering can distinguish them,
    and the mis-attribution runs in BOTH directions - each session can drain the
    other's queue, and the symptom on the victim's side is silence, which looks
    exactly like a quiet PR.

    Not used as the `owner` id itself: every one of the 57 watches already on
    disk is owned by a 12-hex daemon session id, so switching identities would
    orphan all of them. It is stored ALONGSIDE the owner as `session`, and
    entries that carry it are matched on it in preference to the owner.
    """
    explicit = os.environ.get("PR_WATCH_SESSION")
    if explicit:
        return explicit
    session_dir = os.environ.get("RLM_SESSION_DIR")
    return str(Path(session_dir)) if session_dir else None


def _entry_is_mine(entry: dict, mine: str,
                   my_session: Optional[str]) -> tuple[bool, bool]:
    """`(belongs to me, provably so)` for one watch entry.

    Prefers the arm-time `session` fingerprint, which is unambiguous in both
    directions. Falls back to the owner id for entries written before
    fingerprints existed - that comparison is the ambiguous one, so it reports
    `provably=False` and the caller must not destroy anything on its strength
    alone.
    """
    session = entry.get("session")
    if session and my_session:
        return session == my_session, True
    return entry.get("owner", mine) == mine, False


def _owner(owner: Optional[str] = None) -> str:
    """Who a watch belongs to: the AGENT SESSION that owns it.

    Watchers in different sessions must keep independent seen-sets, or the first
    one to mark an item seen silently swallows the other's notification. The
    watcher CHILD inherits its parent's owner (watch_via_child passes it in), so
    a parent's ack() still reaches its own blocked child.

    See `_owner_provenance` for how the id is established, and why callers that
    MUTATE another session's seen-set must check the provenance first.
    """
    return _owner_provenance(owner)[0]


def _require_unambiguous_owner(action: str, owner: Optional[str] = None) -> str:
    """The owner id, or a loud failure when it cannot be established.

    For destructive operations only (`ack`, `unwatch(all=True)`): guessing an
    owner and being wrong is worse than an error, because the damage is silent
    and permanent - the mis-attributed write marks another session's items seen,
    and those ids never appear as `fresh` again, so its agent is never woken.
    """
    resolved, provenance = _owner_provenance(owner)
    if provenance in AMBIGUOUS_OWNER_SOURCES:
        raise PrWatchError(
            f"refusing to {action}: this session's owner id cannot be "
            f"established unambiguously (best guess {resolved!r}, established "
            f"by {provenance!r}). In a sub-agent kernel the ambient daemon "
            f"session id names an ANCESTOR, so acting on it would silence "
            f"another session's notifications. Pass owner=<id> explicitly, or "
            f"export PR_WATCH_OWNER.")
    return resolved


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
    """The LEGACY, path-keyed state key. Kept only so `_migrated_key` can find
    and move entries written by older versions - never use it for new writes."""
    return f"{Path(repo).resolve()}#{pr}@{_owner(owner)}"


def _slug_key(slug: str, pr: Any, owner: Optional[str] = None) -> str:
    """The state key: repo SLUG, not local path.

    Keying on the checkout path made the same PR watched from a `jj workspace
    add` directory and from the canonical clone into two independent ledgers
    with divergent seen-sets, so an item reported to one watcher stayed
    unreported for the other - which is how ~24 hours of review comments on
    fay-ui#3733 went unseen. The PR is the thing being watched, and the PR is
    identified by owner/name#number, so that is what the key says.
    """
    return f"{slug}#{pr}@{_owner(owner)}"


def _merge_entries(old: dict, new: dict) -> dict:
    """Fold a legacy path-keyed entry into its slug-keyed successor.

    UNION of the seen-sets, deliberately, and never the intersection or a fresh
    empty one: dropping either side replays that side's history as new activity,
    and intersecting swallows everything only one side had reported. Live ledgers
    really do carry both forms for one PR - fay-service#7295, #7292, #7297 and
    fay-ui#3733 each had a path-form AND a slug-form key when this was written -
    so this merge decides whether those PRs replay, go silent, or behave.

    A `session` fingerprint on either side is kept (`new` wins on conflict, being
    the more recent arm), because an entry that loses its fingerprint downgrades
    to ambiguous-owner matching and becomes read-only for its own owner.
    """
    merged = {**old, **new}
    merged["seen"] = sorted(set(old.get("seen", [])) | set(new.get("seen", [])))
    if session := (new.get("session") or old.get("session")):
        merged["session"] = session
    return merged


def _migrate_in_place(state: dict, legacy: str, key: str) -> bool:
    if legacy == key or legacy not in state.get("watches", {}):
        return False
    watches = state["watches"]
    watches[key] = _merge_entries(watches.pop(legacy), watches.get(key, {}))
    return True


async def _converge_keys() -> None:
    """Move every legacy path-keyed entry onto its slug key.

    Runs at the top of `poll()`, which is the one place that already walks the
    whole file, so the migration converges for watches this session never
    touches by name. An entry whose checkout has since been deleted cannot be
    resolved to a slug; it is left as-is rather than dropped, since a stale key
    is recoverable and a deleted seen-set is not.
    """
    state = _load()
    moves: dict[str, str] = {}
    for key, entry in list(state.get("watches", {}).items()):
        # The test is "is the key's head a valid owner/name slug", NOT "does it
        # look like a path". An earlier key format used the checkout's BASENAME
        # (`fay-service-ret227#7292@...`), which is neither a slug nor an
        # absolute path, so a startswith("/") guard skipped it and left a
        # duplicate ledger for that PR alive - observed live, and it survived
        # convergence with `session: None` next to the canonical fingerprinted
        # entry, which is the worst of both worlds.
        if "#" not in key or not entry.get("repo"):
            continue
        if _SLUG_RE.match(key.split("#")[0]):
            continue   # already canonical
        try:
            # allow_ambient=False: this rewrites entries belonging to OTHER
            # sessions, and an ambient GH_REPO would re-point their watch at this
            # session's repo under their own owner id.
            slug = await _resolve_slug(entry["repo"], allow_ambient=False)
        except PrWatchError:
            # A deleted checkout (or one that can only be named by this
            # process's environment) cannot be converged safely. Leave the entry
            # exactly as it is: a stale key is recoverable, a dropped seen-set is
            # not.
            continue
        moves[key] = _slug_key(slug, entry.get("pr"), entry.get("owner"))
    if not moves:
        return
    with _locked():
        state = _load()
        # A list, not any(): any() short-circuits and would skip later moves.
        if [1 for legacy, key in moves.items() if _migrate_in_place(state, legacy, key)]:
            _save(state)


async def _migrated_key(repo: str, pr: Any, owner: Optional[str] = None) -> str:
    """The slug-keyed key for this watch, migrating a path-keyed one if present.

    Migration happens here rather than in `_load()` because `_load()` is sync
    and the slug can only come from `gh`/`git`/`jj`; doing it lazily on every
    read-modify-write path converges the file without ever dropping an entry.
    """
    key = _slug_key(await _resolve_slug(repo), pr, owner)
    legacy = _key(repo, pr, owner)
    with _locked():
        state = _load()
        if _migrate_in_place(state, legacy, key):
            _save(state)
    return key


# --------------------------------------------------- repo identity (GH_REPO)
# ----
# Every gh call has to be told which repository it is about. Left to itself, gh
# infers that from the git remote of its cwd - which fails outright in the
# directory layout these agents actually work in: a `jj workspace add`
# directory has no `.git` at all, so gh dies with "failed to run git: fatal:
# not a git repository". That failure used to surface as `serve()` raising the
# instant it armed, i.e. a watcher that reported as armed while never polling
# once. Four real watchers were lost that way before this was fixed.
#
# So resolve the owner/name ourselves and hand it to gh as GH_REPO in the
# subprocess env. GH_REPO rather than a `--repo` flag because `_gh` serves both
# `gh pr ...` (takes --repo) and `gh api graphql` (does NOT take --repo), so a
# per-subcommand flag would have to know which is which; the env var applies
# uniformly and gh honours it for every subcommand.

# Resolution shells out to jj/git, so cache it per repo path: serve() polls
# every 30s for up to 6 hours and the answer cannot change for a given path.
_SLUG_CACHE: dict[str, str] = {}

# Paths whose slug came from the ambient `GH_REPO` rather than from the checkout
# itself. Tracked separately because that provenance is only acceptable for gh
# calls about the CALLER's own repo: `GH_REPO` names whatever the POLLING kernel
# exports, so accepting it while rewriting somebody else's ledger entry would
# re-point their watch at this session's repo - a webflow PR #399 silently
# converged to `fayhealthinc/fay-service#399@<their owner>`, polled against the
# wrong repository, in their name. Caught in review before it shipped.
_AMBIENT_SLUG_PATHS: set[str] = set()

# Only GitHub remotes are usable by gh, and this must be strict about it:
# fay-service carries a `bitbucket` remote and a local `no-mistakes` remote
# alongside `origin`, so "take the first remote" would silently point the
# watcher at Bitbucket.
_GITHUB_URL_RE = re.compile(
    r"^(?:git@github\.com:|ssh://git@github\.com/|https://(?:[^@/]+@)?github\.com/)"
    r"(?P<owner>[^/]+)/(?P<name>.+?)(?:\.git)?$")


async def _run(binary: str, args: list[str], cwd: str) -> tuple[int, str, str]:
    """Run a binary, returning (rc, stdout, stderr) with colour stripped.

    Both preconditions are checked here rather than left to the OS, because this
    function's contract is "returns a status, never raises": a missing binary and
    a missing `cwd` both make `asyncio.create_subprocess_exec` throw
    `FileNotFoundError`, which is an OSError and NOT a `PrWatchError`, so it flies
    straight through every `except PrWatchError` in this module. That took the
    whole fleet down on 2026-08-13: one watch pointed at a deleted checkout
    (`/private/tmp/fay-webflow-custom-code`), and `poll()`'s pass over all 54
    entries died on it before reading a single item - for every session at once,
    with silence as the symptom.
    """
    if shutil.which(binary) is None:
        return 127, "", f"binary not found on PATH: {binary}"
    if not os.path.isdir(cwd):
        return 127, "", f"cwd does not exist: {cwd}"
    proc = await asyncio.create_subprocess_exec(
        binary, *args, cwd=cwd, env={**os.environ, **_PLAIN_ENV},
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    out, err = await proc.communicate()
    return (proc.returncode,
            _ANSI_RE.sub("", out.decode("utf-8", "replace")).strip(),
            _ANSI_RE.sub("", err.decode("utf-8", "replace")).strip())


def _parse_github_url(url: str) -> Optional[str]:
    match = _GITHUB_URL_RE.match(url.strip())
    return f"{match['owner']}/{match['name']}" if match else None


async def _resolve_slug(repo: str, allow_ambient: bool = True) -> str:
    """`owner/name` for the GitHub repo that `repo` (a path) belongs to.

    Works in a plain git checkout, in a colocated jj repo, and - the case this
    exists for - in a `jj workspace add` directory that has no `.git`. Raises
    loudly rather than returning None: a watcher that cannot name its repo must
    fail at arming time, not poll silently forever against nothing.

    `allow_ambient=False` refuses the `GH_REPO` last resort, so the answer must
    have come from the checkout itself. Pass it whenever the answer will be
    written into a ledger entry this session does not own - see
    `_AMBIENT_SLUG_PATHS`.
    """
    path = str(Path(repo).resolve())
    if path in _SLUG_CACHE:
        if not allow_ambient and path in _AMBIENT_SLUG_PATHS:
            raise PrWatchError(
                f"refusing an ambient slug for {path!r}: it was resolved from "
                f"this process's GH_REPO, not from the checkout, so it names "
                f"this session's repo rather than that watch's.")
        return _SLUG_CACHE[path]
    tried: list[str] = []
    rc, out, err = await _run("git", ["-C", path, "remote", "get-url", "origin"], cwd=path)
    if rc == 0 and (slug := _parse_github_url(out)):
        _SLUG_CACHE[path] = slug
        return slug
    tried.append(f"git remote get-url origin -> {out or err or f'rc={rc}'}")
    # jj's own view of the remotes: this is what still works inside a workspace.
    rc, out, err = await _run("jj", ["git", "remote", "list"], cwd=path)
    if rc == 0:
        for line in out.splitlines():
            name, _, url = line.partition(" ")
            # `origin` specifically - see _GITHUB_URL_RE's comment on why
            # scanning for "the first GitHub-looking remote" is not enough here.
            if name == "origin" and (slug := _parse_github_url(url)):
                _SLUG_CACHE[path] = slug
                return slug
        tried.append(f"jj git remote list -> no GitHub `origin` in: {out!r}")
    else:
        tried.append(f"jj git remote list -> {err or f'rc={rc}'}")
    # An ambient GH_REPO is honoured only as a LAST resort, not first: it used
    # to be the only reason a workspace ever worked, so dropping it would be a
    # regression - but preferring it would make one exported GH_REPO silently
    # mistarget every other repo this process watches.
    override = os.environ.get("GH_REPO", "").strip()
    if override:
        _SLUG_CACHE[path] = override
        _AMBIENT_SLUG_PATHS.add(path)
        if not allow_ambient:
            raise PrWatchError(
                f"cannot determine the GitHub repo for {path!r} from the "
                f"checkout itself, and this caller refuses the ambient GH_REPO "
                f"({override!r}) because the answer would be written into a "
                f"watch entry that may belong to another session.")
        return override
    raise PrWatchError(
        f"cannot determine the GitHub repo for {path!r}, so gh has nothing to "
        f"talk to. Set GH_REPO=owner/name, or point repo= at a checkout with a "
        f"GitHub `origin` remote. Tried: " + "; ".join(tried))


# ------------------------------------------------------------------ gh ----

async def _gh(args: list[str], repo: str, check: bool = True) -> str:
    if shutil.which(GH_BIN) is None:
        raise PrWatchError(f"binary not found on PATH: {GH_BIN}")
    # Same landmine as `_run`: a deleted `cwd` makes create_subprocess_exec raise
    # FileNotFoundError, which no caller's `except PrWatchError` would catch.
    # Raise the module's own error type so a dead checkout degrades to "this one
    # watch failed" instead of killing the poll for every other watch too.
    if not os.path.isdir(repo):
        raise PrWatchError(
            f"cannot run gh for this watch: its checkout is gone ({repo!r}). "
            f"The watch is left in place - `unwatch()` it deliberately if the "
            f"repo is really finished with.")
    # GH_REPO is what makes this work from a jj workspace: gh no longer has to
    # infer the repo from a git remote in cwd, which there is not one of.
    env = {**os.environ, **_PLAIN_ENV, "GH_REPO": await _resolve_slug(repo)}
    proc = await asyncio.create_subprocess_exec(
        GH_BIN, *args, cwd=repo, env=env,
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    out, err = await proc.communicate()
    out_s = _ANSI_RE.sub("", out.decode("utf-8", "replace")).strip()
    err_s = _ANSI_RE.sub("", err.decode("utf-8", "replace")).strip()
    if check and proc.returncode != 0:
        raise PrWatchError(f"gh {' '.join(args)} exited {proc.returncode}: {err_s or out_s}")
    return out_s


# One query for both review threads and the draft transitions, because they
# come from the same PR object - a second `gh api graphql` round trip per poll
# would double the cost of every poll for two fields. The draft transitions are
# read as timeline EVENTS (each with its own node id) rather than derived from
# the current `isDraft` boolean: a boolean gives no id to dedup on, so a PR
# flipped to draft and back and to draft again would report at most one of
# those transitions.
_THREAD_QUERY = """
query($owner:String!, $name:String!, $number:Int!) {
  repository(owner:$owner, name:$name) {
    pullRequest(number:$number) {
      reviewThreads(last:50) {
        nodes { id isResolved path
          comments(last:20) { nodes { author { login } body createdAt url } } }
      }
      timelineItems(last:20,
                    itemTypes:[READY_FOR_REVIEW_EVENT, CONVERT_TO_DRAFT_EVENT]) {
        nodes { __typename
          ... on ReadyForReviewEvent { id createdAt actor { login } }
          ... on ConvertToDraftEvent { id createdAt actor { login } } }
      }
    }
  }
}
"""

_DRAFT_EVENT_KINDS = {"ReadyForReviewEvent": "ready_for_review",
                      "ConvertToDraftEvent": "converted_to_draft"}


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


def _lifecycle_items(view: dict) -> list[dict]:
    """Merge / unmerged-close items derived from `gh pr view`'s own fields.

    Field spellings are gh's, checked against `gh pr view --json` rather than
    guessed: `state` is OPEN/CLOSED/MERGED, the merge timestamp is `mergedAt`
    (there is no `merged` field), and `mergeCommit` is an object - `{"oid":
    "<sha>"}` - or null while the PR is open.

    The ids are stable and derived from the event, not from the poll, so the
    same merge observed by ten polls (or ten watchers) dedups to one item.
    """
    items: list[dict] = []
    merged_at = view.get("mergedAt")
    state = (view.get("state") or "").upper()
    if merged_at:
        sha = (view.get("mergeCommit") or {}).get("oid") or ""
        items.append({
            "kind": "merged", "id": f"merged:{sha or merged_at}",
            "author": None,
            "body": f"merged as {sha or 'an unreported commit'}",
            "url": view.get("url"), "at": _ts(merged_at)})
    elif state == "CLOSED":
        items.append({
            "kind": "closed_unmerged", "id": f"closed:{view.get('number')}",
            "author": None, "body": "closed without merging",
            "url": view.get("url"), "at": _ts(view.get("closedAt"))})
    return items


async def _activity(repo: str, pr: Any) -> list[dict]:
    """Every comment-ish, CI-failure or lifecycle event on a PR, newest last,
    as flat dicts with an id."""
    raw = await _gh(["pr", "view", str(pr), "--json",
                     "number,url,title,comments,reviews,headRefOid,"
                     "state,isDraft,mergedAt,mergeCommit,closedAt"], repo=repo)
    view = json.loads(raw)
    items: list[dict] = _lifecycle_items(view)
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
    # _THREAD_QUERY and the check-run API both need owner/name explicitly, and
    # _resolve_slug already had to work them out to make gh usable at all -
    # so reuse that instead of a second `gh repo view` round trip per poll.
    slug_owner, _, slug_name = (await _resolve_slug(repo)).partition("/")
    graph = await _gh(["api", "graphql",
                       "-F", f"owner={slug_owner}",
                       "-F", f"name={slug_name}",
                       "-F", f"number={view['number']}",
                       "-f", f"query={_THREAD_QUERY}"], repo=repo, check=False)
    if graph:
        try:
            pull = json.loads(graph)["data"]["repository"]["pullRequest"]
        except (KeyError, TypeError, json.JSONDecodeError):
            pull = {}
        nodes = ((pull.get("reviewThreads") or {}).get("nodes") or [])
        for event in ((pull.get("timelineItems") or {}).get("nodes") or []):
            kind = _DRAFT_EVENT_KINDS.get(event.get("__typename"))
            if not kind or not event.get("id"):
                continue
            items.append({
                "kind": kind, "id": f"draft:{event['id']}",
                "author": (event.get("actor") or {}).get("login"),
                "body": kind.replace("_", " "),
                "url": view.get("url"), "at": _ts(event.get("createdAt"))})
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
    for run in await _check_run_failures(repo, slug_owner, slug_name,
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


def _has_ignored_signature(item: dict, ignore_signatures: Sequence[str]) -> bool:
    """Whether the body's last non-empty line is `-- <sig>` for a listed signature.

    Signatures, not authors: every agent here authenticates to GitHub as the
    human `jack-michaud`, so filtering on `item["author"]` would drop his real
    review comments too. Last line only, so a comment quoting someone else's
    signature still notifies.
    """
    if not ignore_signatures:
        return False
    # A lifecycle item (merged / closed / draft flip) is GitHub's own event, not
    # something a persona wrote, so no signature list may suppress it. Belt and
    # braces with the `or ""` below, which already keeps a None body from being
    # read as a signature: a merge carries no body at all, and swallowing a
    # merge notification would defeat the reason merge detection exists.
    if item.get("kind") in LIFECYCLE_KINDS:
        return False
    body = item.get("body") or ""
    lines = [line for line in body.splitlines() if line.strip()]
    if not lines:
        return False
    last = lines[-1].strip()
    return any(last == f"-- {sig}" for sig in ignore_signatures)


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
    # Resolve up front, even when seed=False skips the first _activity() call:
    # an unresolvable repo must blow up HERE, at arming time, while someone is
    # looking at the result - not later inside a poll loop that swallows errors.
    slug = await _resolve_slug(repo)
    key = await _migrated_key(repo, pr)
    items = await _activity(repo, pr) if seed else []
    # DISTINCT ids, not len(items): several items can share one id (a comment
    # that is also the first comment of a review thread carries the same url), so
    # reporting len(items) as "seeded" overstated the seen-set by one or more -
    # 11 reported against 10 stored, live - and made the resulting single
    # re-report look like a notification bug rather than an off-by-one in the
    # report. `seeded` now counts what was actually stored.
    seeded_ids = {i["id"] for i in items if i.get("id")}
    with _locked():
        state = _load()
        existing = state["watches"].get(key, {})
        state["watches"][key] = {
            "repo": repo, "slug": slug, "pr": pr, "quiet_seconds": quiet_seconds,
            "owner": _owner(),
            # Captured HERE, at arm time, from the arming session's own
            # environment - the one moment when this session's identity is not
            # in doubt. See `_session_fingerprint`.
            "session": _session_fingerprint(),
            "entry_version": ENTRY_VERSION,
            # Union with whatever a migrated path-keyed entry already had, so
            # re-watching from a different checkout does not replay the backlog.
            "seen": sorted(set(existing.get("seen", [])) | seeded_ids),
            "added_at": datetime.now(timezone.utc).isoformat(),
        }
        _save(state)
    hb = await _ensure_heartbeat(interval) if heartbeat else None
    return {"watching": key, "seeded": len(seeded_ids), "items_seen": len(items),
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


async def poll(mark_seen: bool = True, owner: Optional[str] = None) -> str:
    """Report watched-PR activity that has been quiet for the debounce window.

    New activity is held until nothing newer has arrived for `quiet_seconds`
    (default 180), so one burst of review comments produces one wake-up.

    A merge or an unmerged close is reported IMMEDIATELY (no debounce - nothing
    further can arrive on a terminal PR) and the watch is then dropped, so the
    heartbeat stops paying for polls of a dead PR.

    READ-ONLY WHEN THE OWNER IS A GUESS. `poll()` normally MUTATES the ledger it
    reports from - it marks reported items seen and drops terminal watches - so
    polling under a mis-attributed owner id does not merely read another
    session's queue, it drains it: those ids never appear as `fresh` again, and
    the rightful owner is never woken. That happened live on 2026-08-13, when a
    sub-agent's `poll()` resolved to its ORCHESTRATOR's session id (the ambient
    daemon variable is inherited by child kernels) and matched six watches
    belonging to that orchestrator.

    The fault runs BOTH ways - the orchestrator's own poll can equally drain the
    sub-agent's watches, and on that side the symptom is silence, which is
    indistinguishable from a quiet PR. So ownership is settled by the arm-time
    `session` fingerprint where one exists (`_entry_is_mine`), and a legacy entry
    matched only by the ambiguous owner id is reported READ-ONLY: nothing marked
    seen, no terminal watch dropped, and a banner saying so on the first line. A
    read cannot corrupt anyone. Pass `owner=<id>` / export `PR_WATCH_OWNER`, or
    simply re-arm the watch from this session, to poll authoritatively.
    """
    await _converge_keys()
    state = _load()
    mine, provenance = _owner_provenance(owner)
    my_session = _session_fingerprint()
    ambiguous = provenance in AMBIGUOUS_OWNER_SOURCES
    now = datetime.now(timezone.utc).timestamp()
    ready_lines: list[str] = []
    holding: list[str] = []
    finished: list[str] = []
    guessed = 0   # entries claimed only on the strength of an ambiguous owner id
    wrote = False   # nothing is saved unless an entry was provably writable
    older_entries = 0   # written by an older pr_watch than this one
    newer_entries = 0   # written by a NEWER one, i.e. THIS kernel is stale
    for key, entry in list(state["watches"].items()):
        is_mine, proven = _entry_is_mine(entry, mine, my_session)
        if not is_mine:
            continue   # another session's watcher reports to its own agent
        # Writes are per-entry, not per-poll: an entry carrying an arm-time
        # fingerprint is provably this session's and can be marked seen even when
        # the ambient owner id is untrustworthy, while a legacy entry matched only
        # by that owner id is reported read-only.
        may_write = mark_seen and (proven or not ambiguous)
        if not proven and ambiguous:
            guessed += 1
        written_by = entry.get("entry_version", 0)
        if written_by < ENTRY_VERSION:
            older_entries += 1
        elif written_by > ENTRY_VERSION:
            newer_entries += 1
        try:
            items = await _activity(entry["repo"], entry["pr"])
        except PrWatchError as exc:
            holding.append(f"{key}: poll failed ({exc})")
            continue
        slug = entry.get("slug") or key.split("#")[0]
        seen = set(entry.get("seen", []))
        fresh = [i for i in items if i.get("id") and i["id"] not in seen]
        for i in fresh:
            _log_event(slug, entry.get("pr"), i)
        terminal = next((i for i in items if i["kind"] in TERMINAL_KINDS), None)
        if not fresh and not terminal:
            continue
        window = float(entry.get("quiet_seconds", DEFAULT_QUIET_SECONDS))
        if fresh and terminal is None:
            newest = max(i["at"] for i in fresh)
            quiet_for = now - newest
            if quiet_for < window:
                holding.append(
                    f"{key}: {len(fresh)} new item(s), still settling "
                    f"({int(window - quiet_for)}s of quiet left)")
                continue
        if fresh:
            ready_lines.append(f"READY {key} - {len(fresh)} new item(s):")
            for i in fresh:
                where = f" [{i.get('path')}]" if i.get("path") else ""
                ready_lines.append(
                    f"  - {i['kind']}{where} by {i.get('author')}: "
                    f"{(i.get('body') or '').strip()}\n    {i.get('url')}")
        if terminal is not None:
            # Drop the watch, not just mark it seen: the PR is terminal, so
            # every future poll would cost a gh round trip to learn nothing.
            # Dropping is a destructive write, so a read-only poll reports the
            # terminal state and leaves the entry for its real owner to clear.
            finished.append(
                f"{key}: {terminal['kind']} - "
                + ("left in place (unproven ownership, read-only)" if not may_write
                   else "no longer watching")
                + f" ({terminal.get('body')})")
            if may_write:
                state["watches"].pop(key, None)
                wrote = True
            continue
        if may_write:
            entry["seen"] = sorted(seen | {i["id"] for i in fresh})
            wrote = True
    if wrote:
        _save(state)
    ready_lines.extend(finished)
    # The banner leads, so a human or agent reading this can never mistake a
    # read-only report for a poll that consumed its queue.
    banner = ([f"pr-watch: {guessed} watch(es) reported READ-ONLY - owner "
               f"{mine!r} was established by {provenance!r} and those entries "
               f"carry no arm-time session fingerprint, so they may belong to "
               f"another session. Nothing was marked seen and no watch was "
               f"dropped for them. Re-arm them from this session, pass "
               f"owner=<id>, or export PR_WATCH_OWNER to poll authoritatively."]
              if guessed else [])
    # Version skew is reported in BOTH directions, because the dangerous one is
    # invisible from inside the stale kernel: an agent that re-armed a watch from
    # a long-lived kernel running an older module wrote an entry with no
    # fingerprint and a third ledger key, and believed it was covered.
    if older_entries:
        banner.append(
            f"pr-watch: {older_entries} watch(es) were armed by an OLDER "
            f"pr_watch (entry_version < {ENTRY_VERSION}). Re-arm them to pick up "
            f"this version's ownership fields - and if you are re-arming from a "
            f"long-lived kernel, `importlib.reload(pr_watch)` FIRST, or the "
            f"already-imported old module writes the old shape again.")
    if newer_entries:
        banner.append(
            f"pr-watch: {newer_entries} watch(es) were armed by a NEWER pr_watch "
            f"than the one running here (entry_version > {ENTRY_VERSION}), so "
            f"THIS kernel is the stale one. Run "
            f"`import importlib; importlib.reload(pr_watch)` before trusting "
            f"anything above, including this report.")
    if not state["watches"] and not ready_lines:
        return "\n".join(banner + ["pr-watch: nothing is being watched."])
    if not ready_lines:
        return "\n".join(banner + ["pr-watch: nothing ready."
                                   + ("\n  " + "\n  ".join(holding) if holding else "")])
    return "\n".join(banner + ready_lines
                     + (["", "still settling:"] + holding if holding else []))


async def ack(repo: str = ".", pr: Optional[Any] = None, all: bool = False,
              owner: Optional[str] = None) -> str:
    """Mark everything currently on a PR as seen, without reporting it.

    Call this right after you post a reply. The agent comments through the same
    GitHub account as its human, so its OWN reply would otherwise read as new
    activity and wake it up to answer itself.

    Acts only on watches this session can PROVE are its own - an arm-time
    `session` fingerprint, or an owner id whose provenance is unambiguous. ack is
    pure destruction (it overwrites a seen-set with "everything currently on the
    PR"), so under a mis-attributed owner `ack(all=True)` would silence every
    notification another session was waiting for. Unlike `poll()` there is no
    useful read-only version of it, so unprovable entries are skipped, and a call
    that can prove nothing raises rather than guessing.
    """
    mine, provenance = _owner_provenance(owner)
    my_session = _session_fingerprint()
    ambiguous = provenance in AMBIGUOUS_OWNER_SOURCES
    state = _load()

    def _provably_mine(entry: dict) -> bool:
        is_mine, proven = _entry_is_mine(entry, mine, my_session)
        return is_mine and (proven or not ambiguous)

    if all:
        keys = [k for k, v in state["watches"].items() if _provably_mine(v)]
        if not keys and ambiguous:
            _require_unambiguous_owner("ack every watch", owner)
    else:
        try:
            keys = [await _migrated_key(repo, pr, owner if not ambiguous else None)]
        except PrWatchError:
            # A deleted checkout cannot be converged to a slug key, but the entry
            # still exists under its legacy key and must remain ackable - found by
            # this module's own dead-checkout test.
            keys = [_key(repo, pr, owner if not ambiguous else None)]
        target = state["watches"].get(keys[0])
        if target is not None and not _provably_mine(target):
            raise PrWatchError(
                f"refusing to ack {keys[0]!r}: it cannot be proved to belong to "
                f"this session (owner {mine!r} established by {provenance!r}, "
                f"entry session {target.get('session')!r}). Acking it would "
                f"silence another session's notifications.")
    current: dict[str, list] = {}
    unreachable: list[str] = []
    for key in keys:
        entry = state["watches"].get(key)
        if entry is None:
            continue
        try:
            current[key] = sorted(
                {i["id"] for i in await _activity(entry["repo"], entry["pr"])
                 if i.get("id")})
        except PrWatchError as exc:
            # One unreachable watch (deleted checkout, gh hiccup) must not abort
            # the ack of every other watch - the same abort-on-one-bad-entry shape
            # that took down poll() for the whole fleet.
            unreachable.append(f"{key} ({exc})")
    with _locked():
        state = _load()
        for key, ids in current.items():
            state["watches"].setdefault(key, {})["seen"] = ids
        _save(state)
    acked = len(current)
    note = (f" {len(unreachable)} watch(es) could not be reached and were left "
            f"untouched: " + "; ".join(unreachable)) if unreachable else ""
    return f"pr-watch: acknowledged current activity on {acked} watch(es).{note}"


async def watching() -> str:
    """List the watched PRs and their debounce windows."""
    state = _load()
    if not state["watches"]:
        return "pr-watch: nothing is being watched."
    return "\n".join(
        f"{k}  quiet={v.get('quiet_seconds')}s  seen={len(v.get('seen', []))}"
        for k, v in state["watches"].items())


async def unwatch(repo: str = ".", pr: Optional[Any] = None, all: bool = False,
                  owner: Optional[str] = None) -> str:
    """Stop watching one PR, or every PR of THIS session (`all=True`) and cancel
    the heartbeat.

    `all=True` used to clear `state["watches"]` outright - every session's
    watches, not just the caller's - which contradicts both this module's
    per-session isolation and the rest of these functions, and would delete
    dozens of other agents' live ledgers in one call (57 entries across 6 owners
    on this machine when the bug was found). It now clears only the watches this
    session can prove are its own (an arm-time fingerprint, or an unambiguous
    owner id), and refuses rather than guessing when it can prove none.
    """
    state = _load()
    if all:
        mine, provenance = _owner_provenance(owner)
        my_session = _session_fingerprint()
        ambiguous = provenance in AMBIGUOUS_OWNER_SOURCES
        dropped = []
        for k, v in state["watches"].items():
            is_mine, proven = _entry_is_mine(v, mine, my_session)
            if is_mine and (proven or not ambiguous):
                dropped.append(k)
        if not dropped and ambiguous:
            _require_unambiguous_owner("unwatch every PR", owner)
        for key in dropped:
            state["watches"].pop(key, None)
        _save(state)
        try:
            import rlm_heartbeat
            jobs = await rlm_heartbeat.list()
            entries = jobs.get("heartbeats", jobs) if isinstance(jobs, dict) else jobs
            for job in entries or []:
                if isinstance(job, dict) and job.get("label") == HEARTBEAT_LABEL:
                    await rlm_heartbeat.delete(job["id"])
        except Exception as exc:  # heartbeat teardown must not lose the state write
            return (f"pr-watch: cleared {len(dropped)} watch(es) owned by "
                    f"{mine!r}; other sessions' watches were left alone; "
                    f"heartbeat cleanup failed: {exc}")
        return (f"pr-watch: cleared {len(dropped)} watch(es) owned by {mine!r} "
                f"and cancelled the heartbeat. Other sessions' watches were "
                f"left alone.")
    # A dead checkout must remain REMOVABLE: `_migrated_key` needs a slug, which a
    # deleted directory cannot supply, so fall back to the legacy path key. This is
    # the one deliberate way to clear an entry whose repo is gone - the automatic
    # paths all leave it alone, because dropping someone's seen-set is
    # unrecoverable while a stale key is not.
    try:
        key = await _migrated_key(repo, pr)
    except PrWatchError:
        key = _key(repo, pr)
    state = _load()   # _migrated_key may have rewritten the file under us
    removed = state["watches"].pop(key, None)
    if removed is None:
        # Also try the other form, so `unwatch` works whichever shape the entry
        # happens to be in.
        for other in [k for k in state["watches"]
                      if k.endswith(f"#{pr}@{_owner()}")
                      and (Path(state["watches"][k].get("repo", "")).resolve()
                           == Path(repo).resolve())]:
            removed = state["watches"].pop(other, None)
            key = other
            break
    _save(state)
    return (f"pr-watch: no longer watching {key}" if removed is not None
            else f"pr-watch: no watch matched {key!r}; nothing removed")


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
                notify_name: Optional[str] = None,
                ignore_signatures: Sequence[str] = (),
                session: Optional[str] = None) -> str:
    """Block here, polling a PR, and message an agent when activity settles.

    Meant to be the ONLY call a watcher sub-agent makes: the loop runs inside
    this one tool call, so idle polling consumes no model tokens. Returns when
    `max_hours` elapses so the caller can re-arm, OR as soon as the PR reaches a
    terminal state (merged / closed unmerged), in which case the returned string
    names that state and says not to re-arm - a merged PR cannot produce more
    review activity, and watchers used to spend their entire window polling one.

    Every newly observed item is also appended to the JSONL event log (see
    `_log_event`), so the PR's lifecycle survives this session's death.

    `notify_role`/`notify_name` default to messaging this watcher's own
    PARENT, which is correct for a `watch_via_child()`-spawned watcher (the
    caller IS its parent). A watcher spawned on someone else's behalf - see
    `watch_via_sibling()`, where the watcher's parent and the original caller
    are different sessions - must override these to reach the right session,
    e.g. `notify_role="sibling", notify_name=<original caller>`.

    `ignore_signatures` keeps a watcher from waking its owner with the owner's
    own signed comments; see `_has_ignored_signature`.

    `session` is the OWNER's session fingerprint, not the watcher's: a watcher
    child is a different session from the agent it reports to, so it must record
    whose ledger this is rather than its own (`watch_via_child` passes both
    `owner` and `session` down). Left None, and with no `owner` given either,
    the watcher is arming for itself and its own fingerprint is stored.
    """
    import time

    repo = str(Path(repo).resolve())
    if pr is None:
        raise PrWatchError("pass pr=<number>")
    # The seen-set lives in the shared state file, not just in memory: this
    # loop blocks for hours, so the parent agent's own ack() (after it posts a
    # reply of its own) has no other way to reach it - a steering message would
    # queue behind the very cell it needs to influence.
    # Same reason as watch(): fail loudly before entering a loop whose
    # per-poll error handling is (deliberately) silent, so a watcher can never
    # again report as armed while being incapable of polling at all.
    slug = await _resolve_slug(repo)
    # Slug-keyed, and migrating a path-keyed predecessor if one exists, so a
    # watcher armed from a jj workspace shares one seen-set with the same PR
    # watched from the canonical clone (see _slug_key).
    key = await _migrated_key(repo, pr, owner)
    seeded = sorted({i["id"] for i in await _activity(repo, pr) if i.get("id")}) if seed else None
    with _locked():
        state = _load()
        entry = state["watches"].setdefault(key, {"repo": repo, "slug": slug,
                                                 "pr": pr,
                                                 "owner": _owner(owner)})
        entry["slug"] = slug
        # `owner` given means this watch belongs to another session (the one that
        # spawned this watcher), so its fingerprint must come from the caller;
        # inventing this watcher's own would make the real owner's poll skip the
        # very entry it is waiting on.
        fingerprint = session if session or owner else _session_fingerprint()
        if fingerprint:
            entry["session"] = fingerprint
        entry["entry_version"] = ENTRY_VERSION
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
            e = st["watches"].setdefault(key, {"repo": repo, "slug": slug,
                                              "pr": pr,
                                              "owner": _owner(owner), "seen": []})
            e["seen"] = sorted(set(e.get("seen", [])) | ids)
            _save(st)
    deadline = time.time() + max_hours * 3600.0
    sent = errors = 0
    pending: dict[str, dict] = {}

    def _finished(terminal: dict, reported: bool) -> str:
        # `reported` distinguishes "this call announced the terminal state" from
        # "it was already in the seen-set when we got here" (e.g. seed=True on an
        # already-merged PR). Both stop the watch; only one of them notified.
        return (f"pr-watch serve finished: {slug}#{pr} is {terminal['kind']} "
                f"({terminal.get('body')}); {sent} notification(s), "
                f"{errors} poll error(s). "
                f"{'Reported in the final message' if reported else 'Already seen when this watch started, nothing reported'}"
                f" - terminal state, do NOT re-arm.")

    while time.time() < deadline:
        await asyncio.sleep(poll_seconds)
        try:
            items = await _activity(repo, pr)
        except PrWatchError:
            errors += 1
            continue
        seen = _seen_now()
        for i in items:
            if i.get("id") and i["id"] not in seen and i["id"] not in pending:
                # Log at first observation, before any filtering: the log is a
                # record of what happened on the PR, not of what this watcher
                # chose to report, so a signature-suppressed comment belongs in
                # it too.
                _log_event(slug, pr, i)
        # A merged or closed PR is the end of the watch. Bypass the debounce
        # window for it - the window exists to let a burst of typing settle, and
        # nothing more can arrive on a terminal PR - and report whatever else is
        # pending in the same, final message.
        terminal = next((i for i in items if i["kind"] in TERMINAL_KINDS), None)
        ignored: set = set()
        for i in items:
            if i.get("id") and i["id"] not in seen:
                if _has_ignored_signature(i, ignore_signatures):
                    ignored.add(i["id"])
                    continue
                pending[i["id"]] = i
        if ignored:
            _mark(ignored)
            seen |= ignored
        for gone in [k for k in pending if k in seen]:   # acked while pending
            pending.pop(gone)
        if not pending:
            # Terminal but already seen: e.g. seed=True on a PR that had
            # already merged. Nothing to notify, but there is also nothing left
            # to watch, so stop instead of burning the whole max_hours window.
            if terminal is not None:
                return _finished(terminal, reported=False)
            continue
        if terminal is None:
            newest = max(i["at"] for i in pending.values())
            if time.time() - newest < quiet_seconds:
                continue  # still arriving - hold the whole burst
        header = (f"pr-watch: {len(pending)} new item(s) on {slug}#{pr} "
                  + (f"(TERMINAL: {terminal['kind']}, reported immediately):"
                     if terminal is not None
                     else f"(quiet for {int(quiet_seconds)}s):"))
        lines = [header]
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
        if terminal is not None:
            return _finished(terminal, reported=True)
    return (f"pr-watch serve finished after {max_hours}h: "
            f"{sent} notification(s), {errors} poll error(s). Re-arm to keep watching.")


CHILD_TASK = """You are a PR watcher. Make exactly ONE tool call and nothing else:

    import pr_watch
    print(await pr_watch.serve(repo={repo!r}, pr={pr!r}, quiet_seconds={quiet}, \
                               poll_seconds={poll}, max_hours={hours},
                               owner={owner!r}, ignore_signatures={ignore!r},
                               session={session!r}))

That call BLOCKS for up to {hours} hours by design - this is expected, not a
hang. It polls the PR inside that single cell and messages your parent itself
whenever comment activity settles, so you must NOT poll it, print progress, or
send any message of your own. When the call finally returns, call it again with
the same arguments unless your parent told you to stop."""


async def watch_via_child(repo: str = ".", pr: Optional[Any] = None,
                          quiet_seconds: float = DEFAULT_QUIET_SECONDS,
                          poll_seconds: float = 30.0, max_hours: float = 6.0,
                          name: str = "pr-watcher",
                          ignore_signatures: Sequence[str] = ()) -> dict:
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
    # Both identities travel with the task: `owner` keeps the legacy ledger key
    # matching this session, `session` is the unambiguous fingerprint that lets
    # this session's poll() recognise the entry as its own even when another
    # session shares its ambient owner id.
    task = CHILD_TASK.format(repo=str(Path(repo).resolve()), pr=pr,
                             quiet=quiet_seconds, poll=poll_seconds,
                             hours=max_hours, owner=_owner(),
                             ignore=tuple(ignore_signatures),
                             session=_session_fingerprint())
    handle = await rlm.run(task, name=name)
    return {"child": getattr(handle, "name", name), "owner": _owner(),
            "session": _session_fingerprint(),
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
                               notify_name={caller!r},
                               ignore_signatures={ignore!r},
                               session={session!r}))

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
                            name: str = "pr-watcher",
                            ignore_signatures: Sequence[str] = ()) -> dict:
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
                               hours=max_hours, owner=_owner(), caller=caller,
                               ignore=tuple(ignore_signatures),
                               session=_session_fingerprint())
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
