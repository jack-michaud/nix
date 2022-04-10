{ config, options, lib, pkgs, ... }:

with lib;
with lib.my;
let cfg = config.modules.desktop.apps.code;
in {
  config = mkIf cfg.enable {
    environment.systemPackages = [
      pkgs.unstable.vscode
    ];
  };
}

