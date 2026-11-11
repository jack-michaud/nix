{ config, options, lib, pkgs, ... }:

with lib;
with lib.my;

let
  cfg = config.modules.shells.herdr;
  installPlugins = pkgs.writeShellApplication {
    name = "install-herdr-plugins";
    # Native installs may build Rust plugins. Do not pick up an older rustup
    # toolchain from the user's shell (jj-workspace requires a recent rustc).
    runtimeInputs = [ pkgs.jq pkgs.git pkgs.curl pkgs.cargo pkgs.rustc ]
      ++ optionals (!pkgs.stdenv.isDarwin) [ pkgs.stdenv.cc ];
    # Outside a Nix build, Darwin's system compiler supplies the selected Xcode
    # SDK (including libiconv); a bare Nix cc lacks stdenv's linker setup.
    text = optionalString pkgs.stdenv.isDarwin ''
      export PATH="$PATH:/usr/bin:/bin"
    '' + builtins.readFile ./config/install-plugins.sh;
  };

  # cursor-agent doesn't emit OSC 7501, so Herdr desktop never lists it as an
  # agent (herdrdev/herdr-app#98). This mod's Cursor hooks emit it instead.
  # Cursor's hook PATH may lack node, so pin the interpreter.
  cursorStatusMod = pkgs.runCommandLocal "herdr-cursor-status" {
    src = pkgs.fetchFromGitHub {
      owner = "juliorr";
      repo = "herdr-cursor-status";
      rev = "147971e501580cb48b06931c0484e7f0357a5b5d";
      hash = "sha256-0Ly01L8ONFAv/ZaArx5OW2U7gWOBfXXwwhvBcgMsDMc=";
    };
  } ''
    cp -R $src/mods/cursor-status $out
    chmod -R u+w $out
    substituteInPlace $out/status.mjs \
      --replace-fail '`node ''${shq(script)} hook`' '`${pkgs.nodejs}/bin/node ''${shq(script)} hook`'
  '';
in {
  options.modules.shells.herdr = {
    enable = mkBoolOpt false;

    # Darwin normally uses a user/Homebrew-managed Herdr. On Linux, set this
    # so activation can find the binary outside the user profile's PATH.
    package = mkOpt (types.nullOr types.package) null;

    # Add trusted OWNER/REPO[/SUBDIR] sources here. Herdr owns versions and
    # builds; `herdr plugin update --yes` rolls them forward independently.
    # Removing an entry does not uninstall it or delete its user data.
    plugins = mkOpt (types.listOf types.str) [ ];

    # List cursor-agent terminals in the Herdr desktop Agents panel. Merges
    # into ~/.cursor/hooks.json; disabling leaves those entries behind
    # (`node <mod>/status.mjs uninstall` removes them).
    cursorStatus = mkBoolOpt false;
  };

  config = mkIf cfg.enable {
    # Only config.toml is managed — ~/.config/herdr also holds runtime state
    # (logs, sockets, session.json) that must stay writable.
    # Equivalent of home-manager's mkOutOfStoreSymlink (which isn't reachable
    # through the darwin-level `home.file` alias): links to the live checkout
    # when dotfiles.dir is a non-store path, so edits apply without a rebuild.
    home.file.".config/herdr/config.toml".source =
      pkgs.runCommandLocal "herdr-config" { } ''
        ln -s ${escapeShellArg "${config.dotfiles.modulesDir}/shared/shells/herdr/config/config.toml"} $out
      '';

    home.file.".config/herdr-app/mods/cursor-status" = mkIf cfg.cursorStatus {
      source = cursorStatusMod;
    };

    home-manager.users.${config.user.name} = { lib, ... }: {
      # Idempotent; replaces its own entries from older store paths and keeps
      # any other hooks in the file.
      home.activation.herdrCursorStatus = mkIf cfg.cursorStatus
        (lib.hm.dag.entryAfter [ "writeBoundary" ] ''
          run ${pkgs.nodejs}/bin/node ${cursorStatusMod}/status.mjs install
        '');

      home.activation.herdrPlugins = mkIf (cfg.plugins != [ ]) (lib.hm.dag.entryAfter [ "installPackages" ] ''
        herdrBin=${optionalString (cfg.package != null) "${cfg.package}/bin/herdr"}
        if [ -z "$herdrBin" ]; then
          herdrBin="$(command -v herdr || true)"
        fi
        if [ -z "$herdrBin" ] && [ -x "$HOME/.local/bin/herdr" ]; then
          herdrBin="$HOME/.local/bin/herdr"
        fi
        if [ -z "$herdrBin" ] && [ -x /opt/homebrew/bin/herdr ]; then
          herdrBin=/opt/homebrew/bin/herdr
        fi
        if [ -z "$herdrBin" ]; then
          echo "herdr not found; cannot install declared plugins" >&2
          exit 1
        fi
        run ${lib.getExe installPlugins} "$herdrBin" ${escapeShellArgs cfg.plugins}
      '');
    };
  };
}
