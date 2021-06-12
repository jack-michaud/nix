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
    user.packages = with pkgs; [
      pipenv
      poetry
      python39Packages.python
      python39Packages.pip
    ];
  };
}

