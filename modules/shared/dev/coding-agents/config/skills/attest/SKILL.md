---
name: attest
description: Produce signed, diff-bound attestations that a change was reviewed against its design document and passes the code-quality eval, for the shipping path to require. Use before opening a non-draft PR or marking one ready for review, when jj-ship refuses a PR for a missing or stale attestation, or to audit which claims an agent has issued.
compatibility: Needs `git` on PATH. `design_reviewed()` additionally needs a Linear API key (LINEAR_API_KEY or ~/.config/linear/api_key), because it fetches the design document. Key, log and thresholds live under ~/.prime/agent/ (override the directory with ATTEST_HOME).
---

# attest

Two verification functions. Each does real work, binds its result to the exact
diff it inspected, and returns an opaque token that `jj_ship` demands before it
will open a non-draft PR or mark one ready.

```python
tok_design = await attest.design_reviewed(
    repo=REPO, base="main", head="my-bookmark",
    design_doc_id="ENG-123",
    quote="The queue must release its slot when no announcement is eligible.",
    requirements=[("release the slot", "src/queue.ts:88")],
)
tok_eval = await attest.eval_passed(repo=REPO, base="main", head="my-bookmark")

await jj_ship.open_pr("Title", body=BODY, repo=REPO,
                      attestations=[tok_design, tok_eval])
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

Both thresholds live in **one editable file**, `~/.prime/agent/attest-thresholds.json`,
which overrides the defaults embedded in `attest.DEFAULT_THRESHOLDS`:

```json
{ "comment_ratio_max_pct": 3.0, "comment_lines_floor": 6, "patching_calls_max": 0 }
```

An unknown key there is rejected loudly rather than ignored, because a silently
dropped threshold reads as "I relaxed the gate" while the gate never moved.
Inspect the current numbers, or a diff, without issuing anything:

```bash
attest --action thresholds
attest --action report --repo . --base main --head my-bookmark
```

## Token format

```text
base64url(json(payload)) + "." + hmac_sha256(key, base64url_payload)
```

`payload` is `{claim, diff_sha, repo, base, base_sha, merge_base, head, head_sha,
doc_id, quote_sha, requirements_n, agent, ts, nonce}`. `base` is whatever the
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

No pytest, no network, no Linear account: the fixtures are real git repositories
in a temp directory and a real in-process HTTP server speaking Linear's GraphQL
shape. That is deliberate - `eval_passed()` counts `mock.patch(`/`MagicMock` as
violations, so its own suite has to be able to pass its own gate.
