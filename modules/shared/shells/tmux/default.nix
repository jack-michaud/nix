{ config, options, lib, pkgs, ... }:

with lib;
with lib.my;

let cfg = config.modules.shells.tmux;
in {
  options.modules.shells.tmux = {
    enable = mkBoolOpt false;
  };

  config = mkIf cfg.enable {
    # Equivalent of home-manager's mkOutOfStoreSymlink (which isn't reachable
    # through the darwin-level `home.file` alias): links to the live checkout
    # when dotfiles.dir is a non-store path, so edits apply without a rebuild.
    home.file.".config/tmux".source = pkgs.runCommandLocal "tmux-config" { } ''
      ln -s ${escapeShellArg "${config.dotfiles.dir}/shared/shells/tmux/config"} $out
    '';
  };
}
