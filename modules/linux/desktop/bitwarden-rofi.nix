{ config, options, lib, pkgs, ... }:

with lib;
with lib.my;
let cfg = config.modules.desktop.bitwarden-rofi;
in {
  options.modules.desktop.bitwarden-rofi = {
    enable = mkBoolOpt false;
  };

  config = mkIf cfg.enable {
    user.packages = [
      pkgs.kyle.bitwarden-rofi
    ];
  };
}

