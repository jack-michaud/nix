# Supported contracts and private journal

## Version checks, not historical API folklore

Before use, read installed generic skills and matching playbooks, run
`lavish-axi --version`, `lavish-axi --help`, `lavish-axi poll --help`,
`herdr-projects version` and current board help. Locate the installed packages
with the executable/package manager, not a baked-in personal path. Read applicable
board other-machines/roles docs. If help/source differs from a skill, verify the
actual installed contract; owner authority still overrides tool suggestions.

Verified implementation baseline: Lavish 0.1.46, board 1.2.26, Pi 1.4.0.
These are observations, not requirements to download/update anything.
Supported Lavish operations:
- `lavish-axi FILE` opens a session; retain actual returned ID/URL.
- `lavish-axi poll FILE` waits for submitted prompts or end.
- `lavish-axi poll FILE --agent-reply TEXT` replies then waits.
- `lavish-axi end FILE` agent-ends. No standalone reply/disconnect-grace CLI was
  verified at this baseline. Historical next_step prose is not an API contract.
- State/port/host environment: `LAVISH_AXI_STATE_DIR`, `LAVISH_AXI_PORT`,
  `LAVISH_AXI_HOST`. Isolate task-owned resources, default loopback.
- Current layout issues are passive until the user queues them, not automatic
  authorization to edit. Fatal `artifact_failures` can return without user action.
- `session_ended` and `ended_by` are source end fields when returned.
  User end forbids uninvited reopen. Do not use `--reopen` here.

Installed source evidence: Lavish `dist/cli.mjs` functions `pollCommand`,
`createPollOutput`, `takeFeedback`, and CLI help. `takeFeedback` consumes before
CLI delivery: raw capture cannot guarantee lossless transport. No ACK/replay or
transactional coordinator idempotency interface was verified.

Board `coordinator tell TEXT` goes to main; `coordinator --machine tell TEXT`
and `coordinator --project REPO tell TEXT` are distinct routes. Verify the actual
authorized one. Do not infer MAIN authority just because it is a default.
No `--delegate` in the helper. No fallback after a role/permission refusal.
No coordinator acceptance, application or verification is inferred from exit 0.

## Identity and storage

All paths are resolved relative to the installed skill for scripts/assets.
Keep identity, normalized inputs, report, raw feedback and journal in the
invoking task's authorized private report area, outside Git. Temporary projects,
test homes, browser profiles and servers use that task's TMPDIR. One canonical
journal per session, on the designated machine; no second root to bypass locking.

Use trusted existing private ancestors. Helper journal root must be a new
owned 0700 directory (helper creates it); files are exclusive-create 0600,
no final symlink/hardlink traversal, locking and atomic fsynced replacement.
OS advisory locks are local POSIX locks, not cross-machine leases or a security
sandbox. Trusted parent directories and the invoking agent remain an explicit
boundary. Do not put this in shared writable paths. Corrupt/unknown schema,
changed identity/scope/route or unsafe files fail closed; do not delete the
journal to bypass a hold.

Create a private identity JSON with exactly these fields, replacing placeholders
with actual verified values, never guessed IDs/URLs:

```json
{
  "taskId": "<invoking task>",
  "sessionId": "<returned session ID>",
  "canonicalArtifactPath": "<absolute existing task-owned HTML file>",
  "reviewUrl": "<returned private URL>",
  "urlLocality": "<loopback-only or separately authorized protected route>",
  "machine": "<socket.gethostname() on designated poll machine>",
  "coordinatorRoute": ["main"],
  "authorizedScope": "<exact owner-authorized area and relay scope>",
  "role": "review-worker",
  "cliVersions": {"lavish": "<observed>", "board": "<observed>"},
  "resourceOwnership": {"evidence": "<state dir, port, process and session ownership>"},
  "lavishExecutable": "<absolute installed CLI executable>",
  "boardExecutable": "<absolute installed board executable>",
  "pollEnv": {"LAVISH_AXI_STATE_DIR": "<task-owned absolute isolated state dir>", "LAVISH_AXI_PORT": "<verified owned port>", "LAVISH_AXI_HOST": "127.0.0.1"}
}
```

Route may instead be `["machine"]` or `["project", "<repo>"]` only with actual
authority. Identity is pinned in state; supply the same identity file on every
command. The identity file is operator input, not sourced from feedback.
The helper validates shape/scope equality, not whether an owner truly granted
authority. Agents must establish that from the task/owner before initializing.

```sh
python3 scripts/review_state.py --journal "$JOURNAL" --identity "$IDENTITY" init
python3 scripts/review_state.py --journal "$JOURNAL" --identity "$IDENTITY" capture
python3 scripts/review_state.py --journal "$JOURNAL" --identity "$IDENTITY" status
```

Capture prints a local capture ID, not a source submission/message ID. It
persists running intent and captures raw stdout/stderr before interpretation.
A held poll lock is inherited by the child; parent SIGKILL cannot permit another
helper poll while that child survives. SIGTERM/interrupt stops ONLY its child,
waits/reaps it and flushes capture files. Abrupt machine failure can still leave
an incomplete raw file. Never equate an interrupted capture with no feedback.

## Normalization trust boundary

The helper deliberately does NOT parse version-varying TOON/JSON responses.
Read full raw capture and current installed contract. Extract exact prompt
strings into normalized JSON, then ingest only a completed exit-0 capture.
Unknown/partial/unsupported formats are held, not guessed. Preserve full raw
output, including unhandled prompt types, layout/fatal data and end fields.
A raw hash binds the extraction to evidence; it does not mechanically prove
the extraction is correct. Agent extraction is an explicit trust boundary.

Normalized JSON has exactly these fields:

```json
{
  "sessionId": "<same returned session ID>",
  "captureId": "<local completed capture ID>",
  "rawSha256": "<SHA-256 of full captured stdout bytes>",
  "formatVerified": "<observed CLI version and extraction/source evidence>",
  "prompts": [{
    "exactPrompt": "<exact submitted text, no trim or whitespace normalization>",
    "sourceIds": {"submissionId": null, "messageId": null},
    "sourceTimestamps": {"submittedAt": null}
  }],
  "sessionEnded": false,
  "endedBy": null,
  "fatalFailure": false
}
```

Empty prompts is valid only when that matches the real response. Source values
are exact strings or null. Do not promote DOM `uid` to a message ID. Other
returned provenance can be named in these maps, including a separately labelled
stored-chat timestamp; never substitute a local time for an absent server time.
An end with missing attribution is sticky `ended-by-unknown`.

```sh
python3 scripts/review_state.py --journal "$JOURNAL" --identity "$IDENTITY" ingest "$NORMALIZED"
```

State schemaVersion 1 stores identity, lifecycle, pollOwner (machine/task/PID/token),
captures and hashes, feedback keyed by exact session-NUL-prompt digest,
immutable raw/normalized observations, local times, relay envelope/intent/receipt,
acceptedEvidence, appliedEvidence, verificationEvidence, executedActions,
artifactRevision/replyState, latestAnswerRefs, checkInBaseline, artifactRevisionHash
and recovery/end events. Duplicate observations append provenance without
re-forwarding or regressing evidence. IDs/times are not fabricated.
Normalization is exclusive-create; after a crash only identical bytes may be
reingested. Reordered end remains sticky.

## Relay and evidence commands

Context JSON must contain exactly `requestedScope` (equal to authorizedScope),
`requestContext`, `priorAnswerRefs` (array) and `authorizationEvidence`.
Scope includes the actual request, prior answers and limits, not a blanket
instruction to start everything in the report.

```sh
python3 scripts/review_state.py --journal "$JOURNAL" --identity "$IDENTITY" relay "$DIGEST" "$CONTEXT"
```

This explicitly sends one contextual envelope through the pinned supported
coordinator route using argv (never shell-interpolated feedback). It durably
reserves intent first. Receipt records actual stdout/stderr bytes as hex plus
readable text/exit/local time. Successful exit records `forwarded-cli-accepted`,
not coordinator acceptance. Nonzero, timeout, crash or missing receipt is
`delivery-uncertain` (a crash may leave `intent` until recovery).
No retry command: even a crash before send requires reconciliation, not an
automatic resend. Preserve returned receipt exactly; don't invent external IDs.

Append independently sourced evidence with `record DATA_JSON`:
`{"digest":"<digest>","field":"acceptedEvidence","evidence":"<actual source>"}`.
Allowed feedback fields: acceptedEvidence, appliedEvidence, verificationEvidence,
executedActions, artifactRevision, replyState. These are assertions WITH source,
not helper-executed actions. With digest null, session fields are
latestAnswerRefs (append history; explicitly mark supersession/order),
checkInBaseline and artifactRevisionHash. Do not silently reorder answers.

After actual same-review changes and only while open:
`capture --reply-file PRIVATE_UTF8_FILE` invokes supported agent-reply poll.
Exact reply hashes cannot be attempted twice, including after interruption;
reconcile uncertain delivery manually. A completed poll is not reading evidence.

## Recovery, error and end semantics

Run `recover --evidence TEXT` only after inspecting raw/session state, matching
ownership and deciding how to hold the incomplete/unprocessed results. It must
acquire the poll lock, marks outstanding captures held, converts relay intent to
delivery-uncertain and records recovery evidence. It never retries a relay,
replies, reopens, deletes evidence or clears an end/fatal failure. An interrupted
or killed poll must be recovered before another capture. If raw data is complete
but exit/finalization is missing, preserve it and reconcile manually rather than
pretend the helper safely normalized it. Unprocessed successful output should
normally be ingested; recovery is an explicit audited hold, not silent discard.

Unknown formats/corruption/fatal review failures: hold and repair only with
verified source evidence. Browser disconnect behavior must be rechecked for
the installed version. Do not automatically end/reopen. Poll timeouts and
consume-before-delivery have no proven lossless recovery API.

`end-observed --by user|agent --evidence TEXT` records an actual externally
observed end; it does not end a live session itself. End is sticky; user end
cannot be downgraded by delayed events or an agent-end call. Normalized final
feedback can still be relayed once after end, but capture/reply are forbidden.
No helper command shuts down a server or executes selected product work.

Keep original private wording unchanged. Redact only derived human reports
where necessary, not raw evidence under its old filename. Store no secrets or
personal inventory in this distributed directory. Preserve journals/URLs under
the board/owner's existing retention lifecycle; no invented expiry, cleanup
daemon or automatic deletion. Task-owned temporary resource cleanup remains the
invoking task's responsibility.

## Discovery and isolated checks

Pi documentation: installed `docs/skills.md`, `docs/packages.md`,
`docs/settings.md`, `docs/configuration.md`, `docs/security.md`,
`docs/sdk.md` and `examples/sdk/04-skills.ts`. Installed
`dist/core/package-manager.js` discovers neutral `~/.agents/skills`;
`skills.js` follows symlink directories, deduplicates real files and diagnoses
name collisions. This module adds just this one neutral link; existing Prime
enumeration stays unchanged. No archived/unmerged distribution is assumed.
A passing isolated loader is not activated global availability.

Tests run without network/models, real poll events or coordinator sends:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -v
PI_PACKAGE_ROOT="<absolute installed pi-coding-agent package>" node tests/test_skill_discovery.mjs
nix-instantiate --eval --strict tests/_test_distribution.nix --arg pkgs '(import <nixpkgs> {})'
```

The Nix fixture starts with an underscore because this repo recursively imports
non-underscored .nix files as host modules. It must never be an activation module.
The Nix test needs the repo's pinned nixpkgs if no NIX_PATH exists; supply
`--arg pkgs` from the current flake input. It imports the real coding-agents
module with narrow stubs, asserts generated effects/unchanged Prime and disabled
behavior, not a host activation. Also run repo Nix parse/flake checks and the
host no-link build where feasible. Record actual limits/failures. All temporary
homes live under TMPDIR; no settings/trust edits, installs, full switch/rebuild or
running-session reload. Review exact committed head before normal board PR flow.
