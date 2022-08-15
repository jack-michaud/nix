{ config, options, lib, pkgs, ... }:

with lib;
with lib.my;
let cfg = config.modules.desktop.picom;
in {
  options.modules.desktop.picom = { enable = mkBoolOpt false; };

  config = mkIf cfg.enable {
    services.picom = {
      enable = true;
      activeOpacity = 1.0;
      inactiveOpacity = 0.8;
      backend = "glx";
      fade = true;
      fadeDelta = 5;
      # opacityRule = [ "100:name *= 'i3lock'" ];
      shadow = true;
      shadowOpacity = 0.75;
      settings = {
        corner-radius = 5;
        blur-method = "dual_kawase";
        blur-strength = "10";
        xinerama-shadow-crop = true;
      };
    };
  };
}
