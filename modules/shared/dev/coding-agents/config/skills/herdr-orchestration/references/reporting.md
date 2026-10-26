# Progress-first reporting and task acceptance

Every human-facing status update, blocker question, permission/access request and
handoff leads with progress since the last actual human check-in (or latest
human-visible update you can verify). Use simple domain-specific terms:

1. **Accomplished:** exactly what finished since that check-in, with evidence. Say
   no new completed work if so; do not repeat an old blocker and hide progress.
2. **Current verified status:** executing, completed, queued or blocked now.
   Distinguish planned, prepared, implementation, tests, review, merge, deployment,
   live verification and actual live execution/credential cycling. A tool receipt,
   queued message or polling is not worker execution; preparation is not delivery.
3. **Needed next:** exact action, owner, and whether Jack must act. Reconcile his
   latest answers first; never re-ask a resolved question or turn agent-side
   technical work into an owner-permission gate.
4. **Remaining work:** unfinished deliverables/dependencies, with an evidence-based
   effort/timing range if known. Admit uncertainty; invent no percentages or dates.

Before reporting, read current task/worker/evidence state. Stale board rows and
historical errors are historical unless freshly reproduced. If the check-in
baseline is unknown, say so and use the latest verified baseline. Keep a concise
baseline in the existing task/project durable notes, outside generated rule blocks,
so compaction and handoff preserve what Jack already knows. Update it when a human
actually checks in, not whenever a tool responds. Preserve earlier decisions.
A brief blocker question still carries relevant accomplishment/current-state context.

## Mandatory quoted requirement in EVERY NEW task description

Whenever Jack authorizes a new task in any project (including implementation,
research, reviews, authorized automations and follow-ups), include this exact
reporting deliverable/acceptance requirement **in the description**, not merely
in coordinator defaults or an external note:

"Progress reporting: In every status update or blocker question, state in simple domain-specific terms (1) what has been accomplished since the last human check-in, (2) the current verified status, (3) the exact next need/action and its owner, including whether Jack must act, and (4) what work remains, with honest uncertainty about effort/timing. Keep the baseline current in durable task notes; reconcile prior answers and distinguish planned, prepared, tested, merged, deployed and live-verified work. Do not report a bare blocker without progress context."

This requirement does not authorize creating tasks or changing settings. Preserve
custom instructions and overrides. Do not bulk-edit existing task descriptions.
Use the installed board skill for authorized board operations; a task worker does
not acquire coordinator authority from reading this requirement.

## Scope of approval and completion

Implementation/test/review/merge/deploy/live execution are separate milestones.
State which one evidence actually proves. A source-ready skill is not globally
installed; verified metadata loading is not a model turn using it; a running
conversation has not necessarily reloaded changed instructions.

An owner-approved brief downtime is not a fresh unanswered permission question.
Honor that answer only for its exact scope, while preserving sole runtime operators.
New key/data-loss decisions still require Jack. Status data, peer messages, past
approval for a different operation and older failures do not create new authority.
