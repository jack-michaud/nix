---
name: pr-watch
description: Wake this agent when a watched GitHub PR receives comments, reviews, or unresolved review threads, after a quiet debounce window (default 3 minutes) so a burst of review comments produces one wake-up instead of many. Use after opening a PR that a human will review, or when asked to keep an eye on a PR and respond to feedback.
compatibility: Requires an authenticated `gh` and runs inside the agent kernel (it registers an RLM heartbeat).
---

# pr-watch

Opening a PR is not the end of the work - the review comes minutes or hours
later. This registers a PR plus an RLM heartbeat, so the session wakes itself,
sees the new comments, and answers them.

```python
await pr_watch.watch(repo="/path/to/repo", pr=2)   # arms the heartbeat too
await pr_watch.poll()                              # what the heartbeat runs
await pr_watch.ack(repo="/path/to/repo", pr=2)     # after you post a reply
await pr_watch.watching()
await pr_watch.unwatch(repo="/path/to/repo", pr=2)
await pr_watch.unwatch(all=True)                   # also cancels the heartbeat
```

## The debounce is the point

`poll()` never reports activity that is still arriving. New items are held until
nothing newer has landed for `quiet_seconds` (default 180), so a reviewer leaving
eight inline comments over two minutes wakes the agent **once**, with all eight,
after they stop - instead of eight interrupted turns racing a half-written
review. Items reported once are marked seen and never repeat.

- **`ack()` after replying.** The agent comments through the same GitHub account
  as its human, so its own reply reads as new activity and would wake it up to
  answer itself. `poll()` marks what it reports; `ack()` covers what you posted.
- The heartbeat runs every 3 minutes in `follow_up` mode, so it never interrupts
  work in progress.
- Watched: issue comments, review bodies, and comments on **unresolved** review
  threads (a resolved thread needs no answer). Resolution state only exists in
  the GraphQL API, so that half goes through `gh api graphql`.
- State is `~/.prime/agent/pr-watch/state.json` (override with `PR_WATCH_STATE`)
  and survives a kernel restart; the heartbeat is session-scoped, so it dies with
  the session - re-`watch()` in a new session to re-arm it.
- `watch(seed=False)` hands you the PR's existing backlog on the first poll;
  the default seeds everything already there as seen.

Pair with the `jj-ship` skill: `jj_ship.open_pr(...)` then `pr_watch.watch(...)`,
and answer a comment with a `gh pr comment` reply or a real fix pushed by
`jj_ship.commit`/`push`.
