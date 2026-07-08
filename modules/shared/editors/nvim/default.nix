{ config, options, lib, pkgs, dotfiles, ... }:

with lib;
with lib.my;
let cfg = config.modules.editors.nvim;
in {
  options.modules.editors.nvim = {
    enable = mkBoolOpt false;
  };

  config = mkIf cfg.enable {
    env.EDITOR = "nvim";

    # Equivalent of home-manager's mkOutOfStoreSymlink (which isn't reachable
    # through the darwin-level `home.file` alias): links to the live checkout
    # when dotfiles.dir is a non-store path, so edits apply without a rebuild.
    home.file.".config/nvim".source = pkgs.runCommandLocal "nvim-config" { } ''
      ln -s ${escapeShellArg "${config.dotfiles.modulesDir}/shared/editors/nvim/config"} $out
    '';

  };

}
