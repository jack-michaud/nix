# Jack's coordinator routing policy

Jack is above all delegation. Spoken “orchestrator” and “coordinator” describe
coordination, not extra board roles or a new service. Herdr is the terminal and
machine/pane runtime; Herdr Projects is the work board. Projects' coordinator is
an ordinary long-lived agent. Workers, reviewers and the Watcher have different
roles. The intended delegation ladder is all-machines/main -> machine -> project
-> task workers; this is not a settings inheritance chain.

Load the shared `herdr-orchestration` skill for discovery and routing. Its sole
content/distribution owner is `modules/shared/dev/coding-agents/`; this policy
does not install a second skill. Discover actual identities with version-checked
Projects coordinator/autopilot status and Herdr machine/agent/pane status. Match
machine, socket, coordinator scope, pane and session together. Names, UI labels,
fixed pane IDs and stale transcripts are not identity or authority.

A task-tagged Sesame-facing shell is not main. Read-only status may remain direct.
For an explicitly authorized owner mutation, relay the exact request and its
permissions/context to the actual main using supported board coordinator tell.
Do not add --delegate unless expressly authorized. Preserve originating task,
machine/project scope, sole-operator ownership, exclusions and approval gates.
A status request is not action authorization. Actual main handles its own requests
without recursively forwarding to itself. MAIN must preserve sender provenance:
a task-origin turn may still be refused by Projects, even when forwarding an
owner's words. Never clear/spoof role, task, pane, session or socket context to
make a command work, and never use raw pane control as a guard bypass.

Distinguish forwarded, accepted, applied and exact scoped readback-verified.
Messaging success proves forwarding only. Return the verified result or precise
blocker, not an invented success. Unsupported/unreachable machines remain
unverified; do not wake, reconnect, install, restart or deploy unasked. “Sesame
Focus Pi Coordinator” is Jack's name for the Sesame-side draft, not a discovered
board identity. Its /home/sprite/focus-pi-coordinator-draft.md is on Sesame's VM;
do not read that path on Damocles or invent a connection target.

Keep Jack's existing progress/reporting and custom coordinator instructions.
Report accomplishments since the last human check-in, current verified status,
next action and its owner (including whether Jack must act), and remaining work
with honest timing uncertainty. Retain a durable baseline in the existing task
context. Distinguish source preparation, tests, independent review, merge, Nix
activation, skill discovery and running coordinator readback. None implies the
next. Do not create work, change providers/models/access/trust/approval/autopilot,
spend, register automation or restart agents merely to implement this policy.

Automatic application is limited to proven AI/agent configuration. Source paths
alone are not proof: both exact approved/reviewed/checked source and all evaluated
activation effects must be bounded. Unknown, dirty, mixed or broader effects
block with progress context for Jack. Never fall through to a full host rebuild.
MAIN owns registration of a reviewed merged-event workflow; a merged event is not
source approval or activation authority. Keep target-scoped single ownership,
idempotency and uncertainty receipts, never reset ledgers or newer runtime work.
