---
name: jj-ship
description: Commit with jj, push a bookmark to a git remote, open a GitHub PR, and monitor its CI checks and PR comments. Use when the user asks to commit/push work with jj (jujutsu), open or update a pull request, check CI status, or watch for review comments on a PR.
compatibility: Requires the `jj` and `gh` binaries on PATH and an authenticated `gh`. The repo must be jj-colocated (`.jj` next to `.git`) with a `git` remote.
---

# jj-ship

A small ship loop for agent sessions: **commit -> push -> open PR -> monitor CI and comments**.
It is the agent-side equivalent of agent-harness's `default` workflow ship stage, but callable
directly from the kernel. It never merges anything - monitoring is deliberately separate from
landing authority.

## Quick use

```python
await jj_ship.status(repo=REPO)                       # what is in @, which bookmarks
await jj_ship.commit("Fix the widget", repo=REPO, bookmark="fix-widget")
await jj_ship.push(repo=REPO, bookmark="fix-widget")
await jj_ship.open_pr("Fix the widget", body=BODY, repo=REPO)
await jj_ship.watch(repo=REPO, interval=20, max_polls=30)   # CI + new comments
```

One-shot equivalent of the first three:

```python
await jj_ship.ship("Fix the widget", bookmark="fix-widget", body=BODY, repo=REPO)
```

Shell form (same actions, JSON out):

```bash
jj_ship --action status --repo /path/to/repo
jj_ship --action watch --repo /path/to/repo --pr 42 --interval 20
```

## Model

- **jj has no staging area.** Whatever is in the working copy already *is* the change `@`.
  `commit()` therefore describes `@`, points the bookmark at it, and then runs `jj new` so a
  later edit starts a fresh change instead of silently amending the one you just pushed.
- `commit()` refuses an empty change unless `allow_empty=True`.
- `push()` runs `jj git push --bookmark <name> --allow-new`; with no `bookmark=` it uses the
  bookmark on `@`, else on `@-` (the normal shape right after `commit()`).
- `open_pr()` is **idempotent**: an existing open PR for that head branch is returned rather
  than a `gh pr create` failure.
- `checks()` state is `passing | failing | pending | none`; a repo with no configured checks
  reports `none`, not an error.
- `comments()` returns issue comments, review bodies, and **unresolved review threads**
  (`isResolved` only exists in the GraphQL API, so it uses `gh api graphql`).
- `watch()` polls until checks settle, printing each poll and any comment that appeared after
  the first poll. It returns `{checks, comments, polls, settled, new_activity}`.

## Notes

**Pass `head=` once the working copy has moved.** `open_pr` infers the branch
from the bookmark on `@` or `@-`, which is right immediately after `commit`, but
after a `jj new main` it resolves to the DEFAULT branch - and `gh pr create
--head main` fails with the opaque `GraphQL: No commits between main and main`.
The skill now refuses that case with an explanation instead of passing it to
`gh`; supply `head="<bookmark>"` explicitly when shipping something you finished
earlier.

Related jj sharp edge, same cause: a colocated jj repo leaves git on a detached
HEAD, so any `gh` subcommand that infers the current branch fails
(`gh pr merge --delete-branch` reports `could not determine current branch`).
The merge still lands; delete the remote branch with
`gh api -X DELETE repos/<owner>/<repo>/git/refs/heads/<branch>`.


- Binaries are overridable with the `JJ_BIN` / `GH_BIN` environment variables.
- Every failure raises `jj_ship.JjShipError` carrying the failing argv and its stderr.
- Fixing CI or answering a review is *your* job: `watch()` reports, it does not act.
