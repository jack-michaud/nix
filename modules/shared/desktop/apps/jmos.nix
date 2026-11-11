{ config, options, lib, pkgs, ... }:

with lib;
with lib.my;

# jmos as a *client* of a jmosd server on another machine (jmos repo:
# docs/jmosd-contract.md, "A second server"). The machine that runs jmosd
# keeps its own hand-written config; this module only writes the client file.
let
  cfg = config.modules.desktop.apps.jmos;
  configPath = "${config.user.home}/.config/jmos/1.0/config.toml";

  clientConfig = {
    default_server = cfg.server.name;

    servers.${cfg.server.name} = {
      url = "tcp://${cfg.server.host}:${toString cfg.server.port}";
      space = cfg.server.space;
      # A `''${KEY}` reference, never the token. jmos reads it from its
      # environment, else asks Automic Vault (`av`) for it at start.
      token = "\${${cfg.server.tokenKey}}";
    };

    edge = { };
    jmosd.enabled = true;

    workspaces.${cfg.workspace.id} = {
      title = cfg.workspace.title;
      default = true;
      server = cfg.server.name;
      menu = cfg.workspace.menu;
      # false: the menu is exactly `menu`, no other built-in app is added.
      rest = false;
    };
  };
in {
  options.modules.desktop.apps.jmos = with types; {
    enable = mkBoolOpt false;

    # jmos has no git remote, so there is no flake input to build it from.
    # null: the module manages the config only and expects `jmos` on PATH
    # (e.g. `cargo install` into ~/.cargo/bin from a copy of the checkout).
    package = mkOpt (nullOr package) null;

    server = {
      # The client's own name for the server: the `[servers.<name>]` key and
      # the replica folder (~/.local/state/jmos/edge/<name>/).
      name = mkOpt str "home";
      host = mkOpt str "";
      port = mkOpt port 7878;
      # Must equal `[server] space` in the server's jmosd.toml; the client
      # refuses a server that answers with another space.
      space = mkOpt str "home";
      # Name of the secret that holds this machine's token. The server has
      # the same value under `[auth] tokens`, one entry per remote machine.
      tokenKey = mkOpt str "";
    };

    workspace = {
      id = mkOpt str "primary";
      title = mkOpt str "Primary";
      # Main menu entries, in order. Slugs: jmos repo, src/apps/mod.rs.
      menu = mkOpt (listOf str) [ "todos" ];
    };
  };

  config = mkIf cfg.enable {
    assertions = [
      {
        assertion = cfg.server.host != "";
        message = "modules.desktop.apps.jmos.server.host must be set";
      }
      {
        assertion = builtins.match "[A-Z_][A-Z0-9_]*" cfg.server.tokenKey != null;
        message =
          "modules.desktop.apps.jmos.server.tokenKey must name a secret (e.g. JMOSD_TOKEN_AUTODESK), not hold one";
      }
    ];

    # A store file: jmos only reads it. Change the options and rebuild.
    home.file.".config/jmos/1.0/config.toml".source =
      (pkgs.formats.toml { }).generate "jmos-config.toml" clientConfig;

    # Without this jmos reads the pre-1.0 ~/.config/jmos/config.toml.
    env.JMOS_CONFIG = configPath;

    environment.systemPackages = optional (cfg.package != null) cfg.package;
  };
}
