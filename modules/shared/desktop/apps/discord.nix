{ config, options, lib, pkgs, ... }:
with lib;
with lib.my;
let cfg = config.modules.desktop.apps.discord;
in {
  options.modules.desktop.apps.discord = {
    enable = mkBoolOpt false;
  };
}