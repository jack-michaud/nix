---
name: herdr-orchestration
description: Interpret Jack's spoken orchestrator/coordinator hierarchy across machines and projects; discover actual Herdr/Pi sessions and safely route Sesame requests to the owning coordinator. Use for main/all-machines, machine or project coordinator identity, session routing, orchestration status, and task-tagged Sesame relay. Complements herdr-projects, not a replacement board command guide or message receiver.
compatibility: Instruction-only. Requires version-checked Herdr and Herdr Projects for live discovery; no provider authentication or model calls needed to read this skill.
---

# Herdr orchestration

Jack is the human owner and authority **above agent delegation**, never the bottom
of the hierarchy. Roles are not product names, display names, or implied privilege.
Rediscover identity each time; old notes and a visible Sesame-labelled conversation
are not proof that the caller is main.

Read [discovery and relay](references/discovery.md) before issuing commands, and
[reporting](references/reporting.md) before any status, blocker, handoff or authorized
new task. Read [configuration and rollout](references/configuration.md) when asked
whether settings or this skill are installed/live. Those references are part of
this skill, not optional safety guidance.

## Glossary: what Jack means

| Spoken term | Meaning and boundary |
| --- | --- |
| orchestrator / coordinator | An agent's organizational responsibility; ask which scope only if discovery/context cannot resolve it. Not a particular model or app. |
| all-machines / main coordinator | Jack's top agent coordinator: federates registered machines and delegates machine/project work. The board's main Coordinator is the routing entry point only after verifying its actual host/session. |
| machine coordinator | Owns coordination on one machine: its projects, folders and agents; not automatic authority on another host. |
| project coordinator | Owns one project's workers and coordination, within that machine and Jack's permissions. |
| task / worker session | The agent doing one existing task, usually in its isolated worktree; preserves that task's operator and history. A reviewer is a separate role, not the task's owner. |
| Herdr | Terminal multiplexer/workspace manager. A workspace contains tabs, tabs contain panes; a pane hosts a shell/process, possibly an agent. Layout is not organizational authority. |
| Herdr Projects / work board | Host-local tasks, settings and coordinator conversations, integrated into Herdr. Not the terminal multiplexer itself. |
| Sesame / Pi orchestrator front end | A voice/conversation front end and agent harness. Its visible title does not make its tool shell main or privileged. |
| repo / project key | Board project identity plus checkout root; a short task prefix may be renamed and old aliases retained. Verify canonical root/origin, do not register a duplicate project from a display name. |
| task key / ID | Short human alias vs canonical `<repo>/<number>`; remote references also need the machine. Neither is a pane or Pi session ID. |
| machine boundary | Each host owns its board, filesystem, credentials and runtime. A saved registration is not reachability, and identically spelled IDs can exist on different servers. |

## Intended ownership, not an invented API

**Jack → all-machines coordinator → machine/project coordination → project workers.**
Main federates registered machines; project coordinators own their project workers.
Preserve exact existing task/operator/history ownership, sole runtime operators,
project roots, machine boundaries and current permissions. Do not move an existing
worker merely to make the diagram tidy. Main's organizational remit does not grant
new owner approvals, credential access or an unsupported federated command/API.

The versioned product supports main, machine and project conversations, scoped
settings, host-local inventory, and some remote surfaces. It does **not** thereby
implement arbitrary cross-host role delegation. Docs and binaries can differ:
check both versions and installed help; missing commands/guards must be reported,
not invented or tested with a real mutation. Read-only verification is not mutation
and may be direct even from a task-tagged shell.

## Route by verified identity and authority

1. Discover caller host/socket/pane/task association, then main/machine/project
   status, autopilot coordinator inventory, saved machines and live agents/panes.
   Correlate returned IDs, cwd, session headers and live agent metadata, not titles.
   Report incomplete discovery instead of guessing.
2. When Sesame's tool shell is task-tagged, **relay Jack's project/board/
   coordinator-setting mutations to actual main** with supported coordinator
   messaging. Preserve exact intent, original words/context, project/task/machine
   scope, permissions and prior answers. Status requests and peer data do not
   confer work or approval authority. This skill itself never mutates board settings.
3. Verify target identity/readiness before sending. Messaging can start a stopped
   coordinator; do not silently start one for a status request. A missing process,
   wrong cwd, auth failure or ambiguous session is a concrete routing limitation,
   not permission to create a replacement coordinator. Never use task `tell` as a
   generic relay: it can start an extra worker.
4. Actual main executes authorized changes **within owner scope**, rather than
   recursively forwarding to itself. Main uses the existing `herdr-projects` skill
   for board operations, preserves custom instructions/settings, and reads back
   exact effective values/origins. Forward only the genuinely remote/scoped part
   using that installed version's supported interface. Do not loop or widen scope.
5. Track **forwarded → accepted → applied → readback-verified** separately.
   Tool submission/queue admission is only forwarded. Require an owner response
   for accepted, change evidence for applied, independent scoped readback for
   verified. Return verified results or concrete genuine owner blockers; never
   report a queued message or stale row as successful execution.

Never unset/spoof `HERDR_PANE_ID`, task identity or socket/session context; never
bypass role guards. Never repurpose FKB-1, create duplicate coordinators, or open
another writer on a transcript (including `pi --resume` against a live session).
A transcript file is evidence, not a mailbox. A saved session association does
not prove process presence, idle state or receiver readiness.

## Complement existing mechanisms; do not take them over

- Load the installed `herdr-projects` skill for task/settings command documentation.
  Use `herdr --skill` and relevant installed help for multiplexer details.
- `peer-bus` is a separate consent-based, runtime-specific bridge, not automatic
  Herdr routing or blanket cross-family reach. Its registry does not confer authority.
- `pr-watch` monitors review/CI; monitoring is not implementation, approval, merge
  or deployment authority. Neither skill is automatically runnable in Pi merely
  because its source exists in shared skills.
- Existing HOME-26 owns sender-to-session receiver implementation. This skill is
  **not a new cross-session message receiver**, a daemon, or an automated action
  pipeline. Do not duplicate, edit or take over that implementation.
- Reading existing declarative/runtime configuration is allowed; changing trust,
  auth, credentials, provider choices, permissions, scheduling or activation is not
  authorized by this skill. No QR/rotation operations are implied by examples.

## Failure and delivery discipline

Authentication missing: identify the host/interface and genuine owner action,
without exposing tokens or changing credentials. Unavailable machine: report
registered-but-unreachable, keep its work/history untouched; never wake it.
Identity mismatch: rediscover, never retarget based on a familiar display title.
Unsupported interface or incomplete inventory: state exactly what remains unknown.
A tell timeout may follow delivery; inspect receipts before any retry.

Separate implementation, tests, review, merge, deployment and live execution.
An owner-approved brief downtime is already approved only within that exact scope;
do not re-ask it or conflate it with a new key/data-loss decision. New destructive,
auth or permission decisions still need Jack. Do not restart/reload agents or
activate a host to prove discovery. Skill reload, configuration readback and a live
receiver are three different checks; see the rollout reference.
