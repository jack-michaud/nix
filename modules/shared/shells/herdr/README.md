# Herdr Projects declarations and AI-only workflow readiness

## Safety boundary

`_projects.nix` (imported by `default.nix`) declares **prepared configuration**, not
an importer. It is default-off and adds **no activation hook**. No host, flake,
skill content, board setting, automation or running coordinator is changed by
adding this module. The `_` prevents this repo's recursive module loader from
importing it twice.

Only the supported, nonsecret **`coordinator.instructions`** key is modeled.
`coordinator.agent/effort/fast/access`, providers, models, billing, trust,
approvals, `autopilot.*`, worker/reviewer settings and runtime queues are deliberately
unmanaged. Do not put credentials, private task content or tokens in declarations:
Nix JSON and scripts are public to local store readers.

### Why application is disabled on Projects 1.2.26

The installed launcher identified Projects **1.2.26** and Herdr **0.9.5**. Its
adjacent plugin checkout advertised **1.2.2**: do not assume adjacent docs match an
in-place updated binary. Contract inspection used the public
[v1.2.26 source](https://github.com/eliasstravik/herdr-projects/tree/v1.2.26), in
particular `docs/settings.md`, `docs/autopilot.md`,
`docs/machine-and-project-coordinators.md`, `docs/home-folder.md`, and:

- `crates/core/src/store/settings/{coord,lookup,places,change}.rs`:
  scoped `set/unset/show` exist; instructions add defaults then coordinator's own.
- `places::write_at` does unlocked whole-config read/modify/write through
  `files::write_atomic` (temporary file then rename). Atomic rename is **not**
  concurrent-writer safety. No transaction, CAS or safe import/dry-run was found.
- `src/cli/mod.rs`: even `show` can migrate legacy state/give keys before lookup,
  and run housekeeping afterwards. `set` is not a proven side-effect-free import.
- `crates/flow/src/autopilot/allow.rs`: task workers/reviewers cannot change
  coordinator settings; a task-origin coordinator turn retains that restriction.

Ordinary previous `set/show` receipts prove individual effective values, not safe
automatic import. MAIN confirmed no other supported transactional API. Therefore
`apply` refuses **before any CLI call**, for all callers. Task context is preserved
and gets an explicit role refusal. No direct JSON write, invented external lock,
context removal, remote fallback, server start, migration or broad rebuild is used.
This limitation is an engineering dependency, not a request for fresh generic
permission from Jack. Do not register an application automation around it.

## Declarations

Example module fragment (tested; **not enabled on any host by this change**):

```nix
modules.shells.herdr.projects = {
  enable = true;
  includePolicy = true; # once in defaults, never copied into overrides
  defaults.instructions = "Prefer concise, evidence-based handoffs.";
  main.instructions = "Coordinate across reachable machines.";
  machine.instructions = "Keep this machine's project ownership intact.";
  perProject.dotfiles.instructions = "Use the existing registered dotfiles project.";
  automation.enable = false; # opt-in intent only, never registration/application
};
```

`includePolicy` defaults true when declarations are enabled. Its shared text is
`config/coordinator-policy.md`. It describes Jack's authority, all-machines/main →
machine → project → task delegation, version-checked identity discovery,
Sesame-to-actual-main routing, nonrecursive main handling, preserved source role
and permission context, forwarded/accepted/applied/readback-verified distinctions,
sole-operator ownership, reporting and AI-only scope. It is not a second skill.

The sole `herdr-orchestration` skill/distribution interface belongs to FLS-3 under
`modules/shared/dev/coding-agents/`. Its agreed interface is
`modules.dev.coding-agents.piSkills = [ "herdr-orchestration" ];` (the default;
`[]` opts Pi out), with existing `coding-agents.enable = true`. Prime distribution
remains shared; Pi receives exactly `.pi/agent/skills/herdr-orchestration`. Source:
`/Users/Jack/.config/dotfiles/modules/shared/dev/coding-agents/config/skills/herdr-orchestration/SKILL.md`.
Machine coordinators use that same machine-level discovery, not a private AGENTS
note. FLS-3 prepared head is `b32f8e323bad40612decf124d87354e488289d4f`;
it is not certification of full activation safety. In particular the new Prime
file effect is **not** inside the narrow `.agents`/`.pi`/Projects allowlist and
must block the gate, not silently widen it.
Integration requires FLS-3's independently reviewed merge; an interface
agreement does not mean the skill is installed or loaded. Nothing here installs
or copies its content.

### Scopes, precedence, removal and rollback

The declaration names map exactly to board scopes:

- `defaults`: unscoped settings (`you`), used by every coordinator **on this board**.
- `main`: `--main-coordinator`, this board's all-machines/main coordinator.
- `machine`: `--machine-coordinator`, this machine's coordinator only.
- `perProject.<registered-name>`: `--project-coordinator <registered-name>`.
  It is **not** `--repo`, which changes work settings for a project's tasks.

This is not distributed config replication: each machine has its own settings.
Machine-coordinator settings do **not** flow into project coordinators. Supported
lookup is this-time (autopilot only) → coordinator's own → you → built in. Other
keys use the nearest answer; instructions add `you`, then own, separated by two
newlines. An explicit runtime `none` suppresses broader instructions. Scoped
`none` therefore refuses an addition rather than silently losing that suppression.
The helper matches 1.2.26 `values.rs::Ty::Text`: trim Unicode White_Space at
both ends, canonicalize case-insensitive `none`, and refuse whitespace-only text.
Thus saved `" NONE "` still suppresses defaults. Raw instruction bytes remain
separate for ownership and before/proposed-own hashes; effective preview hashes
and scoped readback use normalized text before additive joining. Python's extra
U+001C–U+001F strip characters are deliberately not trimmed, matching Rust.

Preview ownership is one `nix:herdr-projects:instructions:v1` marked block **inside
the individual instruction value**, never the file/tree. Existing owner reporting
policy and custom text outside it remain byte-for-byte. New declared text replaces
only that scope's block; repeated composition is identical. Shared text is kept
only in defaults and literal duplication into an own addition is refused.
`null`/omitted instructions release ownership without removing any existing block;
empty text explicitly previews removal of only that block. To preview removal of the shared policy, set `includePolicy = false` and
`defaults.instructions = ""`; disabling policy with null merely releases ownership. Omitting a whole project also leaves
runtime text alone. This non-pruning rule avoids deleting newer runtime work.

Rollback is only a **preview** of an earlier block, preserving newer unmanaged
text; never restore a whole old settings file or task/session backup. Malformed,
ambiguous, duplicate or unknown declarations/markers fail closed. Since there is
no importer, there is no partial command mutation to undo, no settings backup to
leak, and Nix generation rollback cannot reset runtime settings. A future importer
must revalidate these contracts, use board-owned concurrency/transaction support,
retain private per-key before/after receipts, and reconcile uncertain outcomes
before any retry. Do not delete locks or ledgers to resolve a failure.

## Generated resources and commands

If explicitly enabled, Home Manager would generate:

- `~/.config/herdr-projects-nix/declarations.json` (nonsecret versioned intent).
- `~/.config/herdr-projects-nix/automation.json` (default-off, `ready:false`,
  `activationCommand:null`, registration owner MAIN).
- Profile tools `herdr-projects-declarations` and `herdr-agent-config-gate`, backed
  by `config/projects_settings.py` and `config/agent_config_gate.py` respectively.

These are **outside** `~/.herdr-projects/`. The mutable board home, settings, data,
sessions, workspaces, histories, ledgers, auth and reports remain board-owned.
Herdr's pre-existing plugin-install hook and TOML management are unchanged.

```sh
herdr-projects-declarations plan
# Optional only after accounting for the CLI housekeeping caveat:
herdr-projects-declarations readback
# Always refuses, with no board call:
herdr-projects-declarations apply
```

`plan` reads raw JSON only, including the standard `HERDR_PROJECTS_HOME` /
`HERDR_PROJECTS_CONFIG_DIR` locations or explicit `--settings`; it never calls the
board or writes a file. Output contains hashes/metadata, not instruction text.
It previews additions/removals for explicitly declared and existing scopes.
`readback` checks **exactly 1.2.26**, then each distinct scoped `show --json`,
checking effective instructions **and own/place provenance**, and detects settings
changes during collection. Unknown versions, unavailable machines, malformed
output, partial command failure or a role refusal stop verification without retry
or fallback. Do not run this unattended as a supposedly side-effect-free audit.
It verifies saved settings, **not** a running chat having consumed new rules.

No live import or reload is authorized here. Even a future safe settings import
would not prove running-chat adoption: Projects documents changed coordinator
settings from the next fresh chat. An authorized later skill install needs real
machine discovery/session verification too. Do not restart/new-chat/reload a busy
coordinator merely to make an activation claim. Darkforest is not live-verified.

## Merged-event workflow specification (not registered)

Managed identity: `dotfiles-agent-config-after-approved-merge-v1`. Proposed trigger
is Projects' supported **`merged` task event** for existing project `dotfiles`;
it is not a Git webhook, recurring timer or proof of approval. MAIN exclusively
owns eventual registration/readback. No automation/task is created here.

Pinned proposed target: **DAMOCLES / Jack / dotfiles**,
origin `git@github.com:jack-michaud/nix.git`, canonical checkout
`/Users/Jack/Code/archive/nix` (alias `/Users/Jack/.config/dotfiles`), candidate HM
attribute `darwinConfigurations.DAMOCLES.config.home-manager.users.Jack.home.activationPackage`.
That attribute is valid for evaluation/build; executing its activation script is
**not** a supported AI-only targeted apply. It includes other hooks, packages and
files. KRONOS and `homeConfigurations."jack@DARKFOREST"` are separate targets,
never fallback targets. No general host activation command is provided.

Exact prepared gate invocation, after the tools are actually installed/built:

```sh
herdr-agent-config-gate check --proof /absolute/path/to/collector-output.json
```

This is a readiness command, **not an activation command**. It returns nonzero and
a four-part progress-first blocker with a private immutable receipt. It accepts
no task-body shell command. The current proof schema is strict in
`agent_config_gate.assess`; `tests/test_agent_config_gate.py::proof` is a synthetic
example, not a real approval/effect attestation. It covers:

- exact 40-hex before/after Git revisions, origin, complete changed paths, clean
  checkout and no unrelated pending work;
- exact machine/user/project/attribute and merged-event identity, nonrecursive
  source-merge origin, exact-source source approval, independent review and all
  required successful checks (not merely an event or peer message);
- complete evaluated before/current target hash and built output hash, complete
  managed file deltas and **every** activation action;
- explicit empty packages/services/credentials/restarts/unknown effects, bounded
  AI instruction/skill/Projects declaration file categories, and install-file
  actions only; unknown/mixed/broader effects block for Jack;
- not-started state only: in-flight, timeout/uncertain and completed cases must
  reconcile before retry; old/reordered source cannot apply to a newer baseline.

Source path screening is only a necessary first filter, **never proof of effects**.
The CLI independently checks canonical checkout, origin, clean/untracked state,
HEAD, locally known origin/main, ancestry and the entire no-renames NUL-delimited
Git diff. It never fetches, resets, switches branches or mutates that checkout.
Even a perfect supplied JSON is **untrusted**: trusted exact-source approval/check
collectors, exhaustive activation-effect analysis and a supported bounded adapter
are unavailable. Thus it **always blocks real application**. Synthetic validator
success means schema/policy acceptance only. There is no bypass/force flag.

Receipts default to
`~/.local/state/herdr-agent-config-gate/DAMOCLES-Jack-dotfiles/`: 0700 directory,
0600 immutable content-addressed JSON, target-scoped kernel flock on a retained
`owner.lock`. Repeated identical blocked evidence reuses its receipt. It stores
only hashes, validated revisions, fixed target, status and fixed reasons, not
source text, secrets or caller instructions. This lock protects **receipt writing
only**, not native board writes or a nonexistent activation executor. Future
execution must hold a target owner throughout proof, write-ahead intent, bounded
apply and readback, retain uncertainty across timeouts, and reconcile the current
installed target/baseline before retry. Never turn this receipt lock into a claim
of board CAS or global exactly-once behavior.

Before registration MAIN needs independently reviewed exact source/tests and a
**genuinely proven** bounded command/collector handoff. Until that engineering gap
is closed, the specification remains unready; Jack's narrow scope consent is not
missing. A future report-only firing must not commit source (avoids recursion),
create other work, broaden permissions, change approval gates or auto-wake hosts.

## Tests (no activation)

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s modules/shared/shells/herdr/tests -v
nix eval --offline --impure --raw --expr \
  '(import ./modules/shared/shells/herdr/tests/_eval-projects.nix { flake = builtins.getFlake (toString ./.); }).results'
nix build --offline --impure --no-link --expr \
  '(import ./modules/shared/shells/herdr/tests/_eval-projects.nix { flake = builtins.getFlake (toString ./.); }).packages'
```

Existing plugin installer tests require `HERDR_PLUGINS_INSTALLER` set to the
Nix-built installer; otherwise they explicitly skip. Tests use scratch state under
`TMPDIR`, mock board readback and synthetic proofs; none proves live transaction
safety, full effect completeness, approval authority or activation. Test new CLI
versions deliberately before expanding the version allowlist. Evaluate actual
DAMOCLES/KRONOS/DARKFOREST host attributes separately; build alone is not switch.
