{ config, options, lib, pkgs, inputs, ... }:

with lib;
with lib.my;

let
  cfg = config.modules.shells.herdr;

  jjWorkspaceSrc = inputs.herdr-plugin-jj-workspace;

  # Build the plugin in nix instead of `herdr plugin install`, which shells
  # out to the system cargo at install time — the rustup toolchain can be
  # older than the plugin's deps require (rustc 1.87 vs ratatui's 1.88).
  jjWorkspace = pkgs.rustPlatform.buildRustPackage {
    pname = "herdr-plugin-jj-workspace";
    version = jjWorkspaceSrc.shortRev or "unstable";
    src = jjWorkspaceSrc;
    cargoLock.lockFile = jjWorkspaceSrc + "/Cargo.lock";
  };

  # The manifest's action commands are relative (`./target/release/...`) and
  # herdr resolves them against the plugin root, so mirror the layout a
  # `cargo build --release` would have produced. The manifest must be a real
  # file, not a symlink: herdr canonicalizes the manifest path when deriving
  # the plugin root, and a symlink would resolve it back to the bare source
  # tree (which has no target/release binary).
  jjWorkspacePluginDir = pkgs.runCommandLocal "herdr-plugin-jj-workspace-dir" { } ''
    mkdir -p $out/target/release
    cp ${jjWorkspaceSrc}/herdr-plugin.toml $out/herdr-plugin.toml
    ln -s ${jjWorkspace}/bin/jj-workspace $out/target/release/jj-workspace
  '';
in {
  options.modules.shells.herdr = {
    enable = mkBoolOpt false;

    # The herdr binary itself isn't installed by this module — on darwin it
    # comes from Homebrew, so activation looks it up at runtime. Hosts that
    # get herdr from nixpkgs set this instead: home-manager's activation
    # script overwrites PATH with a fixed set of store paths (the user profile
    # is never on it), so a PATH lookup can't find a nix-installed herdr.
    package = mkOpt (types.nullOr types.package) null;
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

    # Register the nix-built plugin with herdr. `plugin link` doesn't build
    # (we already did) and is idempotent: re-linking the same plugin id
    # updates the registered plugin root, so plugin updates converge on the
    # next rebuild. The registry (plugins.json) stays herdr-managed runtime
    # state, so we don't touch it directly.
    home-manager.users.${config.user.name} = { lib, ... }: {
      # After installPackages, so a herdr from `home.packages` is on disk by
      # the time we shell out to it.
      home.activation.herdrJjWorkspacePlugin =
        lib.hm.dag.entryAfter [ "installPackages" ] ''
          herdrBin=${optionalString (cfg.package != null) "${cfg.package}/bin/herdr"}
          if [ -z "$herdrBin" ]; then
            herdrBin="$(command -v herdr || true)"
          fi
          if [ -z "$herdrBin" ] && [ -x /opt/homebrew/bin/herdr ]; then
            herdrBin=/opt/homebrew/bin/herdr
          fi
          if [ -n "$herdrBin" ]; then
            run "$herdrBin" plugin link ${jjWorkspacePluginDir}
          else
            echo "herdr not found; skipping jj-workspace plugin link"
          fi
        '';
    };
  };
}
