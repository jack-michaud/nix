{ config, options, lib, pkgs, ... }:
with lib;
with lib.my;
let cfg = config.modules.desktop.apps.code;
in {
  options.modules.desktop.apps.code = {
    enable = mkBoolOpt false;
  };

  config = mkIf cfg.enable {
    homebrew.casks = [
      "obsidian"
    ];
  };
}