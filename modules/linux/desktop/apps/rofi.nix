{ config, options, lib, pkgs, ... }:
with lib;
with lib.my;

let cfg = config.modules.desktop.apps.rofi;
in {
  options.modules.desktop.apps.rofi = {
    enable = mkBoolOpt false;
  };

  config = mkIf cfg.enable {
    home.programs.rofi = {
      enable = true;
      # Theming was done in xresources
      extraConfig = {
        modi = "drun,emoji";
        kb-primary-paste = "Alt+V";
        kb-primary-copy = "Alt+C";
      };

      package = pkgs.rofi.override {
        plugins = [ pkgs.rofi-emoji ];
      };
    };
  };
}
