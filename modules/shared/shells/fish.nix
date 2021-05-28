{ config, options, lib, pkgs, ... }:

with lib;
with lib.my;

let cfg = config.modules.shells.fish;
in {
  options.modules.shells.fish = {
    enable = mkBoolOpt false;
  };

  config = mkIf cfg.enable {
    home.programs.fish = {
      enable = true;
      package = pkgs.fish;
      shellInit = ''
        set fish_greeting ""
        alias dcl="docker-compose logs"
        alias dcd="docker-compose down"
        alias dcu="docker-compose up"
        alias dcp="docker-compose ps"
      '';
    };
    user = {
      shell = pkgs.fish;
    };
  };
}
