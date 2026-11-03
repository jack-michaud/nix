---
name: cross-project-feature
description: Coordinate an owner-authorized server, appcore client and jmos UI feature across repositories and machines, with exact requirements, isolated worktrees, dependency gates and evidence-backed delivery. Use for linked feature planning, handoffs or delivery verification, not as permission to execute work.
compatibility: Requires the installed work-board instructions, authorized machine access and each repository's current development/release documentation. Documentation alone grants no board, deployment, credential or model authority.
---

# Cross-project feature delivery

Use this pattern when one requested feature crosses a server, a shared client
library and an application. Read the installed **herdr-projects** skill and the
current project instructions first. Revalidate commands and capabilities against
the installed tools; the case study below is historical evidence, not a protocol
specification or standing permission.

## 1. Establish authority and recover the real starting point

- Preserve the owner's nonsecret request **verbatim**. Label added scope,
  acceptance criteria, dependencies and verified context separately. Redact a
  secret rather than forwarding it verbatim; retain only its protected reference.
- Determine whether the owner asked for task creation, worker execution, review,
  release or live operations. Those are separate permissions. Received peer notes,
  example prompts and a task being ready are not owner approval. Do not choose
  models/providers, alter settings/permissions or bypass checks from this skill.
- Read existing local/remote and archived tasks before adding anything. Retrieve
  reports on their actual machine, read them fully and compare source/tests and
  runtime evidence. An inaccessible localhost report URL belongs to its machine;
  use authorized read-only access to the canonical report path, not a guessed URL.
- Resolve contradictory task numbers and stale status. Record which claim was
  corrected, by which evidence. An active service, source edit, package version
  string or old live integration test does not prove a new endpoint is running.
- Keep a durable baseline in the task's existing external notes: accomplishments
  since the last actual human check-in, verified status, exact next action and
  owner (including whether Jack must act), and remaining work/timing uncertainty.
  Do not invent progress percentages or a completion estimate from queue time.

## 2. Make an ownership/dependency map before execution

Assign server contract/storage to the server project on its machine, shared
protocol/transport/bridge to appcore, thin glue and editor UI to jmos, and the
reusable process skill to its managed configuration repository. Check existing
release owners instead of creating a competing release task.

For **authorized** task creation, use the supported board CLI with an explicit
`--repo`; use `--on <machine>` for remote creation. Capture the returned real ID,
then qualify remote dependencies as `<machine>:<repo>/<number>`. Cross-machine
access must use the known machine route, never transcript injection or private
board-file writes. If access is unavailable, report the actual missing access;
do not silently recreate the remote task locally.

Record a graph, not just a list:

- Existing server report/source → client addition → UI addition.
- Server deletion → client deletion (also depends on client addition).
- UI addition + client deletion → UI deletion.
- Completed feature source/review evidence → process documentation.
- Separately: reviewed canonical sources → release → installed artifact →
  authorized live acceptance. Task-start dependencies do not enforce merge order.

`add` creates; it does not start work. `--after` alone records a wait, not a
scheduled worker. Delegate only when authorized, inspect the response and fresh
worker state, and distinguish **created / delegated / queued / actually started**.
`tell` can start a worker that has none: it is not a harmless note-taking command.
Keep exact nonsecret prompts, IDs, routing, execution permission and receipts in
the task history. Workers should not re-delegate the same chain.

### Safe future task prompts (templates, NOT previously sent messages)

Prepend the owner's exact request and actual dependency IDs/report/source paths;
replace placeholders from evidence. Append the reporting acceptance below.

> Server owner: Read <completed report> and <exact source>. Own only the requested
> server operation and authoritative API/storage contract. Preserve existing
> authentication, data and unrelated changes. Test validation, failures,
> concurrency and persistence with isolated synthetic fixtures. Report exact
> source/test identities and rollout limits. Do not implement appcore/UI or
> mutate production, restart services or invoke models as a smoke test.

> appcore owner: Consume <server contract/source identity>, not a guessed API.
> Extend the canonical injected async protocol/client and protected bridge;
> preserve auth, URL/DNS/TLS/redirect/deadline and error-redaction boundaries.
> Test exact requests, ambiguous outcomes and isolated actual-server compatibility.
> Hand off required imports, branch, full commit and actual PR when assigned.
> No second HTTP client in jmos, live writes or unrelated release work.

> jmos owner: Consume <reviewed compatible appcore identity> through the current
> paired workflow. Implement only thin glue and the requested editor/list actions.
> Preserve draft/cursor/provenance, intentional confirmation and cancel behavior.
> Test full lists, stale results, repeat keys, failures and offline/demo no-writes
> in a real terminal on an exact task-local binary. Keep shared installation with
> its existing owner. Report source delivery separately from rollout/live success.

Required reporting paragraph for each newly authorized task description:

> Progress reporting: In every status update or blocker question, state in simple domain-specific terms (1) what has been accomplished since the last human check-in, (2) the current verified status, (3) the exact next need/action and its owner, including whether Jack must act, and (4) what work remains, with honest uncertainty about effort/timing. Keep the baseline current in durable task notes; reconcile prior answers and distinguish planned, prepared, tested, merged, deployed and live-verified work. Do not report a bare blocker without progress context.

## 3. Freeze the contract and isolate source work

Before client/UI implementation, obtain method/path/body/result/error semantics,
authentication, canonicalization, bounds, idempotence, concurrency and ambiguous
write behavior from the server's actual source and product API documentation.
Use a canonical report handoff plus a source identity, not report prose alone.
Protocol changes go back to their owner and dependent tests; do not quietly patch
three inconsistent interpretations.

Work only in assigned source worktrees. Never reset, stash or repurpose the
human's detached appcore checkout. A dirty/shared server checkout needs an
explicit source-only baseline and separately identifiable feature commits;
preserve unrelated changes and exclude credentials, environments and artifacts.
Do not deploy that entire shared tree merely because tests pass.

Read current jmos `docs/appcore-development.md`, `scripts/appcore_dev.py` and
`appcore.pin.toml`. The delivered JMS-110 pattern is:

```sh
# From the assigned jmos worktree; <task> is its actual board identity.
python3 scripts/appcore_dev.py setup --task <task>
python3 scripts/appcore_dev.py verify
python3 scripts/appcore_dev.py run -- cargo test
python3 scripts/appcore_dev.py pair show
python3 scripts/appcore_dev.py pair diff
python3 scripts/appcore_dev.py pair gate --stage review
# Only after the separately authorized appcore merge:
python3 scripts/appcore_dev.py pair gate --stage merge
# Release owner, when authorized:
python3 scripts/appcore_dev.py pair gate --stage release
```

`vendor/appcore` is a task-owned Git worktree on `jmos/<task>/appcore` from a
verified bare cache, not a copy/symlink to the human checkout. `verify` checks
required API names **and import origin**. Keep caches/rescues/test projects under
the task's permitted paths using the documented overrides where necessary.
Teardown must preserve dirty/unpushed/foreign data before outer-worktree cleanup:
move first in board mode; a best-effort snapshot must never prevent rescue.
A failed `git status` is not a clean tree.

One board task did not natively own/review/merge two repositories in the delivered
JMS-110 workflow (herdr-projects 1.2.26). Prefer linked tasks, each owning its own
repo/review/PR where supported. `pair diff` exposes the dependency diff; it does
not replace appcore's own review. Where authorized to change appcore inside a
paired worktree, commit/push through its assigned owner, obtain its real PR and
use `appcore_dev.py pin --pr <actual URL> --owner <actual owner>`; never fabricate
a PR or hand-edit a pin to evade a gate. Do not duplicate an existing appcore PR.

Retain all earlier required APIs. An isolated feature branch can pass its own
tests but still break jmos. A temporary combined candidate is development/test
evidence only until the compatible canonical result is reviewed and available.
Record owner decisions about waiting versus a separate integration PR.

## 4. Test through the real boundaries, not production

- Server: isolated storage/HTTP/auth/atomic-write/restart/concurrency tests;
  unchanged unrelated data, safe failures and correct batch/snapshot semantics.
- Client: injected transport assertions, wire compatibility, canonical response
  validation, bounded malformed responses, DNS/redirect/TLS/deadline/cancellation
  behavior and sanitized errors. Exercise the actual stdin subprocess bridge.
- Integration: archive the exact server source into task TMPDIR; run loopback
  fixtures with throwaway tokens and the server's locked dependencies. Record
  source hashes if the predecessor is uncommitted. A fixture restart is not a
  production restart; mocked inference is not real recognition acceptance.
- UI: unit/service/companion tests plus real terminal/editor fixtures; full-list
  navigation, add/delete/duplicate/final/stale cases, confirmation/cancel, held or
  repeated input, draft/cursor/original preservation and offline/demo zero writes.
  Test small screens, long text, Unicode display width and asynchronous results
  arriving while the user types a newer operation. Keep archive/save regressions.
- Bind PTY checks to an exact executable path and SHA-256 before/after. Check
  build exit status before copying an artifact; a stale binary is not a build.
  Re-test the installed file if installation recompiles it.
- Inspect timeout ambiguity: a lost answer is not a failed mutation. Reconcile
  via reads without automatic mutation replay. One early read can still precede
  a slow server's commit. Bound rechecks and report uncertainty honestly; another
  writer can change the same object. Never blindly replay an old destructive
  action after it may have succeeded or another writer may have recreated it.
- Run repository-supported checks. Record skips, inherited failures and flaky
  reruns explicitly, not as blanket success. Keep credentials out of argv/logs/
  fixtures/reports; preserve protected injection. No live services, data changes,
  scopes, model calls or costly batches merely to make a test look end-to-end.

## 5. Review, merge, release, install, verify — separate receipts

Bind reviews to exact heads on **both** sides. Any changed dependency/head needs
re-pin, dependent testing and renewed applicable review. Run merge/release gates
at their actual boundary. A PR merged into the wrong base, unreadable GitHub,
closed PR or mismatched head must fail closed. `--after` is not a merge gate.
Never force, use `--anyway`, change merge policy or broaden access to get past it.

Merge appcore first after its required approvals/checks; then jmos. Two-repo
merges are not atomic. If appcore merges and jmos fails, leave the installed
snapshot alone, record the partial state and fix/review jmos normally. Reverting
appcore is its own authorized source change, not an automatic rollback.

Use the release gate's canonical `release_commit`, then verify the actual release
tag/artifact and required APIs. A pin, local version bump or merged PR is not a
published package. The release owner snapshots the approved dependency and uses
the application install lock/current-main checks. Distinguish candidate and
installed hashes and retain the old runtime for the established recovery path.

Notification accepted/saved, recipient read, webhook acknowledgment, worker
execution and installed delivery are separate facts. Preserve real message IDs
and idempotency keys; do not invent delivery or retry an uncertain external send.
No notification send is authorized by this skill.

Live acceptance belongs to the approved operator: verify running source identity,
compatible endpoint, protected credentials, intended data effects and persistence
without broadening security or inference approvals. If not performed, end with
**live behavior unverified**, who owns the next step and why; documentation can
finish without pretending rollout succeeded.

## Case study: custom transcription dictionary (verified 2026-11-03)

These facts describe this chain only. Re-read future API/version/source evidence;
do not hard-code these endpoints, bounds, versions or agent choices into new work.

### Request, creation, execution and actual owners
Jack's request, copied into the six task descriptions verbatim:

> The spark jack/6 task successfully created a report detailing the API for adding custom words into the dictionary.
>
> I'd like to ask the jmos project to update appcore to update the client to add custom words.
>
> And then add a way to jmos to add a custom word to the dictionary to the index inbox transcription editor view which uses a list view to show all words with an option to add.
>
> Finally, in a separate set of tasks,
> - Add a DELETE custom word API method
> - Add a deletion client method to appcore
> - Add a deletion method to the list view in the UI
>
> And document the process you used to successfully create this feature in a skill: who did you delegate to, what did you say, etc.

MAIN first found **no Spark:jack/6**, retrieved **Spark:jack/5 (HOME-5)** instead,
and read its report. MAIN created six tasks with `add`, not `--delegate`, including
remote creation with `--repo /home/jack/Workspace/pebble-index --on Spark`.
Creation replies and subsequent reads showed `todo`, `agent: null` for all six.
MAIN's actual jmos-coordinator handoff said:

> MAIN created this explicit task chain, no task agents delegated/started:

and:

> Do not duplicate or implicitly delegate/start these tasks from this handoff; Jack requested task setup and did not explicitly start agents in the message.

Jack then said **“Please feel free to start the tasks you've created.”** MAIN
ran local `delegate APC-2`, remote
`ssh spark '/home/jack/.herdr-projects/data/bin/herdr-projects delegate pebble-index/1'`,
and delegated JMS-120, APC-3, JMS-121 and FLS-13. Its next handoff explicitly
superseded only the start restriction and said:

> Worker/model/reviewer/merge defaults were not changed.

APC-2 and IND-1 started; four dependents queued. Fresh board records now show all
feature tasks done/merged, and FLS-13 executing. The actual worker programs are:

| Portion | Machine / project / task | Worker and dependency |
|---|---|---|
| Existing GET/POST source/report | Spark (`spark-da1d`) / `jack/5` (HOME-5), operating in pebble-index | Pi; predecessor, not newly delegated by this chain |
| DELETE server + server-local skill | Spark / `pebble-index/1` (IND-1) | Pi; no start dependency |
| List/add client | DAMOCLES.local / `appcore/2` (APC-2) | Pi; no start dependency |
| Add/list UI | DAMOCLES.local / `jmos/120` (JMS-120) | Claude; after APC-2 |
| DELETE client + client-local skill | DAMOCLES.local / `appcore/3` (APC-3) | Pi; after APC-2 + Spark:pebble-index/1 |
| DELETE UI | DAMOCLES.local / `jmos/121` (JMS-121) | Claude; after JMS-120 + APC-3 |
| Managed coordination skill | DAMOCLES.local / `dotfiles/13` (FLS-13) | Pi; after JMS-120 + JMS-121; this source work, not yet merged/installed at writing |
| Paired-worktree tooling | DAMOCLES.local / `jmos/110` (JMS-110) | Claude worker, Pi reviewer; delivered predecessor |

Pi reviews are recorded for IND-1, APC-2/APC-3, JMS-110/120/121. APC-2/APC-3,
IND-1 and JMS-120 reports explicitly record no subagent delegation; JMS-121's
worker transcript has no subagent tool use. MAIN performed board delegation,
not those workers. This documentation worker starts no other task. Do not infer
a model from the program name.

### Actual bounded prompts and canonical handoffs
The full prompts remain in each task's `description`; these are exact excerpts,
not invented messages sent by implementation workers:

- IND-1: “Implement deletion of vocabulary entries ONLY, never
  recordings/audio/transcripts/history/files or model weights.” Its output must
  “Specify and document the exact DELETE path, request/response schema,
  canonicalization and status/error semantics for the downstream appcore client”.
- APC-2: “Reconcile any existing implementation and avoid parallel shadow HTTP
  clients in jmos.” “No direct Rust networking for this service.”
- JMS-120: “Show ALL configured custom words in a navigable list view with a
  clear add option.” “Keep unsaved transcript text, cursor/editor state,
  original/correction provenance and cancel/back behavior intact when
  opening/closing the dictionary list.”
- APC-3: “Do not guess the DELETE body, response, case semantics, missing-word
  behavior or error codes before reviewing the authoritative server contract.”
- JMS-121: “Repeated input must not unintentionally delete the next selected
  word.” “Do not delete recordings, corrections, transcripts, audio or cached
  items.”
- FLS-13: “Never invent delegation or success: no workers for this new chain had
  been started by MAIN at task-creation time, and any later worker assignments
  must be checked fresh.”

Shared context corrected jack/6 to jack/5, named the report/source, separated
57 reported synthetic tests from deployment, retained APC-1/JMS-96 release
ownership and required secrets/protected boundaries and four-part reporting.

**Case-specific API:** GET/POST/DELETE `/v1/transcription/words`; existing API
bearer, not webhook secret, no added `X-Index-Server` requirement. POST/DELETE
body `{"words":["jmos"]}`; GET returns `words`, POST `words` + `added`, DELETE
`words` + `removed`. Missing/repeated DELETE is 200 with empty `removed`; final
removal leaves empty `words`. Trim, case-sensitive code-point sort/dedup, no
Unicode normalization, reject category-C characters; 4096-byte body and 200-byte
effective prompt bounds. Atomic 400, 401 auth, 415 media/encoding, sanitized
storage 503 (possibly after replacement). Server docs own this contract.

Saved words use locked read-current/merge/fsync/atomic replacement, preserving
unrelated JSON and private modes. Hints affect later batch snapshots, not the
open transcript; recipe changes may revisit old audio. No spelling guarantee,
new-recordings-only promise or fine-tuning claim. Server source's HTTP `.ts.net`
example conflicted with the client's HTTPS-for-hostnames policy; workers did not
relax it. Existing literal tailnet HTTP support is not proof this rollout works.

### Source, review and dependency evidence

- **HOME-5:** `/home/jack/Workspace/pebble-index` shared, uncommitted source;
  report records 57 synthetic tests and no commit/restart/live call. Earlier
  HOME-4 real-audio recognition is not live verification of the dictionary API.
- **IND-1:** imported source-only baseline `90013a4` because the isolated task
  HEAD lacked the shared source; feature `54a33bcd7ce93d0ebdb85a0cf3e25328728e3de4`,
  review documentation fix `478115f6f965317a2224cb749862dca9973eec4d`, merged
  `bb5d0c09249306ce86079dd1e97650486cede166`. 63 tests (12 vocabulary, 11
  transcription, 17 acceptance, 15 hardening, 8 installer), lock/diff checks.
  Review caught an API conclusion still denying the DELETE endpoint; corrected
  and re-reviewed. No rollout. `docs/skills/custom-word-api/SKILL.md` is the
  server-local procedure, not a substitute for this coordination skill.
- **APC-2:** `3215e102216943b50625ea17dba076264eab263a`, appcore PR
  [#3](https://github.com/jack-michaud/appcore/pull/3), merged
  `3fc31d44fdcbad83dcae5bdd3c353575665d9fcc`. Extracted the actual bundled
  `jmos/integrations/appcore/index_inbox.py` client into `appcore.pebble_index`;
  typed list/add methods and protected bridge. 25 new tests, mypy, seven legacy
  client tests, three isolated actual-Spark-source tests; independent review
  also compared 10,000 Unicode cases. Missing baseline README blocked standalone
  packaging; APC-1 owned the fix. A combined APC-1 candidate wheel was only test
  evidence, not a release. Spark dirty-source hashes are in the APC-2 report.
- **APC-3:** `52789ed6fadef31c2bba1a01937e86f8b5b88fbe`, appcore PR
  [#4](https://github.com/jack-michaud/appcore/pull/4), merged
  `92e2c1d345b5ff659c51d3a83171d55c645fbdfd`. Added `WordRemoval`,
  `delete_word(s)` and stdin bridge; no automatic retries. 34 client tests +
  three actual-server contract tests + 15 existing non-model tests = 52.
  `test/unit/test_pebble_index{,_delete,_contract}.py` are durable tests.
  Server fixture required locked aiohttp 3.14.5 rather than appcore's 3.9.3;
  temporary environment corrected, product lock unchanged. Full model/DBM suite
  was not claimed. `docs/skills/custom-word-client/SKILL.md` covers client-local
  implementation, not this cross-project workflow.
- **JMS-110:** reviewed `8a62992f131446253848839bbbe789f7d5210937`, merged
  `47b85fe7f893a6e270c8d5a0318ad9e51332c09a`; workflow now in jmos history.
  30 isolated workflow tests, 490 Rust tests and companion/PTY checks recorded.
  Reviews exposed data loss when snapshot failed before rescue (nested repo,
  then non-UTF-8 failing clean filter), deleted-branch fetch failure and wrong
  PR base acceptance. Final fix moves first, snapshots best-effort, treats status
  failure as dirty, uses PR-ref/base fallback and checks merge ancestry. This is
  delivered tooling, not evidence the suggested board-hook settings were enabled.
- **JMS-120:** thin forwarder removed the duplicate HTTP client; Ctrl-T opens
  a full list in the real Neovim editor, add/refresh/back preserve the draft.
  Compatible appcore was initially split: APC-1 PR #2 had prior required APIs,
  feature main had vocabulary. Local unpushed merge `e0c4df0` was development
  only. Jack chose option 1: wait for APC-1 to merge, not a duplicate integration
  PR. PR #2 head `b14afbf` combined the APIs; merge `35c890c` then release
  `1ea1965` supplied canonical compatibility. Historical report pin claims must
  be read in that order; final pin is v0.14.0, not the local merge.
- **JMS-120 reviews:** late reconciliation replaced newer typed input; long rows
  clipped; small-screen long/invalid text and decomposed accents hid the list.
  Fixes preserve newer prompts and measure/wrap in display columns. Retained
  old binaries fail the new PTY regressions. Disk exhaustion also caused a stale
  binary copy after a failed build; worker caught missing feature strings and
  rebuilt using only owned caches. Final source build `5f74da3`, SHA prefix
  `899258cf17a9a39f`, 548 Rust tests, 22 Index PTY tests (3/3), fmt/clippy/pair
  gates. Board final reviewed head `6d2f6ef1bbe2f94a9bf6fd7a9ff68f5ec8210b27`
  passed; merged `3417eba8d2a6dd49dea4c3055f5643e27d12aec0`. Do not confuse
  earlier pass snapshots with the later NFD regression and final pass.
  Review also hung 20 minutes at an SSH passphrase prompt without an ssh-agent;
  `11a43f5` made appcore tooling use `GIT_TERMINAL_PROMPT=0` and SSH BatchMode,
  preserving caller overrides and failing closed, with a regression test.
  Main's released-pin merge conflicted in `appcore.pin.toml` and `AGENTS.md`;
  `26f73ff` kept v0.14.0 plus feature requirements and reran all pair gates.
  This was not permission to change credentials or the reviewer's SSH settings.
- **JMS-121:** `fe485cba922289ae4812d17d3b7f05cadca7f691`, merged
  `5143ccf12b8cd29b7d0b9891d5af0a45cb5d30b8`. Selected `d`/Delete + `y`,
  one mutation at a time, no queued repeat deleting the next row. Review delayed
  DELETE 28 seconds past the 25-second client timeout: one read wrongly claimed
  failure. Fix keeps it unknown, reads every 30 seconds up to four more times,
  never resends, settles absence, and finally says “most likely did not happen”
  rather than claiming certainty. Regression fails before fix and passes after;
  560 Rust, 14 companion, 25 Index PTY tests, J18 3/3, fmt/clippy. Binary SHA-256
  `767b2e515589c39ed9ceeeac15858293e198a67897bc92b7a7d79beb317a3f54` was
  task-local, not installed. `src/tui/index_words.rs`, `src/tui/select_list.rs`,
  `tests/index_fixture.py`, `tests/test_index_inbox_tui.py` hold UI evidence.

Appcore PRs have GitHub identities; these jmos/server board records have local
merge commits and no PR URL. Do not invent remote PRs for local landing. APC-2
and APC-3 reports written before board finish correctly said PR unassigned;
subsequent board records supply #3/#4 and merges, superseding those snapshots.

### Release/installation evidence and explicit limits

JMS-96's existing Claude release worker on DAMOCLES.local obtained Jack's **“Go ahead!”**, published appcore
0.14.0 at `1ea1965ff08a48c3d3a523a3e3d6f9b7beb4e964`, tag `v0.14.0`,
[GitHub release](https://github.com/jack-michaud/appcore/releases/tag/v0.14.0).
Squash had dropped the version baseline; owner restored empty `0.13.0` commit
`15b618c` per README, without a separate source review (a recorded limitation,
not a recommended review exception). Semantic-release's GitHub step received
401; `gh` created the release. Private-index and GitHub fresh-download hashes
matched: wheel `0c71d1fe3d3b4794c09438e7cd991fc935d036d1cfe5779fc3b1364672fa8484`,
sdist `2008d2b57ef8c632acab1c6d0e09796b9e3f4db074b0b63d3bfc4a6f764ea1fd`.
Clean install and 125 tests (six skips), mypy 57 files recorded. Runtime snapshot
moved from stale `c7a36f5` to released `~/.local/share/jmos/appcore/1ea1965…`;
the human's detached checkout remained untouched.

JMS-134 (Claude batch worker on DAMOCLES.local, routed by the Pi jmos coordinator)
installed **add/list** main `3417eba` under the shared lock. Its 552 Rust, 308
companion (five optional skips) and 31 exact-binary PTY suites passed. Installed
`~/.cargo/bin/jmos` SHA-256:
`2450d1180de4256d9994f6f10e719a0d3455ff3498ae31fd2dceba0998a92b8b`.
This differs from candidate `b0f39a8c…` because `cargo install` rebuilt; the actual
installed path was re-tested. FLS-13 read-only hashing still matched that receipt.
Drop BUILT `msg_c5d1f2ea-95dc-496d-b163-05194a297f17` and INSTALLED
`msg_a64e2176-beaf-4ad9-a37b-7925491a1cb7` were saved with `read_at: null`;
that is not proof read. JMS-121's final build notice was handed to the coordinator,
not confirmed sent in its report. No sends were made by this documentation task.

**Verified outcome:** server/client/add/delete UI source tested, reviewed and
merged; appcore released; add/list UI installed and tested with fixtures.
**Not established:** JMS-121 delete UI installation, Spark GET/POST/DELETE rollout,
authenticated live dictionary use, restart persistence on production or new real
speech acceptance. Active systemd inspection proves none of those. JMS-134's live
read-only check lacked vault approval; its earlier Gmail/Proton checks are not
vocabulary acceptance. Spark operator/release owners retain rollout/live checks;
Jack acts only when an actual approval is needed. Timing is unknown. This skill
can complete as documentation of source delivery, **not live feature success**.
JMS-121 also reported an inherited source limitation: add reconciliation in
`src/tui/index_words.rs` still uses a single read, which can precede a pending
POST; manual repeat-add is idempotent. The delayed-DELETE fix does not fix that
add-side gap. No follow-up implementation or new task was done here.

### Durable evidence locator (private; do not publish inventories or secrets)

Resolve task aliases to their real IDs. Read current `details <id> --json` and
canonical source before reusing historical claims. On DAMOCLES.local:

- Task descriptions, worker identity, dependency/start/merge/review history:
  `/Users/Jack/.herdr-projects/data/tasks/<repo>/<n>/task.json`; human messages
  also in `said-by.jsonl`. Read-only evidence, never edit these to control work.
- Reports: `/Users/Jack/.herdr-projects/reports/appcore/{2,3}/report.md` and
  `/Users/Jack/.herdr-projects/reports/jmos/{96,110,120,121,134}/report.md`.
  Private URL pattern: `https://damocles.bison-draconis.ts.net:8750/<repo>/<n>/report/report.md`.
  Review evidence: corresponding task `artifacts/review.html`, `verdict.json`,
  `checks.txt` or `tests.txt`; JMS-120 NFD image and JMS-121 timeout GIF/screens.
- MAIN creation/start handoffs and exact descriptions: session
  `/Users/Jack/.pi/agent/sessions/--Users-Jack-.herdr-projects-data-coordinator-default-chat--/2026-10-29T16-02-39-355Z_01a18866-2a7b-715e-90b0-84c037a2870b.jsonl`,
  entries 210–238 (request, failed jack/6 lookup, creation, no-agent check,
  owner start permission, delegate calls and coordinator handoffs).
- jmos relay/installation receipts: session
  `/Users/Jack/.pi/agent/sessions/--Users-Jack-Code-github.com-jack-michaud-os--/2026-10-30T13-15-06-004Z_sw-90df758d-299e.jsonl`,
  entries 984–1005; receipts independently corroborated in JMS-134 report.
- Canonical repositories: appcore `git@github.com:jack-michaud/appcore` (fetch
  reviewed merges/tag, not detached local HEAD); jmos local repository
  `/Users/Jack/Code/github.com/jack-michaud/os` (board project `jmos`).

On Spark, corresponding board paths start `/home/jack/.herdr-projects/`:
`data/tasks/jack/5/task.json`, `data/tasks/pebble-index/1/task.json`,
`reports/jack/5/report.md`, `reports/pebble-index/1/report.md` and review artifacts.
Canonical source is `/home/jack/Workspace/pebble-index`; read `docs/api.md`,
`transcription_vocabulary.py`, `pebble_index.py`, `local_transcription.py` and
`tests/{vocabulary,transcription,acceptance,hardening,installer}.py` at the recorded
merge. Historical loopback report URLs and ephemeral test paths are not durable
cross-machine access routes. Do not copy private transcripts wholesale into Git.

## Acceptance checklist for the next authorized feature

- [ ] Owner request/permission, exact requirements, correct projects/machines,
  existing tasks and report discrepancies reconciled; no duplicate assignments.
- [ ] Actual worker programs and created/queued/started state verified; canonical
  contract, source hashes/commits and nonsecret handoffs recorded.
- [ ] Isolated sources and API-compatible dependency; both diffs/heads reviewed;
  required unit/contract/bridge/real-editor checks and skips documented.
- [ ] Changed-head, partial-merge, cleanup and uncertain-write cases covered;
  no secret leakage, implicit model choice or unapproved live operation.
- [ ] Merge → release → snapshot → install order proven independently, installed
  path/hash checked; recipient receipt not confused with delivery/execution.
- [ ] Live acceptance either evidenced or explicitly unverified with next owner;
  four-part progress baseline reconciled. No completion percentage/ETA invented.
- [ ] Reusable skill lives in managed source, loader metadata and documentation/
  distribution tests pass; source/review/merge/activation remain separate.

## Managed source and documentation checks

This directory is the one cross-project coordination skill. The case's server
and appcore skills are narrower implementation guides, not copies to install.
`../../../default.nix` (relative to this directory) enumerates skill directories for
Prime's automatic managed links. Only lavish-priorities-review currently has an
explicit neutral/Pi link; adding this source does **not** imply global Pi
activation. Do not broaden distribution, install a global copy, rebuild Nix,
reload Pi or change settings from this documentation task.

From this directory, with task-owned TMPDIR:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -v
PI_PACKAGE_ROOT=<installed-pi-coding-agent-package> node tests/test_skill_discovery.mjs
# From repository root, using the flake's already available nixpkgs:
nix eval --impure --json --expr 'let f = builtins.getFlake (toString ./.); in import ./modules/shared/dev/coding-agents/config/skills/cross-project-feature/tests/_test_distribution.nix { pkgs = import f.inputs.nixpkgs { system = builtins.currentSystem; }; }'
git diff --check
```

The loader test uses an isolated temporary home/project and the real installed
Pi loader; it validates frontmatter/discovery, not a running-session reload.
The Nix test evaluates the actual module with build primitives stubbed, like the
existing repository fixture: it checks this automatic Prime link and unchanged
neutral links/settings, not activation or a full host build. Documentation tests
check local references, unique metadata, evidence IDs and explicit delivery limits.
