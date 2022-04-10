{ config, options, lib, pkgs, ... }:

with lib;
with lib.my;
let cfg = config.modules.dev.git;
in {
  options.modules.dev.git = {
    enable = mkBoolOpt false;
  };

  config = mkIf cfg.enable {
    home.programs.git = {
      enable = true;
      userName = "Jack Michaud";
      userEmail = "jack@lomz.me";

      iniContent = {
        init = {
          defaultBranch = "main";
        };
      };
    };

    environment.systemPackages = [
      pkgs.github-cli
    ];
  };
}
