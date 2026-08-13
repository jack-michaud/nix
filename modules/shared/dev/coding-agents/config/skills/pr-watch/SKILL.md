---
name: pr-watch
description: Wake this agent when a watched GitHub PR receives comments, reviews, unresolved review threads, a failing CI check-run, a lifecycle change (merged, closed unmerged, ready for review, converted to draft), or a merge-conflict transition (the base branch moved and the PR now conflicts, or a prior conflict just resolved), after a quiet debounce window (default 3 minutes) so a burst of activity produces one wake-up instead of many. Watching is free while the PR is quiet - a sub-agent blocks in a single tool call and pushes the notification. Every observed transition is also appended to a durable JSONL event log, so a PR's lifecycle is reconstructible even if the watching session dies. Use after opening a PR that a human will review, when you need to know the moment a PR merges (e.g. to trigger evaluation on merge), when a PR's base branch is likely to keep moving and you need to know if it drifts into conflict, or when asked to keep an eye on a PR and respond to feedback.
compatibility: Requires an authenticated `gh` and runs inside the agent kernel (it spawns a sub-agent, or registers an RLM heartbeat).
---

# pr-watch

Opening a PR is not the end of the work - the review comes minutes or hours
later, and CI can go red without anyone commenting about it (GitHub Actions
failures do not post PR comments on their own). This watches the PR and wakes
the session when comments land OR a check-run fails, so they get answered
instead of forgotten - without paying model tokens for the silence in between.

```python
await pr_watch.watch(repo="/path/to/repo", pr=2)   # arms the heartbeat too
await pr_watch.poll()                              # what the heartbeat runs
await pr_watch.ack(repo="/path/to/repo", pr=2)     # after you post a reply
await pr_watch.watching()
await pr_watch.unwatch(repo="/path/to/repo", pr=2)
await pr_watch.unwatch(all=True)                   # also cancels the heartbeat
```

## Three ways to be woken (prefer the child)

Prefer `watch_via_child()` by default; use `watch_via_sibling()` only when
you are already at the RLM max recursion depth; otherwise use `watch()`
(heartbeat) when a PR may sit quiet long enough that you'd rather not hold
a sub-agent open, or when other constraints apply.

| | `watch_via_child()` | `watch_via_sibling()` | `watch()` |
|---|---|---|---|
| Mechanism | a sub-agent blocking in `serve()` | a sub-agent blocking in `serve()`, spawned by YOUR PARENT | an RLM heartbeat + `poll()` |
| Token cost while quiet | **zero** - the loop runs inside ONE tool call | **zero**, same as `watch_via_child()` | one model turn per interval, forever |
| Cost to start | one turn | one turn (yours) + your parent's next turn | one turn |
| Latency | `poll_seconds` (default 30s) after the quiet window | same, plus however long until your parent acts on the request | up to the heartbeat interval |
| Lifetime | until `max_hours` elapses, then re-arm | until `max_hours` elapses, then re-arm | until the session ends |
| Requires | RLM depth headroom to spawn a child | nothing - works even at max RLM recursion depth | nothing |

```python
await pr_watch.watch_via_child(repo="/path/to/repo", pr=2)   # push, free while idle
```

Stop a watcher with `await pr_watch.stop_watchers("pr-watcher")` rather than
hand-rolling the lookup: an `RLMSubagent` exposes `session_name`, and its `name`
attribute is `None`, so filtering on `name` silently matches nothing and leaves
the child running.

The child makes exactly one call - `await pr_watch.serve(...)` - which blocks for
hours, polls `gh` inside that single cell, and calls `agent_message.send(...,
receiver_role="parent")` from inside the still-running cell when a burst settles.
Polling therefore costs no tokens at all: an idle watcher is a sleeping Python
loop, not a recurring conversation. Never poll that child; it reports on its own.

### `watch_via_sibling()` - use only at the RLM recursion depth cap

`watch_via_child()` spawns a CHILD (depth+1) and relies on that child being
able to message `receiver_role="parent"` straight back to the session that
spawned it. That breaks down when the calling session is ALREADY at max RLM
recursion depth: `rlm.run` has no depth left to spawn into, so
`watch_via_child()` cannot be called at all - and calling `serve()` directly in
the caller's own kernel just blocks the very session that needed to stay free
(and its "message parent when settled" side effect fires to the CALLER's
parent, not back to the caller, since the caller isn't that parent's child in
this picture - it just invoked a blocking function directly). That is a real
bug that has been hit live.

**Use `watch_via_child()` normally; use `watch_via_sibling()` instead only
when you are already at max RLM recursion depth and cannot spawn a child.**

```python
await pr_watch.watch_via_sibling(repo="/path/to/repo", pr=2)
```

There is no "spawn a sibling of myself" primitive exposed to a running
session's own code - only to whatever orchestrated that session in the first
place, which from inside the session is reachable only as "my parent". So
`watch_via_sibling()` sends its OWN PARENT a message asking it to spawn a
watcher child of ITS OWN: a child spawned by the parent lands at the *caller's*
depth (a true sibling), not one below it. The spawned watcher then calls
`pr_watch.serve(..., notify_role="sibling", notify_name=<the original caller>)`
so it reports settled activity directly back to the original caller via
`agent_message.send(..., receiver_role="sibling")` - never through the
parent's own turn, so the parent does not end up making decisions that were
the watcher's own job. This makes the spawn step slightly less immediate than
`watch_via_child()` (it depends on the parent acting on the request on its
next turn), but the calling session itself never blocks and is notified
directly, which is the whole point.

## The debounce is the point

`poll()` never reports activity that is still arriving. New items are held until
nothing newer has landed for `quiet_seconds` (default 180), so a reviewer leaving
eight inline comments over two minutes wakes the agent **once**, with all eight,
after they stop - instead of eight interrupted turns racing a half-written
review. Items reported once are marked seen and never repeat.

- **`ack()` after replying.** The agent comments through the same GitHub account
  as its human, so its own reply reads as new activity and would wake it up to
  answer itself. `poll()` marks what it reports; `ack()` covers what you posted.
- **`ignore_signatures=` for comments your own family posts.** An orchestrator
  that posts disclosure comments on the PRs it watches wakes itself once per
  comment (twice in one day on fay-service#7256 and #7257).
  `serve()`, `watch_via_child()` and `watch_via_sibling()` take
  `ignore_signatures=["Kalinda", "Bashaarat"]`: an item is skipped (silently,
  but marked seen) when its body's LAST non-empty line is exactly `-- <name>`,
  which is how these agents sign. Last line only, so a comment that *quotes*
  another agent's signature still notifies; case-sensitive; items with no body
  (a failing check-run) are never filtered. Default `()` - omit it and nothing
  changes.
  **Never "improve" this into author filtering:** every agent here
  authenticates to GitHub as the human `jack-michaud`, so matching on the
  author would silently swallow his real review comments.

```python
await pr_watch.watch_via_child(repo="/path/to/repo", pr=2,
                               ignore_signatures=["Kalinda"])
```

- The heartbeat path runs every 3 minutes in `follow_up` mode, so it never
  interrupts work in progress. It is the fallback for when no sub-agent should
  be held open; `watch_via_child` is the default choice.
- Watched: issue comments, review bodies, comments on **unresolved** review
  threads (a resolved thread needs no answer - resolution state only exists in
  the GraphQL API, so that half goes through `gh api graphql`), and **failing
  CI check-runs** on the PR's head commit (`gh api
  repos/<owner>/<repo>/commits/<sha>/check-runs`, paginated at `per_page=100` -
  the default page size silently truncates on repos with many checks, which is
  how a real CI failure went unreported before this existed). A check-run
  failure is keyed by `(run id, conclusion)`, so a check that fails, is fixed,
  and fails again for a different reason is reported again, but the same
  failure is not reported twice. A repo/PR with no CI configured, or a
  head commit `gh api` cannot resolve, degrades to "no CI activity" rather
  than erroring - see `_check_run_failures` in pr_watch's source, which
  mirrors the check-run logic in the `jj-ship` skill's `checks()`.
## Ownership: which session a watch belongs to

- **A watch records the ARMING session's fingerprint, and that is what decides
  ownership.** `_owner()`'s fallback is the ambient
  `PRIME_AGENT_INTERNAL_DAEMON_WORKER_ACTIVE_SESSION_ID`, which a spawned
  sub-agent **inherits** - so inside a child it names an ancestor, and two
  sessions resolve to the *same* owner id. `poll(mark_seen=True)` (the default)
  writes `entry["seen"] |= fresh`, so under that collision whichever session
  polls first **drains the other's queue permanently**; on the victim's side the
  symptom is silence, indistinguishable from a quiet PR. Verified live on
  2026-08-13: a sub-agent's `poll()` matched six of its orchestrator's watches.
  Re-deriving the owner at poll time cannot fix this (both sessions are the same
  string), so `watch()`/`serve()` store `session` - from `RLM_SESSION_DIR`, which
  is per-session - at ARM time, and `_entry_is_mine` matches on it first.
  `watch_via_child`/`watch_via_sibling` pass the OWNER's fingerprint down, since a
  watcher child is a different session from the agent it reports to.
- **An entry that cannot be proved yours is REPORTED, never consumed.** For
  legacy entries with no fingerprint, `poll()` runs read-only - nothing marked
  seen, no terminal watch dropped - and leads with a banner saying so. `ack()` and
  `unwatch(all=True)` refuse instead, having no useful read-only form; `ack()` is
  pure destruction (it overwrites a seen-set with "everything on the PR"), and
  `unwatch(all=True)` used to clear *every* session's watches (57 entries across 6
  owners when that was found) and now clears only provably-own ones. Re-arm a
  watch from your session, pass `owner=`, or export `PR_WATCH_OWNER` to be
  authoritative.
- **Several watchers on one machine are safe.** A watch is keyed
  `<owner/name>#<pr>@<owner-session>`, where the first part is the repo SLUG
  (**not** the local checkout path - keying on the path made the same PR watched
  from a jj workspace and from the canonical clone into two ledgers with
  divergent seen-sets, which is how ~24h of review comments on fay-ui#3733 went
  unseen; existing path-keyed entries are migrated, seen-sets unioned, not
  dropped) and the second is the agent SESSION that owns it
  (`PRIME_AGENT_INTERNAL_DAEMON_WORKER_ACTIVE_SESSION_ID`, or `PR_WATCH_OWNER`).
  Two sessions watching one PR keep independent seen-sets, so neither swallows
  the other's notification; `poll()`/`ack()` only touch the current session's
  watches. The watcher child inherits its PARENT's owner id - that is what lets
  a parent's `ack()` reach its own blocked child while staying isolated from
  other sessions. Writes take an `flock` and use per-pid temp files.
## Merge/close detection and the event log

`_activity()` also reads `state,isDraft,mergedAt,mergeCommit` from `gh pr view`
(there is no `merged` field - it is `mergedAt`) and the PR's
`ReadyForReviewEvent`/`ConvertToDraftEvent` timeline items, and emits four more
item kinds through the same dedup/seen machinery: `merged` (carrying the merge
commit sha), `closed_unmerged`, `ready_for_review`, `converted_to_draft`. They
are never suppressed by `ignore_signatures` - a lifecycle item has no body to
sign, and eating a merge notification would defeat the point.

- **A terminal state ends the watch.** A merged or closed PR is reported
  immediately (no debounce - nothing further can arrive) and then `serve()`
  RETURNS a summary naming the terminal state, while `poll()` drops the watch.
  Before this the module had no merge detection at all, so a watcher polled a
  merged PR every 30s for the rest of its `max_hours` window and never mentioned
  the merge. The returned summary is what a caller keys evaluation-on-merge off.
- **Every newly observed transition is appended to `~/.prime/agent/pr-watch/events.jsonl`**
  (override with `PR_WATCH_EVENTS`, which is re-read on every append so it can be
  set after import), one JSON object per line:
  `{"at", "repo", "pr", "kind", "id", "author", "url"}`, `repo` being the slug -
  an entry whose `repo` is not `owner/name` is refused rather than written, since
  this log is meant to be safe to trigger automation off. **Anything that writes
  events in a test must redirect `PR_WATCH_EVENTS` (and `STATE_PATH`) to a
  tmpdir**: this suite once appended five fixture lines to the real log, and a
  fixture in a log that fires evals is a false trigger, not a mess. See
  `IsolatedPaths` and `ProductionLogIsNeverTouchedTest` in the tests. Note that
  the slug check does NOT substitute for that isolation - the leaked fixtures used
  `repo="o/r"`, which is a well-formed slug.
  A notification only exists inside the session that receives it - a worker
  interruption on 2026-08-13 killed ten of eleven live watchers and took their
  unreported activity with them - whereas an append-only log lets any later
  process replay what happened. Logging is best-effort and swallows its own
  errors: losing a log line must never kill a watch.

- State is `~/.prime/agent/pr-watch/state.json` (override with `PR_WATCH_STATE`)
  and survives a kernel restart; the heartbeat is session-scoped, so it dies with
  the session - re-`watch()` in a new session to re-arm it.
- `watch(seed=False)` hands you the PR's existing backlog on the first poll;
  the default seeds everything already there as seen.
- **A dead checkout must not take down the fleet.** `poll()` converges keys
  before reading anything, and convergence shells out with `cwd=<checkout>`. A
  missing `cwd` (or a missing binary) makes `create_subprocess_exec` raise
  `FileNotFoundError` - an OSError, NOT a `PrWatchError` - so it flew through
  every `except PrWatchError` and `poll()` raised for **every session** off one
  deleted directory. `_run` now returns `(127, "", "cwd does not exist: ...")`
  and `_gh` raises `PrWatchError`, so a dead checkout degrades to "this one watch
  failed". Its entry is left completely alone (never dropped, never re-keyed) -
  a stale key is recoverable, someone else's deleted seen-set is not - and
  `unwatch(repo=<dead path>, pr=N)` remains the deliberate way to remove it.
- **Convergence never accepts an ambient `GH_REPO`.** `_resolve_slug` honours
  `GH_REPO` as a last resort, which is fine for gh calls about your own repo and a
  corruption vector when rewriting somebody else's ledger entry: an
  existing-but-not-a-repo path would resolve to whatever the POLLING kernel
  exports, silently re-pointing a stranger's webflow PR #399 at
  `fayhealthinc/fay-service#399` under their owner id. `_converge_keys` passes
  `allow_ambient=False`, and an entry it cannot name from the checkout itself is
  left untouched.
- **Stale-module detection.** A long-lived kernel keeps running the `pr_watch` it
  imported hours ago, so re-arming a watch can silently write the OLD entry shape
  and leave the agent believing it is covered. Every entry is stamped with
  `entry_version`, and `poll()` reports skew in BOTH directions - older entries
  mean re-arm them (after `importlib.reload(pr_watch)` if the kernel is
  long-lived), newer entries mean THIS kernel is the stale one and its report
  cannot be trusted.
## Merge-conflict detection

`_activity()` also folds `mergeable,mergeStateStatus` into the SAME `gh pr
view --json` call used for the lifecycle fields above (no extra round trip).
Field values verified live against every open PR on fayhealthinc/fay-service
(2026-08-13): `mergeable` takes exactly `MERGEABLE`, `CONFLICTING`, `UNKNOWN` -
`mergeStateStatus` is a DIFFERENT, coarser field (its conflict value is
`DIRTY`, not `CONFLICTING`) used for other purposes and not what this reads.

- **Only a genuine EDGE is reported, never "still conflicting".** A PR can
  drift from clean to conflicting and back many times as its base branch
  moves, so this is not a terminal kind (see `TERMINAL_KINDS`) - the watch
  keeps running after reporting `conflict_detected` or `conflict_resolved`.
  The edge is detected by `_lifecycle_items(view, prev_mergeable=...)`
  comparing the CURRENT poll's `mergeable` against the CALLER's persisted
  `last_mergeable` (stored in the watch entry / passed via closures in
  `serve()`), because a single `gh pr view` snapshot has no notion of
  "changed" on its own. `UNKNOWN` (GitHub still computing mergeability, a
  normal transient after a push) is treated as no-observation on EITHER side
  of the comparison, and is never persisted over a real known value - or a
  transient UNKNOWN reading between two CONFLICTING polls would look like a
  resolve-then-reconflict that never happened.
- **The persisted baseline is written immediately, not gated on the debounce
  window.** If it waited for the item to be reported (like `seen` does), every
  poll during the quiet window would recompute the same edge against the
  still-stale baseline and mint a new item each time. `last_mergeable` updates
  the moment a poll observes it, independently of whether the resulting item
  has settled long enough to be reported yet.
- **This was the exact gap that let fay-service#7294 drift silently.**
  Rebased clean, watched by an armed sibling, then 4 more commits landed on
  `main` and put it back into `mergeable: CONFLICTING` - GitHub emits no
  comment/event for this (it is a pure git-level computation), so the
  comment/review/check-run/lifecycle stream this module already watched could
  not have seen it by construction. The watcher never said a word; a human
  caught it by asking directly.

- **`repo=` may be a `jj workspace add` directory.** Such a directory has no
  `.git`, so `gh` cannot infer the repo from it; pr-watch resolves
  `owner/name` itself (git `origin`, else `jj git remote list`'s `origin`,
  GitHub-only) and passes it as `GH_REPO`. Resolution is cached per path and
  raises at arming time if it fails - it used to fail silently, leaving a
  watcher that reported as armed while never polling once.
- Watching is **read-only `gh` polling** - it never touches the working copy,
  so aiming a watcher at a colocated checkout (or any other workspace) while
  you work elsewhere is safe and does not break workspace isolation.

Pair with the `jj-ship` skill: `jj_ship.open_pr(...)` then `pr_watch.watch(...)`,
and answer a comment with a `gh pr comment` reply or a real fix pushed by
`jj_ship.commit`/`push`.
