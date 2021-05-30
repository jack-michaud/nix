{ config, options, lib, pkgs, ... }:
with lib;
with lib.my;

let cfg = config.modules.desktop.apps.spotify;
in { 
  options.modules.desktop.apps.spotify = {
    enable = mkBoolOpt false;
  };
}

