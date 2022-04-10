{ config, options, lib, pkgs, ... }:
with lib;
with lib.my;

let cfg = config.modules.desktop.apps.gimp;
in { 
  options.modules.desktop.apps.gimp = {
    enable = mkBoolOpt false;
  };

  config = mkIf cfg.enable {
    environment.systemPackages = [
      pkgs.gimp
    ];
  };
}
