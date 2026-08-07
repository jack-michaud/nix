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

## Two ways to be woken (prefer the child)

| | `watch_via_child()` | `watch()` |
|---|---|---|
| Mechanism | a sub-agent blocking in `serve()` | an RLM heartbeat + `poll()` |
| Token cost while quiet | **zero** - the loop runs inside ONE tool call | one model turn per interval, forever |
| Cost to start | one turn | one turn |
| Latency | `poll_seconds` (default 30s) after the quiet window | up to the heartbeat interval |
| Lifetime | until `max_hours` elapses, then re-arm | until the session ends |

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

## The debounce is the point

`poll()` never reports activity that is still arriving. New items are held until
nothing newer has landed for `quiet_seconds` (default 180), so a reviewer leaving
eight inline comments over two minutes wakes the agent **once**, with all eight,
after they stop - instead of eight interrupted turns racing a half-written
review. Items reported once are marked seen and never repeat.

- **`ack()` after replying.** The agent comments through the same GitHub account
  as its human, so its own reply reads as new activity and would wake it up to
  answer itself. `poll()` marks what it reports; `ack()` covers what you posted.
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

Pair with the `jj-ship` skill: `jj_ship.open_pr(...)` then `pr_watch.watch(...)`,
and answer a comment with a `gh pr comment` reply or a real fix pushed by
`jj_ship.commit`/`push`.
