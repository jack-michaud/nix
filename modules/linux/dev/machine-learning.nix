{ config, options, lib, pkgs, ... }:

with lib;
with lib.my;
let cfg = config.modules.dev.machine-learning;
in {
  options.modules.dev.machine-learning = {
    enable = mkBoolOpt false;
  };

  config = mkIf cfg.enable {
    environment.systemPackages = [
      pkgs.python39Packages.pyopengl
    ];
  };
}

