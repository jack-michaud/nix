{ config, options, lib, pkgs, ... }:

with lib;
with lib.my;
let cfg = config.modules.desktop.apps.cad;
in {
  options.modules.desktop.apps.cad = { enable = mkBoolOpt false; };

  config = mkIf cfg.enable {
    environment.systemPackages = with pkgs; [
      # unstable.freecad # I'm on the openscad grind! 
      openscad
      prusa-slicer
    ];
  };
}
