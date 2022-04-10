{ config, options, lib, pkgs, ... }:
with lib;
with lib.my;
let cfg = config.modules.services.syncthing;
in {
  config = mkIf cfg.enable {
    homebrew.casks = [
      "syncthing"
    ];
  };
}