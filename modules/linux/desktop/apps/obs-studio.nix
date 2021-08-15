{ config, options, lib, pkgs, ... }:

with lib;
with lib.my;
let cfg = config.modules.desktop.apps.obs-studio;
in {
  options.modules.desktop.apps.obs-studio = {
    enable = mkBoolOpt false;
  };

  config = mkIf cfg.enable {
    user.packages = with pkgs; [
      obs-studio
      obs-v4l2sink
    ];
  };
}

