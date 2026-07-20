---
paths: ["~/.agents/rules/**", "~/.claude/rules/**"]
---

# Editing agent rules

`~/.agents/rules/` and `~/.claude/rules/` are deployed by the `coding-agents`
module of Jack's nix config (checkout at `@dotfilesDir@`). Don't edit the
deployed copies — edit the sources in
`@dotfilesDir@/modules/shared/dev/coding-agents/config/rules/` instead.

- A rule deployed as a live symlink into the checkout picks up source edits
  immediately; one deployed as a `/nix/store` path has `@var@` markers baked
  in at build time and needs a rebuild after its source changes. `ls -l` on
  the deployed file shows which kind it is.
- To add a rule, create the markdown file in `config/rules/` and register it
  in the `rules` attrset in `modules/shared/dev/coding-agents/default.nix`
  (`substitute = true` only if it uses `@var@` markers), then rebuild.
- A plain file sitting in these dirs (not a symlink, not a store path) is
  unmanaged by nix and only reaches the harness whose dir it sits in —
  prefer migrating it into the module so every harness sees it.
