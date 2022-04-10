{ config, options, lib, pkgs, ... }:

with lib;
with lib.my;
let cfg = config.modules.desktop.apps.chrome;
in {
  options.modules.desktop.apps.chrome = {
    enable = mkBoolOpt false;
  };

  config = mkIf cfg.enable {
    environment.systemPackages = [
      pkgs.unstable.google-chrome
    ];
  };
}

