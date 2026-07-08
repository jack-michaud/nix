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

    # Equivalent of home-manager's mkOutOfStoreSymlink, which isn't reachable
    # through the darwin-level `home.file` alias.
    home.file.".config/nvim".source = pkgs.runCommandLocal "nvim-config" { } ''
      ln -s ${escapeShellArg "${config.dotfiles.dir}/modules/shared/editors/nvim/config"} $out
    '';

  };

}
