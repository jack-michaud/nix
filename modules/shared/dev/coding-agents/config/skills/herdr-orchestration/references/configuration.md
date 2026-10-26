# Read configuration; distinguish rollout stages

## Ownership and read-only inspection

Canonical source: `/Users/Jack/.config/dotfiles` resolves to
`/Users/Jack/Code/archive/nix`, origin `git@github.com:jack-michaud/nix.git`.
Use the board-provided isolated worktree for source changes, not Jack's checkout;
leave unrelated local edits/history untouched. Verify these paths on the host
before relying on them. Never move/register a replacement repo from an old skill's
outdated default path.

The shared source is
`modules/shared/dev/coding-agents/config/skills/herdr-orchestration/SKILL.md`;
distribution is `modules/shared/dev/coding-agents/default.nix`. Existing Prime
fan-out remains. `modules.dev.coding-agents.enable = true` enables the module;
`modules.dev.coding-agents.piSkills` selects shared Pi skills and defaults to
`[ "herdr-orchestration" ]`. A host can use `[]` to opt out. This avoids publishing
all Prime Python/runtime-specific skills or shadowing other installed copies.

Prime and Pi destinations share the same store-backed **live source symlink**:
`~/.prime/agent/skills/herdr-orchestration` and
`~/.pi/agent/skills/herdr-orchestration`. Pi's native discovery directory is the
only Pi mechanism here: no parallel `.agents/skills` copy, package install or
mutable Pi settings edit. A source edit after deployment changes that live target;
adding the destination to Home Manager still requires reviewed rollout. Host-local
source and symlinks must exist; a store symlink alone is not a portable bundled skill.

Read the existing declarative Herdr module under `modules/shared/shells/herdr/`
and its own docs before explaining its settings/helper interface. Declarative
Projects settings/helper/workflow/gate ownership is separate (FLS-4); do not copy
its implementation into this skill or assume sibling unmerged code is installed.
Read runtime effective settings through version-supported board `show` and
coordinator/autopilot status. Settings live under the board's own home (usually
`~/.herdr-projects/settings/config.json`); runtime tasks/conversations remain under
its data tree. Do not dump secret-bearing files or overwrite the mutable tree.
This skill explains/reads configuration and routes requests; **it does not mutate
board settings** or invoke an apply helper.

Jack's narrowly approved automatic-application policy is **only AI/agent
configuration** (`.agents`, `.pi`, Herdr Projects). FLS-4 owns the declarative
workflow and deny-by-default gate, examining **both Nix source and generated
activation effects**. Mixed, unknown, host, service, package, credential or restart
effects block for Jack. The preserved Prime fan-out adds a `.prime` destination;
do not assume that destination qualifies for a `.agents`/`.pi`/Projects allowlist.
Unknown/out-of-scope effects must block. A shared module pathname alone proves no safe impact.
This policy does not authorize this skill to run a rebuild, create an automation,
activate a host or duplicate that gate. No circular dependency or repeated scope
question is needed; supply source/effect/host evidence to the owning workflow.

## Evidence ladder (never collapse these stages)

1. **Fixture/isolated discovery:** installed Pi loader parses the exact skill and
   finds it via a simulated native user directory, without a model call/provider
   auth. Check diagnostics, collisions, resolved paths and broken symlinks.
2. **Source-ready / PR-reviewed:** committed source and passing tests/evaluation
   are distinct from board review and merge. Quote real output/commit, not a
   fabricated passing host activation. Follow the task's git/PR ownership rules.
3. **Current-machine installation:** after authorized reviewed rollout, inspect
   the exact Home Manager/store/live symlink chain and run installed loader
   discovery against the real configured locations. Existing settings can exclude
   a resource or introduce name collisions. Never force-overwrite a destination.
4. **Current-running-session reload:** a new session scans at startup; Pi supports
   `/reload` for resources. Only the actual session owner should reload an active
   conversation at an appropriate boundary. A fixture load is not a live reload,
   and `/reload` does not start or prove readiness of an external message receiver.

Do not claim global availability merely because SKILL.md exists in the repo.
Record canonical source, installed path (if any), resolved target, loader version,
diagnostics and rollout limits in the task's normal report folder. If installation
or reload remains, name the exact remaining step and known owner with evidence.
Do not silently restart workers, run a darwin/home-manager switch, change trust or
auth, deploy cloud services, wake unreachable hosts or install sibling work as merged.

## Product checks

See the coding-agents module README for repeatable tests. They use installed Pi's
exported loader in isolation, lint safety/reporting content, check the installed
CLI's advertised syntax without sending a message, and evaluate real Nix host
attributes. A negative fixture checks collisions/broken links because Pi may
silently skip a broken directory symlink. No tests send operational QR/rotation
requests, start a worker, or modify board settings.
