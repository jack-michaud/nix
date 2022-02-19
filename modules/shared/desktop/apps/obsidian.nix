{ config, options, lib, pkgs, generators, ... }:

with lib;
with lib.my;

let cfg = config.modules.desktop.apps.obsidian;
in {
  options.modules.desktop.apps.obsidian = { enable = mkBoolOpt false; };

  config = mkIf cfg.enable {
    #home.configFile = let 
    #  obsidian-theme = generators.toCSSFile ../../../../config/obsidian-theme/default.scss;
    #in {
    #  "${config.dotfiles.vaultDir}/personal/.obsidian/themes/theme.css".source = obsidian-theme;
    #  "${config.dotfiles.vaultDir}/private/.obsidian/themes/theme.css".source = obsidian-theme;
    #};
  };
}
