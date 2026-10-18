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

    home-manager.users.${config.user.name} = { lib, ... }: mkIf (cfg.plugins != [ ]) {
      home.activation.herdrPlugins = lib.hm.dag.entryAfter [ "installPackages" ] ''
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
      '';
    };
  };
}
