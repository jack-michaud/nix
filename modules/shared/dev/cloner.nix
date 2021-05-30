{ config, options, lib, pkgs, ... }:

with lib;
with lib.my;
let cfg = config.modules.dev.cloner;
in {
  options.modules.dev.cloner = {
    enable = mkBoolOpt true;
  };

  config = mkIf cfg.enable {
    environment.systemPackages = [
      pkgs.my.cloner
    ];
  };
}

