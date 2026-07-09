{ config, options, lib, pkgs, ... }:

with lib;
with lib.my;

let cfg = config.modules.desktop.jankyborders;
in {
  options.modules.desktop.jankyborders = {
    enable = mkBoolOpt false;
  };

  config = mkIf cfg.enable {
    # Draws a colored border around Alacritty windows (alacritty has no
    # native border support). Colors match the Monokai Pro rice in
    # modules/shared/desktop/terminals/alacritty and the herdr accent.
    services.jankyborders = {
      enable = true;
      style = "round";
      width = 8.0;
      hidpi = true;
      active_color = "0xffffd866"; # Monokai yellow
      inactive_color = "0xff727072"; # Monokai bright black
      whitelist = [ "Alacritty" ];
    };
  };
}
