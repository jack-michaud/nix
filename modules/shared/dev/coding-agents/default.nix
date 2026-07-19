{ config, options, lib, pkgs, ... }:

with lib;
with lib.my;
let
  cfg = config.modules.dev.coding-agents;
  rulesDir = "${config.dotfiles.modulesDir}/shared/dev/coding-agents/config/rules";

  substVars = ''
    --subst-var-by host ${escapeShellArg config.environment.variables.NIX_FLAKE_HOST} \
    --subst-var-by role ${escapeShellArg cfg.role} \
    --subst-var-by vaultDir ${escapeShellArg cfg.vaultDir} \
    --subst-var-by dotfilesDir ${escapeShellArg config.dotfiles.dir}'';

  # @var@ markers in AGENTS.md are substituted at build time so per-host facts
  # (vault path, role) sit inline in the deployed file.
  agentsMd = pkgs.runCommandLocal "AGENTS.md" { } ''
    substitute ${./config/AGENTS.md} $out ${substVars}
  '';

  # Defines one agent rule: a markdown file in config/rules/ fanned out to
  # every location a harness reads rules from — ~/.claude/rules for Claude
  # Code, ~/.agents/rules as the harness-neutral spot. By default the deployed
  # file is a live symlink into the checkout (same mkOutOfStoreSymlink
  # workaround as zsh) so edits apply without a rebuild; `substitute = true`
  # instead bakes the @var@s in via the store, for rules that need them.
  mkAgentRule = name: { substitute ? false }:
    let
      source =
        if substitute then
          pkgs.runCommandLocal name { } ''
            substitute ${./config/rules + "/${name}"} $out ${substVars}
          ''
        else
          pkgs.runCommandLocal name { } ''
            ln -s ${escapeShellArg "${rulesDir}/${name}"} $out
          '';
    in {
      ".agents/rules/${name}".source = source;
      ".claude/rules/${name}".source = source;
    };

  rules = {
    "vault.md" = { };
    "agentsmd-rules.md" = { substitute = true; };
  };
in {
  options.modules.dev.coding-agents = {
    enable = mkBoolOpt false;
    # Conditions what agents are told about this machine: "personal" | "work".
    role = mkOpt types.str "personal";
    # The Obsidian vault the agents files point at.
    vaultDir = mkOpt types.str "${config.dotfiles.vaultDir}/Personal";
  };

  config = mkIf cfg.enable {
    home.file = foldl' (acc: r: acc // r) {
      # AGENTS.md is the source of truth; CLAUDE.md is the same file under the
      # vendor-specific name Claude Code insists on.
      ".agents/AGENTS.md".source = agentsMd;
      ".claude/CLAUDE.md".source = agentsMd;
    } (mapAttrsToList mkAgentRule rules);
  };
}
