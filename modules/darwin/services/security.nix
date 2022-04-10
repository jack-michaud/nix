# Security modules
{ config, options, lib, pkgs, ... }:
with lib;
with lib.my;
let cfg = config.modules.services.security;
in {
  options.modules.services.security = {
    enable = mkBoolOpt false;
  };

  config = mkIf cfg.enable {
    homebrew.casks = [
      "ransomwhere"
    ];
  };
}