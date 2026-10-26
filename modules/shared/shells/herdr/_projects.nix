{ config, lib, pkgs, ... }:
let
  cfg = config.modules.shells.herdr.projects;
  scope = lib.types.submodule {
    options.instructions = lib.mkOption {
      type = lib.types.nullOr lib.types.str;
      default = null;
      description = "Nonsecret coordinator instruction addition; null is unmanaged, empty removes only our marked block.";
    };
  };
  declared = s: lib.optionalAttrs (s.instructions != null) {
    "coordinator.instructions" = s.instructions;
  };
  manifest = {
    version = 1;
    scopes = {
      defaults = declared {
        instructions = if cfg.includePolicy then
          builtins.readFile ./config/coordinator-policy.md
          + lib.optionalString (cfg.defaults.instructions != null) ("\n" + cfg.defaults.instructions)
        else cfg.defaults.instructions;
      };
      main = declared cfg.main;
      machine = declared cfg.machine;
    } // lib.mapAttrs' (name: value: lib.nameValuePair "project:${name}" (declared value)) cfg.perProject;
  };
  helper = pkgs.writeShellScriptBin "herdr-projects-declarations" ''
    exec ${pkgs.python3}/bin/python3 ${./config/projects_settings.py} "$@"
  '';
  gate = pkgs.writeShellScriptBin "herdr-agent-config-gate" ''
    export PATH=${lib.makeBinPath [ pkgs.git ]}:"$PATH"
    exec ${pkgs.python3}/bin/python3 ${./config/agent_config_gate.py} "$@"
  '';
in {
  options.modules.shells.herdr.projects = {
    enable = lib.mkEnableOption "prepared Herdr Projects declarations (no runtime activation)";
    includePolicy = lib.mkOption {
      type = lib.types.bool;
      default = true;
      description = "Include the shared routing policy once, in defaults only. Existing custom/reporting instructions remain unmanaged.";
    };
    defaults = lib.mkOption { type = scope; default = { }; };
    main = lib.mkOption { type = scope; default = { }; };
    machine = lib.mkOption { type = scope; default = { }; };
    perProject = lib.mkOption {
      type = lib.types.attrsOf scope;
      default = { };
      description = "Explicit project coordinator additions, keyed by exact registered board project name (not --repo work settings).";
    };
    automation.enable = lib.mkOption {
      type = lib.types.bool;
      default = false;
      description = "Declare intent for MAIN to register the merged-event audit. Does not register or authorize activation.";
    };
  };
  config = lib.mkIf (config.modules.shells.herdr.enable && cfg.enable) {
    home.file.".config/herdr-projects-nix/declarations.json".text = builtins.toJSON manifest;
    home.file.".config/herdr-projects-nix/automation.json".text = builtins.toJSON {
      schema = 1;
      identity = "dotfiles-agent-config-after-approved-merge-v1";
      requested = cfg.automation.enable;
      ready = false;
      trigger = { event = "merged"; repo = "dotfiles"; };
      source = { origin = "git@github.com:jack-michaud/nix.git"; checkout = "/Users/Jack/Code/archive/nix"; };
      target = {
        machine = "DAMOCLES";
        project = "dotfiles";
        attribute = "darwinConfigurations.DAMOCLES.config.home-manager.users.Jack.home.activationPackage";
        user = "Jack";
      };
      # A fixed, read-only gate; never interpolate a task body into a shell.
      gate = "${gate}/bin/herdr-agent-config-gate";
      command = "check";
      activationCommand = null;
      blocker = "No proven AI-only targeted activation or concurrency-safe Projects import in the inspected installed contracts.";
      registrationOwner = "MAIN";
    };
    home-manager.users.${config.user.name}.home.packages = [ helper gate ];
    # Deliberately no activation hook: the board owns its entire mutable tree.
  };
}
