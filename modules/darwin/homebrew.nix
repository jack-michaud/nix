{ config, options, lib, pkgs, ... }:

with lib;
with lib.my;

let cfg = config.modules.homebrew;
in {
  options.modules.homebrew = {
    enable = mkBoolOpt false;
  };

  config = mkIf cfg.enable {
    homebrew = {
      enable = true;
      autoUpdate = true;
      cleanup = "zap";
      extraConfig = ''
        cask_args appdir: "~/Applications"
      '';
      taps = [
        "homebrew/cask"
        "homebrew/cask-drivers"
        "homebrew/cask-fonts"
        "homebrew/cask-versions"
        "homebrew/core"
        "homebrew/services"
      ];
    };
  };
}
