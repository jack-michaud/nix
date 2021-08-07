{ config, options, lib, pkgs, ... }:

with lib;
with lib.my;
let cfg = config.modules.wms.gnome;
in {
  options.modules.wms.gnome = {
    enable = mkBoolOpt false;
  };

  config = mkIf cfg.enable {
    desktopManager.gnome = {
      enable = true;
    };
  };
}

