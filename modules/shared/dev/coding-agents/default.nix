{ config, options, lib, pkgs, ... }:

with lib;
with lib.my;
let
  cfg = config.modules.dev.coding-agents;

  # @var@ markers in the templates are substituted at build time so per-host
  # facts (vault path, role) sit inline in the deployed file — agents never
  # need a second file to learn where the vault is.
  agentsMd = pkgs.runCommandLocal "AGENTS.md" { } ''
    substitute ${./config/AGENTS.md} $out \
      --subst-var-by host ${escapeShellArg config.environment.variables.NIX_FLAKE_HOST} \
      --subst-var-by role ${escapeShellArg cfg.role} \
      --subst-var-by vaultDir ${escapeShellArg cfg.vaultDir} \
      --subst-var-by dotfilesDir ${escapeShellArg config.dotfiles.dir}
  '';
  vaultRulesMd = pkgs.runCommandLocal "vault-rules.md" { } ''
    substitute ${./config/vault-rules.md} $out \
      --subst-var-by vaultDir ${escapeShellArg cfg.vaultDir}
  '';
in {
  options.modules.dev.coding-agents = {
    enable = mkBoolOpt false;
    # Conditions what agents are told about this machine: "personal" | "work".
    role = mkOpt types.str "personal";
    # The Obsidian vault the agents files point at.
    vaultDir = mkOpt types.str "${config.dotfiles.vaultDir}/Personal";
  };

  config = mkIf cfg.enable {
    home.file = {
      # AGENTS.md is the source of truth; CLAUDE.md is the same file under the
      # vendor-specific name Claude Code insists on.
      ".agents/AGENTS.md".source = agentsMd;
      ".agents/CLAUDE.md".source = agentsMd;
      # Read on demand when an agent is about to touch the vault, so its
      # mechanics don't cost context in sessions that never go there.
      ".agents/vault-rules.md".source = vaultRulesMd;
      # pi loads its global agents file from here at session start.
      ".pi/agent/AGENTS.md".source = agentsMd;
      # Claude Code: rules files without a `paths` filter load in every
      # session — additive next to the handwritten ~/.claude/CLAUDE.md.
      ".claude/rules/agents.md".source = agentsMd;
    };
  };
}
