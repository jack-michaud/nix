# Shared coding-agent configuration

`default.nix` distributes rules, skills and extensions from `config/`. Rules and
skills generally use store-backed live symlinks to the canonical checkout, rather
than copying mutable user configuration. Keep private runtime data out of source
and the Nix store.

## Herdr orchestration skill

Source: [`config/skills/herdr-orchestration/SKILL.md`](config/skills/herdr-orchestration/SKILL.md).
This instruction-only skill complements the plugin-installed `herdr-projects`
command guide. It explains Jack's hierarchy, actual session discovery, task-tagged
Sesame relay, reporting and safe configuration/rollout boundaries. It neither
receives cross-session messages nor applies Projects settings. Read its linked
references as part of the skill.

With `modules.dev.coding-agents.enable = true`:

- All shared skills continue to reach `~/.prime/agent/skills/<name>`.
- `modules.dev.coding-agents.piSkills` selects names from the shared skill
  directories for `~/.pi/agent/skills/<name>`. The default is
  `[ "herdr-orchestration" ]`; hosts can set `[]` to opt out, or explicitly select
  another reviewed shared skill. Do not publish Prime-only runtime helpers blindly.
- Prime and Pi use the same source derivation. Pi gets no second `.agents/skills`
  copy, package registration or generated settings modification for this skill.
- A preexisting destination must be inspected for collisions, ownership and
  broken links before rollout; never force-overwrite it.

Canonical source on DAMOCLES is
`/Users/Jack/.config/dotfiles/modules/shared/dev/coding-agents/config/skills/herdr-orchestration`,
with `/Users/Jack/.config/dotfiles` resolving to `/Users/Jack/Code/archive/nix`.
The store symlink points at that canonical checkout, **not** at a task worktree.
Building before the source is merged can therefore produce a dangling live target;
that is not installed/discoverable delivery.

The declarative Projects helper and source/generated-effect automatic-application
gate are owned separately under `modules/shared/shells/herdr/`. This distribution
interface does not qualify an entire host activation as safe. Its existing module
also has independent mutable-settings hooks; a full generated activation must be
examined by that gate. In particular, the preserved shared fan-out also adds a
`.prime` destination: do not assume it is in an allowlist limited to `.agents`,
`.pi` and Herdr Projects. Unknown/out-of-scope effects must block, not broaden the
policy. No workflow/automation or activation is performed here.

## Repeatable checks

Run in the isolated task worktree, with `TMPDIR` set to that task's own temporary
folder. Python writes no bytecode; Node removes its isolated fixture afterward.
No test invokes an agent/model, provider auth, board settings mutation, coordinator
message, extra worker, server, restart or system activation.

```bash
PYTHONDONTWRITEBYTECODE=1 HERDR_CLI_CHECKS=1 \
  python3 -m unittest discover -s modules/shared/dev/coding-agents/config/tests -v
node --test modules/shared/dev/coding-agents/config/tests/test_herdr_skill.mjs
nix flake check --no-build
nix eval --impure --json --expr '
  import ./modules/shared/dev/coding-agents/config/tests/skill-distribution.nix-test {
    flake = builtins.getFlake (toString ./.);
  }'
nix build --no-link .#darwinConfigurations.DAMOCLES.system
```

The Node test resolves the installed `pi` executable's package and uses its
exported `DefaultResourceLoader`, `loadSkills` and `formatSkillsForPrompt` APIs.
For a nonstandard layout, set `PI_PACKAGE_DIR` to the reviewed installed package
root. It isolates HOME/agentDir/cwd/settings, disables extensions/context loading,
and never constructs an agent session. It checks exact parsed metadata, native
Pi symlink discovery, references, diagnostics, same-source deduplication, name
collisions, malformed/missing metadata, and broken symlinks. A Prime-only fixture
must not be discovered by Pi. Pi silently skips some broken links, so explicit
filesystem audits remain necessary.

Python tests protect glossary/hierarchy/identity/guard rules, the exact quoted
reporting acceptance, dated-only pane examples, rollout distinctions and safe
shell syntax. `HERDR_CLI_CHECKS=1` enables installed help/version-only checks;
without it those two integration tests are explicitly skipped.
`HERDR_PROJECTS_BIN` can select another reviewed installed launcher. Network
machine probes and relay messages are deliberately not automated tests.

The `.nix-test` suffix is intentional: this repository automatically imports
`*.nix` recursively as system modules. The expression evaluates the real DAMOCLES
Darwin graph and checks selected Pi/Prime sources, no `.agents` duplication and
machine-level Pi opt-out. It accepts `host`/`user` for another actual supported
Darwin configuration. Check `flake.nix` rather than inventing a host attribute.
`flake check` omits incompatible systems unless requested; a successful build is
**not** activation or evidence of a running session reload.

## Rollout and readback

Keep per-task progress/readback receipts outside the repo in the board-provided
report folder. Distinguish isolated discovery, committed/reviewed/merged source,
current-machine installation, and current-running-session reload.

After review/merge into the canonical checkout, the authorized owner/workflow must
qualify and apply the bounded file distribution (not blindly switch the host).
Inspect both Home Manager destination links and the store-to-canonical chain;
confirm `SKILL.md` exists and no same-name loader collision/filter hides it. Then
the actual active-session owner can use Pi's `/reload` at an appropriate boundary,
or verify discovery at the next normal startup. Do not restart workers to load a
skill, resume a live transcript from another process, or claim a receiver is ready
because this skill loaded. Current-session reload is separate from installation.
