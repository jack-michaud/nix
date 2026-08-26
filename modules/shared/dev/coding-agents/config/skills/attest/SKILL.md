---
name: attest
description: Produce signed, diff-bound attestations that a change was reviewed against its design document, passes the code-quality eval, and (advisory, not yet enforced) carries a PR description short enough that a human will read it, for the shipping path to require. Use before opening a non-draft PR or marking one ready for review, when jj-ship refuses a PR for a missing or stale attestation, or to audit which claims an agent has issued.
compatibility: Needs `git` on PATH. `design_reviewed()` needs a Linear API key (LINEAR_API_KEY or ~/.config/linear/api_key) only when `design_doc_id` is a Linear ID; a design doc that lives on disk (spec.md, proposal, exported lavish plan) is read directly. `description_humanized()` loads a humanizer module - ATTEST_HUMANIZER, an installed `humanizer`, or ~/.prime/agent/ceo-console/humanizer/humanizer.py - and degrades to a length-only claim when there is none. Key, log and thresholds live under ~/.prime/agent/ (override the directory with ATTEST_HOME).
---

# attest

Three verification functions. Each does real work, binds its result to the exact
diff it inspected, and returns an opaque token. `jj_ship` demands
`design_reviewed` and `eval_passed` before it will open a non-draft PR or mark
one ready; `description_humanized` is computed and logged on every run but is
**not required anywhere until an epoch is set** - see "Turning it on".

```python
tok_design = await attest.design_reviewed(
    repo=REPO, base="main", head="my-bookmark",
    design_doc_id="ENG-123",
    quote="The queue must release its slot when no announcement is eligible.",
    requirements=[("release the slot", "src/queue.ts:88")],
)
tok_eval = await attest.eval_passed(repo=REPO, base="main", head="my-bookmark")
tok_body = await attest.description_humanized(repo=REPO, base="main",
                                              head="my-bookmark", body=BODY)
BODY = tok_body.report["body"]   # post THIS text: the token binds its hash

`design_doc_id` names the design doc wherever it lives: a Linear ID (`"ENG-123"`)
is fetched from Linear; a path to an existing file — a `spec.md` in the repo, a
design proposal, an exported lavish plan — is read from disk with no Linear key
needed. The same checks apply either way: the quote must appear in the loaded
text, and every requirement must cite a path the diff touches.

await jj_ship.open_pr("Title", body=BODY, repo=REPO,
                      attestations=[tok_design, tok_eval, tok_body])
```

Attest **after committing**: `base`/`head` are git revisions, so the diff being
hashed is the committed tree jj is about to push, not the working copy. A
bookmark that only exists locally resolves fine; one that does not exist yet
raises and says so.

`repo=` may be a `jj workspace add` directory, which has **no `.git` at all**.
The git dir is found by following `.jj/repo` and then `store/git_target`, so
`git -C <workspace>` never runs - the same failure mode jj-ship documents for
`gh`, hit live from a real workspace while shipping this skill. A second diff
implementation (`jj diff`) is deliberately not used as a fallback: it would hash
differently for the same commits, and every mismatch would read as tampering.

A token is a plain `str`, so it drops straight into `attestations=[...]`. It also
carries what the verification found:

```python
tok_eval.report["comment_ratio_pct"]                       # what it counted
tok_eval.report["excluded"]["shebangs"]                    # what it did not
tok_design.report["doc"]["url"]                            # the document read
attest.decode(tok_eval)                                    # the payload
```

## What each function actually verifies

`design_reviewed()` fails, rather than returning a token, unless all of:

1. `design_doc_id` **is fetched from Linear** - the document must exist and be
   readable by this machine's key.
2. `quote` appears in the fetched text **verbatim modulo whitespace**. The
   description and every comment count, since design decisions land in the
   discussion as often as in the body. Re-wrapping is fine; paraphrase is not.
3. every `requirements` entry `("requirement text", "path/file.py:LINE")` names
   a path **the diff actually touches**. A requirement citing a file the change
   never opens is the usual shape of a claim written from memory.

`eval_passed()` scores the diff against thresholds and reports its exclusions
next to its counts:

| measure | rule | excluded |
| --- | --- | --- |
| `comment_ratio_pct` | comment lines added in PRODUCTION files, over production lines added, must be <= **3.0%** (`#` for py/nix/yml/sh/toml; `//`, `/*`, `* ` for ts/tsx/js/jsx/css/go/rs/java/c) | shebangs; every line in a test file |
| `patching_calls` | **zero** `monkeypatch.setattr/setenv/delattr/delitem`, `mock.patch(`, `MagicMock` added | `monkeypatch.chdir` and `syspath_prepend` - cwd and import-path plumbing, not reaching inside the unit under test; and every **mention** rather than call (see below) |

The comment ratio fails a diff only when **both** conditions hold: the ratio is
over 3.0% **and** more than `comment_lines_floor` (6) comment lines were added. A
ratio alone punishes exactly the changes worth making - a 38-line type-level diff
scores 10.5% for four defensible comment lines, which a 400-line diff would hide
at 1%.

Patterns are matched against each added line with its **comment and its string
literals removed**, so a documented or tested pattern is not read as a call. A
backtick counts as a quote: in every language scored here it is prose notation or
a JS template literal. What a per-line scan still cannot see is a plain
triple-quoted string, so an unbackticked pattern inside a docstring counts - named
here rather than hidden.

Only ADDED lines are measured: a change is judged on what it introduces, not on
what it happens to sit beside.

`description_humanized()` is about the text a human is asked to read. It scores
the description, rewrites it through the humanizer when it is over the line, and
binds the hash of the result. `tok.report["body"]` is the text to post - post
anything else and `jj_ship` refuses, because that is what "bound" means here.

| measure | rule |
| --- | --- |
| length | the description must be <= **6000** characters after any rewrite. Counted by attest itself from the text about to be posted, never read off the humanizer's own `metrics` |
| `slop_score` | the humanizer's 0..1 score (1 = worst) must be <= **0.5** |
| floor | under **800** characters a description is not scored, not rewritten and not flagged |

**This claim is ADVISORY by default and can refuse nothing.**
`description_claim_required_since` in the thresholds file is `null` out of the
box, so `required_claims()` returns the two older claims and a description
failure is recorded rather than raised. The reason is an open question, not
caution for its own sake: the scorer is deterministic and was calibrated so that
Jack's short prose scores low and #27's 13k scores high, which is also exactly
what a **length detector wearing a slop costume** would do. coding-evals is
fitting a length-only baseline against the same corpus to settle it. Until that
baseline FAILS to reproduce the ranking, this check must not be able to block a
ship on any machine. Read every `slop_score` below as "a number under test".

Advisory still means recorded. The score, the rewrite, the body hash and the
whole signal vector are computed and written to `attest.log.jsonl` on every run,
with `passed: false` on a failure - that log is the dataset the question above
will be answered from, and `verify()` refuses a `passed: false` token the moment
the epoch turns the claim on, so recording one lets nothing through.

The rewriter's own record of the run goes in beside it: `humanizer_run` is
`{attempts, succeeded, degraded, failures, duration_ms, attempted_at}` copied
through whole, and the payload carries a signed `degraded`. **True** means
inference was attempted and every attempt failed; **False** means it ran, or was
not needed; **None** means `humanize()` was never called - under the floor, no
humanizer, or already within the limits. A degraded run and an "already clean"
verdict produce identical text and mean opposite things, so the flag day needs
real degradation rates rather than a guess made from the text afterwards. Only
the keys named here are read, so the rewriter can add its own without breaking
this gate.

**When it IS required, the failure policy is: rewrite and proceed; refuse only
when a description needs a rewrite and cannot get one.** The other two claims
have no option but to refuse - nothing here can review a design or delete a patching call for you -
but slop has a mechanical fix, and a gate that blocks shipping over a defect it
could have fixed is a gate agents learn to route around. The tradeoff is real
and worth stating: an auto-rewrite means the text that ships is not always the
text the agent wrote, so the claim is only as good as the humanizer. That is why
the length limit is measured here and not delegated, and why the hash is taken
over the posted text rather than over "a description was humanized".

The two hard refusals are the cases where proceeding would be a lie: the rewrite
could not run, or it ran and the result is still over the line. Human-ack was
considered and rejected - an agent cannot wait on a human mid-ship, so an ack
prompt becomes a keystroke that always says yes.

| situation | what happens |
| --- | --- |
| the claim is advisory (the default) | every failure below is **recorded, not raised**: the token is issued with `passed: false`, the report names the failure, and nothing is blocked |
| under the 800-character floor | passes untouched and unscored. A short description is the goal, not the defect - this is the false positive that would cost most |
| no humanizer module anywhere | length is still checked here and the report says the claim covers **LENGTH ONLY**. Over the length limit with no humanizer **raises**: nothing left could fix it |
| humanizer raises (no inference, network down) | **raises only if the description was flagged.** One that needed no rewrite never needed the humanizer |
| the rewrite drops `Shipped-With:` | **raises,** and does not re-attach it. `ship-check` reads the PR body and nothing else, so a lost trailer silently breaks the attestation chain - and a humanizer that drops the one block it was told to carry verbatim is broken, which quiet repair would hide |
| the agent-authorship disclosure is missing | the line is **added**, before and after the rewrite. It is fixed boilerplate that cannot make the description claim anything new, and failing a ship over a missing constant is friction with no reader on the other end |
| the rewrite is still over the line | **raises,** naming both numbers. That is the signal to edit by hand, not to move the threshold |

### Turning it on: the epoch, and its hard precondition

`required_claims(at=None)` answers "which claims must a ship carry", and it
answers it for a MOMENT. `verify()` passes nothing and gets now; `ship_check`
passes the PR's `created_at`, so a PR is judged by what was required when it was
opened. That is not politeness to old work - both callers read the required set
at call time, so adding a claim to a bare tuple invalidates the trailer on every
PR already shipped, merged ones included, the instant the new code deploys. A
fleet outage with a delay fuse. jack-michaud/nix#27 is pinned as a test for
exactly this.

```json
{ "description_claim_required_since": null }            // never required
{ "description_claim_required_since": "2026-09-01T00:00:00Z" }
```

**Precondition, hard: the flag cannot be flipped anywhere until the humanizer
ships into this repo as a proper skill.** `humanizer.py` currently lives at
`~/.prime/agent/ceo-console/humanizer/humanizer.py`, which nix does not deploy.
On any machine without it a description over `description_chars_max` fails with
no fix available - the one refusal that cannot be worked around by rewriting.
Moving the humanizer into the repo is its own change and its own review; it is
deliberately not bundled with this one.

### Binding the claim to the body that is actually posted

`body_sha` is `sha256(canonical_body(text))`, and `canonical_body()` drops three
things and nothing else: the `Shipped-With:` trailer (jj_ship appends it *after*
this token exists - it names the token - so a hash covering it could never
match), `\r\n` (GitHub returns bodies CRLF-terminated and `mark_ready()`
re-posts what it read), and leading/trailing whitespace. `jj_ship` hands the body
to `attest.verify(..., body=...)`, which recomputes that hash at the moment of
posting; a body edited after attesting is refused with `the description
attestation is bound to a different body`.

**The ordering problem is real and is not solved by this.** A body can be edited
on github.com a minute after the PR opens, and nothing signed on this machine can
prevent that. What the binding buys is that the text that went *through* the gate
is pinned - in the payload and in `attest.log.jsonl` - so a later edit is one
`attest.body_matches(token, live_body)` away from being visible. Detection, not
prevention, the same deal as the diff binding.

All thresholds live in **one editable file**, `~/.prime/agent/attest-thresholds.json`,
which overrides the defaults embedded in `attest.DEFAULT_THRESHOLDS`:

```json
{ "comment_ratio_max_pct": 3.0, "comment_lines_floor": 6, "patching_calls_max": 0,
  "description_chars_max": 6000, "description_slop_score_max": 0.5,
  "description_short_chars": 800 }
```

An unknown key there is rejected loudly rather than ignored, because a silently
dropped threshold reads as "I relaxed the gate" while the gate never moved.
Inspect the current numbers, or a diff, without issuing anything:

```bash
attest --action thresholds
attest --action report --repo . --base main --head my-bookmark
attest --action humanize-report --body ./pr-body.md
attest --action check-body --token "$TOKEN" --body ./pr-body.md
```

`--body` naming an existing file is that file: a PR description is long enough,
and quoted enough, that passing it as an argv word is a mangling waiting to
happen.

## Token format

```text
base64url(json(payload)) + "." + hmac_sha256(key, base64url_payload)
```

`payload` is `{claim, diff_sha, repo, base, base_sha, merge_base, head, head_sha,
body_sha, doc_id, quote_sha, requirements_n, agent, ts, nonce}`. `body_sha` and
`passed` are set only by `description_humanized`; they are `null` rather than
absent on the other two claims, so an audit can tell "no body was measured" from
"this token predates the field". `passed: false` marks a claim issued while
advisory that did NOT pass - kept as evidence, and refused by `verify()` once the
epoch requires the claim. `base` is whatever the
caller named; `base_sha`, `merge_base` and `head_sha` are the commits that were
actually measured, so an audit of the log can tell the difference. The key is `~/.prime/agent/attest.key`, mode
0600, created on first use from `secrets.token_bytes(32)`.

`diff_sha` is `sha256` of `git diff <merge-base> <head>` **computed inside the
attest function and never accepted from the caller**.

**A base branch NAME resolves through `origin/<name>`, never a local ref.**
Resolving it locally is a false-attestation bug: a local `main` that is behind
the remote is still an ancestor of the feature branch, so the merge base is the
old tip and the diff quietly grows every commit other people merged in between.
That happened for real on fayhealthinc/fay-service#7373 - an eval scored 136
comment lines and 7 patching calls out of strangers' merged tests, and signed the
result - and it breaks the verify direction too, refusing honest tokens as
"bound to a different diff". So `_base_anchor()` fetches the single ref, resolves
`refs/remotes/origin/<name>`, and **raises** rather than guessing when origin is
configured but the ref will not resolve, or when the local branch has commits the
remote does not. A hex sha is taken as given; a repository with no `origin` at
all falls back to the local ref, since there is nothing for it to be stale
against. The diff flags
(`--no-color --no-ext-diff --no-textconv --unified=3 --find-renames`) are fixed
so a user's pager colour, difftool or textconv filter cannot change the bytes
being hashed.

Every issued token is appended to `~/.prime/agent/attest.log.jsonl`, one JSON
object per line, carrying the payload, the short `token_id`
(`sha256(token)[:12]`) and the full report. Logging never raises into the
caller: losing the log must not fail a verification that really passed.

## What this does and does not give you

**Binding.** The payload carries the diff hash, so a token stops verifying the
moment the code changes. Attest, edit one line, and `jj_ship` refuses with
`attestation is bound to a different diff - re-run the verification after your
last edit`. This is the property that makes "I reviewed the design" mean "I
reviewed *this* code" rather than "I reviewed something, once".

**Auditability.** The log records every issuance, including claims that were
made and then abandoned. `Shipped-With:` in the PR body records which token IDs
a PR was opened with, so a PR created outside this path is detectable from
GitHub alone.

**Not secrecy, and not unforgeability.** The agent runs as the same user as
`attest.key` and can read it. Anything that can read the key can mint any
payload it likes. So this is **tamper-evident, not tamper-proof**: it makes
skipping the work visible, not impossible.

The real defence is not the signature at all - it is that the verification
functions **do work that cannot be faked without doing it**. `design_reviewed()`
has to reach Linear, get the document, and find the quote in it; the requirement
citations have to name paths that are really in the diff. There is deliberately
no `doc_fetcher=` parameter, because a seam for injecting the document is a seam
for fabricating the review. `ATTEST_LINEAR_ENDPOINT` exists for the test suite's
stub server and is the one hole, named here rather than hidden.

### What the description check cannot detect

An honest list, because a gate that oversells itself is worse than no gate:

- **Slop, possibly.** This is the open one. The scorer may be measuring LENGTH
  and calling it slop; a length-only baseline is being fitted against the same
  corpus to find out (see above). Nothing here claims to "detect AI slop" as
  settled fact, and that is why the claim ships advisory.
- **Truth.** Nothing here checks that the description matches the diff. A short,
  plainly written, entirely false description passes.
- **Slop under the limits.** `slop_score` is the humanizer's heuristic, not a
  judgement. Text tuned to score well can still be padding, and the 800-character
  floor is a blind spot on purpose.
- **A rewrite that loses the point.** attest checks that the trailer survived,
  the disclosure is there, and the result is under the limits. It cannot tell
  whether the claim the rewrite dropped was the important one. Read
  `tok.report["body"]` before you post it.
- **A humanizer that lies.** The loader is a seam (`ATTEST_HUMANIZER`), unlike
  `design_reviewed()`, which deliberately has none, because here the humanizer is
  a tool rather than the evidence. A stub could score everything 0.0. What a stub
  cannot fake is length - that is counted here, over the text about to be posted.
- **Edits after posting.** Detectable via `body_matches()`, not preventable.
- **Anything that is not the body.** The PR title, review comments and commit
  messages all go unchecked.

## What dogfooding it on its own diff found

Pointing `eval_report` at the change that introduced it produced **12 patching
violations, not one of which was a patching call**: documentation prose naming
what the skill forbids, the detector's own regex literal, and test fixtures that
exist to prove the detection works. A detector that cannot tell a call from a
mention flags exactly the code most worth having.

That is a **detector** bug, and it was fixed as one - relaxing the threshold
instead would have hidden it behind a policy change:

1. patterns are matched after comments and string literals (backticks included)
   are stripped from the line;
2. files with no comment syntax this scorer understands are not scanned at all;
3. the comment ratio gained an absolute floor, so a small diff is not failed for
   a handful of defensible comment lines.

After the fix this change measures **2.93% (26 comment / 888 production lines
added), 0 patching calls - it passes its own gate.** Getting there also meant
cutting real prose from the module, which belonged in this file rather than in
banner comments; that is the gate working, not the gate being appeased.

The remaining known blind spot is an unbackticked pattern inside a triple-quoted
string, which a per-line scan cannot see. Every count is reported next to its
exclusions so a disagreement is about the evidence rather than the verdict.

## Tests

```bash
cd <this directory> && python3 -m unittest discover -s tests
```

No pytest, no network, no Linear account, no inference: the fixtures are real
git repositories in a temp directory, a real in-process HTTP server speaking
Linear's GraphQL shape, and real humanizer modules written to disk and loaded
through `ATTEST_HUMANIZER` - including three that fail the three ways a real one
can (drops the trailer, refuses to shorten, cannot run at all). That is deliberate - `eval_passed()` counts `mock.patch(`/`MagicMock` as
violations, so its own suite has to be able to pass its own gate.
