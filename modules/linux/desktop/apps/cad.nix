{ config, options, lib, pkgs, ... }:

with lib;
with lib.my;
let cfg = config.modules.desktop.apps.cad;
in {
  options.modules.desktop.apps.cad = {
    enable = mkBoolOpt false;
  };

  config = mkIf cfg.enable {
    environment.systemPackages = [
      pkgs.freecad
      pkgs.prusa-slicer
    ];
  };
}

