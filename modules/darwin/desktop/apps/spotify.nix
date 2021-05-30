{ config, options, lib, pkgs, ... }:
with lib;
with lib.my;
let cfg = config.modules.desktop.apps.spotify;
in {
  config = mkIf cfg.enable {
    homebrew.casks = [
      "spotify"
    ];
  };
}