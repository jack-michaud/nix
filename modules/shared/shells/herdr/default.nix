{ config, options, lib, pkgs, ... }:

with lib;
with lib.my;

let cfg = config.modules.shells.herdr;
in {
  options.modules.shells.herdr = {
    enable = mkBoolOpt false;
  };

  config = mkIf cfg.enable {
    # Only config.toml is managed — ~/.config/herdr also holds runtime state
    # (logs, sockets, session.json) that must stay writable.
    # Equivalent of home-manager's mkOutOfStoreSymlink (which isn't reachable
    # through the darwin-level `home.file` alias): links to the live checkout
    # when dotfiles.dir is a non-store path, so edits apply without a rebuild.
    home.file.".config/herdr/config.toml".source =
      pkgs.runCommandLocal "herdr-config" { } ''
        ln -s ${escapeShellArg "${config.dotfiles.dir}/shared/shells/herdr/config/config.toml"} $out
      '';
  };
}
