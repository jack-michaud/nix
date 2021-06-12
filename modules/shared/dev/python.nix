{ config, options, lib, pkgs, ... }:

with lib;
with lib.my;
let cfg = config.modules.dev.python;
in {
  options.modules.dev.python = {
    enable = mkBoolOpt true;
  };

  config = mkIf cfg.enable {
    env.PYTHONPATH = [ "$HOME/.local/lib/python3.9/site-packages" ];
    home.packages = [
      pipenv
      poetry
      python39
      python39Packages.pip
    ];
  };
}

