---
name: nix-config-change
description: Delegate a change to Jack's nix config (flake at ~/Code/github.com/jack-michaud/nix) to a sub-agent that edits it following the repo's conventions, evaluates the affected host for real, and ships it as a PR with jj-ship. Use whenever Jack asks to add, enable, change, or remove something in his nix config, nix flake, home-manager setup, or a nix module.
compatibility: Requires the nix config checkout, `nix`, `treehouse` (jj backend), and the `jj-ship` skill (jj + authenticated gh). Runs inside the agent kernel, since it spawns a sub-agent.
---

# nix-config-change

Jack asks for nix-config changes often. This skill turns the request into one
delegated, verified, shipped unit of work instead of a fresh improvisation.

Each change gets its own leased **treehouse** workspace, so two changes in flight
never touch the same working tree.

```python
await nix_config_change("Install ripgrep-all for the DARKFOREST host")
await nix_config_change("Add a prime-agent skills fan-out to the coding-agents module",
                        bookmark="prime-agent-skills")
```

Inspect the prompt before spawning, or skip shipping:

```python
print(await nix_config_change("...", dry_run=True))
await nix_config_change("...", ship=False)     # leave it in the working copy
```

## What the sub-agent is told

- **Conventions**: `modules/shared|linux|darwin/**` + per-host enablement,
  `lib.my`'s `mkBoolOpt`/`mkOpt` options defaulting to off, module config files
  living in a sibling `config/` and deployed as live symlinks into the checkout,
  `builtins.readDir` over hand-maintained lists, why-comments.
- **Verification is required**: `nix flake check --no-build` plus a real
  `nix build --no-link .#homeConfigurations."jack@<HOST>".activationPackage`
  (or the darwin equivalent), with the real output quoted in the PR.
- **It must not activate**: no `home-manager switch`, no `darwin-rebuild switch`,
  no merging the PR. Those are Jack's calls.
- **Shipping** goes through the `jj-ship` skill: `commit` → `push` → `open_pr`
  → `watch` for CI and review comments.
- **Its workspace**: it works in a leased jj workspace, and returns it with
  `treehouse return <path> --if-lease-id <id> --force` as its last step.

## Workspace isolation

`treehouse` manages the jj workspaces; this skill only drives it. Each call leases
one (`treehouse get --lease`), points the sub-agent at it, and the sub-agent returns
it when done. Pass `workspace=False` to work directly in `repo` instead.

`TREEHOUSE_VCS=jj` is passed explicitly rather than inherited: `hm-session-vars.sh`
guards on `__HM_SESS_VARS_SOURCED`, which agent kernels already have set, so the
variable never reaches us. The lease is then asserted to be a real jj workspace —
a git-flavored pool slot otherwise fails much later, inside the ship step.

## Contract

Returns immediately with the spawned child's handle as JSON — spawning is
admission, not completion. The child reports back with `agent_message`; wait for
that message rather than polling it. Defaults come from `NIX_CONFIG_REPO` and
`NIX_CONFIG_HOST` if set.
