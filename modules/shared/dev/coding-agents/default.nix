{ config, options, lib, pkgs, ... }:

with lib;
with lib.my;
let
  cfg = config.modules.dev.coding-agents;
  configDir = "${config.dotfiles.modulesDir}/shared/dev/coding-agents/config";
  rulesDir = "${configDir}/rules";

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

  # Prime Agent reads skills from ~/.prime/agent/skills/<name>/SKILL.md, and
  # installs a Python-backed skill's package into its kernel venv from the same
  # directory. Each skill in config/skills/ is deployed as a live symlink into
  # the checkout (the same out-of-store trick the rules use), so editing a skill
  # applies to the next agent session without a rebuild. The set is read off the
  # filesystem, so adding a skill needs no edit to this file.
  mkAgentSkill = name: {
    ".prime/agent/skills/${name}".source = pkgs.runCommandLocal name { } ''
      ln -s ${escapeShellArg "${configDir}/skills/${name}"} $out
    '';
  };
  skillNames = attrNames
    (filterAttrs (_: type: type == "directory") (builtins.readDir ./config/skills));

  # Prime Agent loads extensions from ~/.prime/agent/extensions/<name>/index.js.
  # Same live-symlink treatment as the skills, set likewise read off the
  # filesystem. An extension is the only place a check can run BEFORE the agent's
  # model reads a message, which is why ship-check needs one.
  mkAgentExtension = name: {
    ".prime/agent/extensions/${name}".source = pkgs.runCommandLocal name { } ''
      ln -s ${escapeShellArg "${configDir}/extensions/${name}"} $out
    '';
  };
  extensionNames = attrNames
    (filterAttrs (_: type: type == "directory") (builtins.readDir ./config/extensions));

  rules = {
    # Substituted so the `paths` trigger globs carry the real vault path.
    "vault.md" = { substitute = true; };
    "agentsmd-rules.md" = { substitute = true; };
    # Substituted so the body names the real checkout path.
    "editing-agent-rules.md" = { substitute = true; };
    "python-rules.md" = { };
  };

  # Claude Code loads no-`paths` rules from ~/.claude/rules natively but never
  # fires path-scoped rules whose globs point outside the project (e.g.
  # vault.md). This PostToolUse hook implements the same contract as the pi
  # extension; it points at the checkout so edits apply without a rebuild.
  globalRuleFilesHook = {
    matcher = "Read|Edit|Write|NotebookEdit|Glob|Grep";
    hooks = [{
      type = "command";
      command = "python3 '${configDir}/claude-hooks/global-rule-files.py'";
      timeout = 10;
    }];
  };
  globalRuleFilesHookJson = pkgs.writeText "global-rule-files-hook.json"
    (builtins.toJSON globalRuleFilesHook);

  # Pi installs packages declared in settings on its next startup. Pin the git
  # ref so rebuilding this config always selects the reviewed revision.
  piPackages = [
    "git:github.com/algal/pi-openai-server-compaction@8a3de2f3b0c178fdd6f73f2f94172dfc3943e466"
  ];
  piPackagesJson = pkgs.writeText "pi-packages.json" (builtins.toJSON piPackages);

  # Merged (not symlinked) into ~/.claude/settings.json: the file is mutable —
  # Claude Code writes enabledPlugins, theme, permissions.allow, etc. into it.
  # Each run drops PostToolUse entries carrying the marker filename and appends
  # the current definition; everything else in the file is left alone.
  mergeGlobalRuleFilesHook = pkgs.writeShellScript "merge-global-rule-files-hook" ''
    set -euo pipefail
    settings="$HOME/.claude/settings.json"
    mkdir -p "$HOME/.claude"
    [ -s "$settings" ] || echo '{}' > "$settings"
    ${pkgs.jq}/bin/jq --slurpfile entry ${globalRuleFilesHookJson} '
      .hooks.PostToolUse = (
        ((.hooks.PostToolUse // [])
         | map(select(
             ((.hooks // []) | map(.command // "") | join(" "))
             | contains("global-rule-files.py") | not)))
        + [$entry[0]]
      )' "$settings" > "$settings.hm-tmp"
    mv "$settings.hm-tmp" "$settings"
  '';

  # Keep Pi's mutable preferences while declaratively adding global packages.
  mergePiPackages = pkgs.writeShellScript "merge-pi-packages" ''
    set -euo pipefail
    settings="$HOME/.pi/agent/settings.json"
    mkdir -p "$HOME/.pi/agent"
    [ -s "$settings" ] || echo '{}' > "$settings"
    ${pkgs.jq}/bin/jq --slurpfile packages ${piPackagesJson} '
      .packages = (
        [(.packages // [])[] | select(
          ((if type == "string" then . else (.source // "") end)
           | startswith("git:github.com/algal/pi-openai-server-compaction"))
          | not
        )] + $packages[0]
      )
    ' "$settings" > "$settings.hm-tmp"
    mv "$settings.hm-tmp" "$settings"
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
    home.file = foldl' (acc: r: acc // r) {
      # AGENTS.md is the source of truth; CLAUDE.md is the same file under the
      # vendor-specific name Claude Code insists on.
      ".agents/AGENTS.md".source = agentsMd;
      ".claude/CLAUDE.md".source = agentsMd;
      ".prime/agent/AGENTS.md".source = agentsMd;
      # pi has no native rules dir; this extension implements the same
      # contract (frontmatter `paths` triggers) over ~/.agents/rules.
      ".pi/agent/extensions/agent-rules.ts".source = pkgs.runCommandLocal "agent-rules.ts" { } ''
        ln -s ${escapeShellArg "${configDir}/pi-extensions/agent-rules.ts"} $out
      '';
    } (mapAttrsToList mkAgentRule rules ++ map mkAgentSkill skillNames
      ++ map mkAgentExtension extensionNames);

    home-manager.users.${config.user.name} = { lib, ... }: {
      home.activation = {
        claudeGlobalRuleFilesHook = lib.hm.dag.entryAfter [ "writeBoundary" ] ''
          run ${mergeGlobalRuleFilesHook}
        '';
        piPackages = lib.hm.dag.entryAfter [ "writeBoundary" ] ''
          run ${mergePiPackages}
        '';
      };
    };
  };
}
