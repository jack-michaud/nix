{ config, options, lib, pkgs, ... }:

with lib;
with lib.my;

let cfg = config.modules.desktop.apps.email;
in { 
  options.modules.desktop.apps.email = {
    enable = mkBoolOpt false;
  };

  config = mkIf cfg.enable {
    environment.systemPackages = [
      pkgs.thunderbird
      pkgs.unstable.protonmail-bridge
    ];
  };
}
