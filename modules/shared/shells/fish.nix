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
        alias dcr="docker-compose restart"
        alias dce="docker-compose exec"
        alias scratchdir="cd (mktemp -d /tmp/scratch.XXX)"

        alias ls="${pkgs.exa}/bin/exa"
        alias cat="${pkgs.bat}/bin/bat"

        # cd into a Code directory
        alias coad="cd (find ${config.dotfiles.codeDir} -maxdepth 3 | fzf)"
      '';
    };
    user = {
      shell = pkgs.fish;
    };
  };
}
