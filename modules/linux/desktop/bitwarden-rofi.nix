{ config, options, lib, pkgs, kyle-sferrazza-overlay, ... }:

with lib;
with lib.my;
let cfg = config.modules.desktop.bitwarden-rofi;
in {
  options.modules.desktop.bitwarden-rofi = {
    enable = mkBoolOpt true;
  };

  config = mkIf cfg.enable {
    user.packages = [
      kyle-sferrazza-overlay.bitwarden-rofi
    ];
  };
}

