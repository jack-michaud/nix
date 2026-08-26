---
name: ship-check
description: Verify that a pull request carries a `Shipped-With:` trailer whose attestations actually validate - reading the PR body only, never its comments - and check each PR URL at most once ever. Use when a PR URL arrives from another agent, when auditing whether a PR went through the shipping gate, or when a trailer looks present but you need to know it is real.
---

# ship-check

Answers one question about a pull request, from its URL alone: **does its body
carry attestations that still hold?** A matching string does not count. The
trailer names attestation ids; each id has to resolve to a real issued claim in
`~/.prime/agent/attest.log.jsonl`, the claims have to cover every one of
`attest.required_claims(at=<the PR's created_at>)`, and each one has to still
bind to the diff the PR shows right now.

```python
verdict = ship_check.verify_pr("fayhealthinc/fay-service", 7373)
verdict["ok"], verdict["reason"]

result = ship_check.check_message(inbound_message_text)   # once per PR URL, ever
result["failures"], result["notice"]
```

## What fails, and why each case is deliberate

| Case | Verdict |
| --- | --- |
| No `Shipped-With:` line in the body | fail |
| The line appears only in a **comment** | fail |
| An id with no issuance record (forged, or typed by hand) | fail |
| Only one of the claims required when the PR was OPENED | fail |
| Attestation issued for a different head or base branch | fail |
| Attestation bound to an older diff than the PR now shows (stale trailer) | fail |
| Anything that cannot be established | fail, with the reason |

**The required set is resolved from the PR's `created_at`, not from now.** This
module and `jj_ship` both read it at call time, so a claim newly added to
`attest` would otherwise fail the trailer on every PR already shipped - merged
ones included - the moment the new code deployed. `attest.required_claims()`
takes an epoch for that reason, and jack-michaud/nix#27 is pinned as a
regression test: a two-claim trailer from before the epoch still verifies.
`verdict["required"]` reports the set that was applied.

**The body only, never comments.** An agent explaining the format in a review
comment - or quoting a trailer verbatim in prose - must not thereby pass. This
is not hypothetical: an agent deliberately avoided writing the literal prefix in
a PR comment for exactly this reason, and was right to. `jj_ship` writes the
trailer into the body and nowhere else, so the body is the whole universe of
legitimate trailers.

**Unverifiable is a failure.** The point is to notice a PR whose gate was
skipped; a check that shrugs when the evidence is missing notices nothing.

## Once per PR URL

`check_message()` records every URL it has checked in
`~/.prime/agent/ship-check.state.json`, under a lock and written atomically, so
"maximum 1 time for each PR URL" holds across processes and across restarts.
`ship_check.forget(url)` drops a record; `--force` on the CLI ignores them.

## What this is and is not

The `ship-check` **extension** (`config/extensions/ship-check`) runs this on
inbound agent messages. Label it precisely:

- **A gate on what the orchestrator's model reads.** It runs in `pi.on("context")`,
  whose return value *is* the message array sent to the provider, so the model
  cannot read a child's "here is my PR" without also reading the verdict. No
  instruction is involved in that half.
- **Not interception at delivery.** There is no inbound-agent-message hook in
  prime-agent: delivery goes through `AgentSession.acceptAgentMessagePrompt()`
  with `skipInputHandlers: true`, so the `input` event - the only hook that can
  transform or swallow a submission - never fires, and the queued path does not
  normalize at all. The raw message is still persisted and visible in the TUI.
- **Not fail-closed.** `emitContext` swallows a throwing handler and continues
  with the messages untouched. The handler therefore catches its own errors and
  writes a visible "the check itself failed - treat every PR URL above as
  UNVERIFIED" marker into the context, but a hard crash of that file leaves the
  gate off.
- **The remediation is an affordance, not a gate.** An extension cannot send an
  agent message (`agent_message.send` is an rlm kernel `host_request`, and
  `ExtensionAPI` has no cross-session send), so the injected text names the exact
  `agent_message.send(...)` call to make to the worker. The orchestrator can
  decline.

## CLI

```sh
python3 -m ship_check --pr https://github.com/o/r/pull/1
python3 -m ship_check --message-file /path/to/message.txt   # what the extension calls
python3 -m ship_check --message-stdin --force
```

Exit status is 0 whenever the check ran, including when it failed the PR: read
`failures`. A file as well as stdin because `pi.exec`'s options have no stdin.

## Tests

```sh
cd config/skills/ship-check && uv run --with pytest python -m pytest tests/ -q
cd config/extensions/ship-check && node test.mjs
```

Real fixtures throughout: a git repository with a real remote, tokens really
signed by `attest` against its real diff, a real `gh` executable on disk, and a
fake `pi` that really spawns the Python checker. Nothing is mocked, so the suite
can pass `attest`'s own eval.
