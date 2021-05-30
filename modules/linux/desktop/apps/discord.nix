{ config, options, lib, pkgs, ... }:
with lib;
with lib.my;

let cfg = config.modules.desktop.apps.discord;
in { 
  config = mkIf cfg.enable {
    environment.systemPackages = [
      pkgs.unstable.discord
    ];
  };
}
