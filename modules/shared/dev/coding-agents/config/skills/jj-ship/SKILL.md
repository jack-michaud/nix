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
await jj_ship.open_pr("Fix the widget", body=BODY, repo=REPO, draft=True)
await jj_ship.watch(repo=REPO, interval=20, max_polls=30)   # CI + new comments
```

**A non-draft PR needs attestations** (see "Attestations" below); a draft needs
none, so the loop above drafts first and asks for review afterwards:

```python
tokens = [await attest.design_reviewed(repo=REPO, base="main", head="fix-widget",
                                       design_doc_id="ENG-123", quote="...",
                                       requirements=[("...", "src/widget.py:12")]),
          await attest.eval_passed(repo=REPO, base="main", head="fix-widget")]
await jj_ship.mark_ready(repo=REPO, attestations=tokens)
```

**Before opening a PR, run your body through `normalize_markdown_body()`** if you
wrote it with a text-wrap habit (hard-wrapping prose at ~80-100 columns):

```python
body = jj_ship.normalize_markdown_body(body)
await jj_ship.open_pr("Fix the widget", body=body, repo=REPO)
```

`open_pr()` (and `ship()`, which calls it) reject a hard-wrapped body outright
with `JjShipError` - see "Model" below for why.

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
- `open_pr()` **rejects hard-wrapped PR bodies** before calling `gh`. GFM (what
  github.com renders) treats a single `\n` inside a paragraph as a hard line
  break (`<br>`), not a soft one like strict CommonMark, so an LLM's habit of
  wrapping prose at ~80-100 columns renders as a paragraph visibly chopped
  into short lines. `find_hard_wrapped_lines(body)` detects this
  markdown-structure-aware (code fences, lists, headers, tables, and
  blockquotes are never flagged); `normalize_markdown_body(body)` fixes it by
  joining each flagged break into one line. `open_pr()`/`ship()` raise
  `JjShipError` naming the offending line pairs instead of auto-fixing and
  submitting - call `normalize_markdown_body()` and retry. `skip_wrap_check=True`
  is an explicit, rarely-needed opt-in past this check, not a default.
- `open_pr()` and `mark_ready()` **require attestations for a non-draft PR** -
  see "Attestations".
- `checks()` state is `passing | failing | pending | none`; a repo with no configured checks
  reports `none`, not an error.
- `comments()` returns issue comments, review bodies, and **unresolved review threads**
  (`isResolved` only exists in the GraphQL API, so it uses `gh api graphql`).
- `watch()` polls until checks settle, printing each poll and any comment that appeared after
  the first poll. It returns `{checks, comments, polls, settled, new_activity}`.

## Attestations

Creating a **non-draft** PR, or `mark_ready()`-ing a draft, requires one signed
token per claim in `attest.REQUIRED_CLAIMS` - `design_reviewed` **and**
`eval_passed` - produced by the `attest` skill. Drafting requires none, on
purpose: a draft is where work-in-progress belongs, and friction there only
teaches agents to skip drafts.

Verification **recomputes the diff hash from the tree jj is about to push**
(`base...head`, base defaulting to the repo's default branch) and compares it to
the hash inside each token. So:

- a token issued before your last edit is refused with `attestation is bound to
  a different diff - re-run the verification after your last edit`, printing both
  hashes;
- a missing claim is refused by name, telling you which `attest.<claim>(...)` to
  run.

On success the body gains a trailer:

```text
Shipped-With: jj_ship/0.2.0 attest=1a2b3c4d5e6f,0f9e8d7c6b5a
```

Those are token IDs (`sha256(token)[:12]`), never the tokens themselves - a token
is a bearer credential. The trailer's purpose is detection: a PR opened outside
this path has none, which is visible from GitHub alone. `mark_ready()` appends it
to the existing body at ready time rather than at draft time, because a draft's
diff is expected to keep moving and a trailer naming a stale token is worse than
no trailer.

`ship()` takes `attestations=` **keyword-only, defaulting to None**, so every
existing call site keeps working and only the non-draft path raises. Read
`attest`'s SKILL.md before assuming what this buys: it is tamper-evident, not
tamper-proof, and the load-bearing part is the verification work, not the
signature.

## Stacked PRs

`ship()` and `open_pr()` take `base=`, so a stack works - but the mechanics are
easy to get wrong. Layout: **one commit per PR, one bookmark per commit, one PR
per bookmark.** PR 1 bases on the trunk branch; every later PR must pass
`base=<bookmark below it>`. Without that, GitHub diffs the child against trunk
and shows the parent's commits inside the child's diff, so the reviewer reads
the same code twice.

**The stack tip is home.** Every operation ends by returning to the tip and
pushing everything. Leaving `@` parked mid-stack is how the next change silently
gets authored in the wrong place.

### Review feedback on an earlier PR in the stack

```sh
jj new -r <latest revision in the PR that got feedback>
# ...do the work...
jj describe
jj rebase -r <revision which starts the next PR>:: -d @   # that rev + all descendants onto the fix
jj new <PR stack tip>                                     # return to the tip
jj git push -b branch1 -b branch2 -b branch3              # push EVERY bookmark, not just the one you touched
```

`<rev>::` selects that revision *and all its descendants*; that is what carries
the rest of the stack forward onto the new commit. Push every bookmark, because
every PR above the fix now has new content - only pushing the one you edited
leaves the PRs above it pointing at abandoned commits. Do not hand-cherry-pick
and do not move bookmarks manually; the rebase already did both.

### When the rebase leaves conflicts

Resolve bottom-up, one revision at a time:

```sh
jj new <earliest conflicting revision>
# ...fix the conflict...
jj squash
```

Repeat until the whole branch is clean, then `jj new <PR stack tip>` and push
everything again. This works because jj records a conflict *in the commit*
rather than blocking the operation, so you can rebase the whole stack first and
resolve afterwards.

### When the bottom PR merges

GitHub retargets the child PR to the trunk branch once the merged branch is
deleted. With a merge queue that can land a moment after approval, so re-check
the base before assuming it broke.

### Orchestration

- **One agent owns a whole stack.** A stack needs shared history, so it cannot
  be split across agents - two agents in one working copy is a known failure
  mode. Independent work gets separate workspaces; a stack does not.
- **Count a stack as one review unit when rate-limiting open PRs.** A WIP limit
  on open PRs exists to protect review capacity, and a stack of tightly-related
  PRs by one author reviews as one cohesive chain - often more easily than the
  same changes reviewed apart, since the whole plan is visible at once. The real
  cost of stacking is reviewer cognitive load, not rebase pain (jj makes
  rebasing cheap), and that is what should drive any depth cap.

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
