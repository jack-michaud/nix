---
name: pr-watch
description: Wake this agent when a watched GitHub PR receives comments, reviews, unresolved review threads, or a failing CI check-run, after a quiet debounce window (default 3 minutes) so a burst of activity produces one wake-up instead of many. Watching is free while the PR is quiet - a sub-agent blocks in a single tool call and pushes the notification. Use after opening a PR that a human will review, or when asked to keep an eye on a PR and respond to feedback.
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
- **Several watchers on one machine are safe.** A watch is keyed
  `<repo>#<pr>@<owner>`, where owner is the agent SESSION that owns it
  (`PRIME_AGENT_INTERNAL_DAEMON_WORKER_ACTIVE_SESSION_ID`, or `PR_WATCH_OWNER`).
  Two sessions watching one PR keep independent seen-sets, so neither swallows
  the other's notification; `poll()`/`ack()` only touch the current session's
  watches. The watcher child inherits its PARENT's owner id - that is what lets
  a parent's `ack()` reach its own blocked child while staying isolated from
  other sessions. Writes take an `flock` and use per-pid temp files.
- State is `~/.prime/agent/pr-watch/state.json` (override with `PR_WATCH_STATE`)
  and survives a kernel restart; the heartbeat is session-scoped, so it dies with
  the session - re-`watch()` in a new session to re-arm it.
- `watch(seed=False)` hands you the PR's existing backlog on the first poll;
  the default seeds everything already there as seen.
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
