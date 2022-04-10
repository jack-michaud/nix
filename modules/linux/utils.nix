{ config, options, lib, pkgs, ... }:

with lib;
with lib.my;
let cfg = config.modules.utils;
in {
  options.modules.utils = {
    enable = mkBoolOpt false;
  };

  config = mkIf cfg.enable {
    environment.systemPackages = builtins.attrValues (import ../../utilScripts {
      inherit pkgs;
    });
  };
}

