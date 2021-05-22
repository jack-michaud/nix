{ pkgs, home-manager, username, ... }:
{
  home-manager.users."${username}".programs.fish = {
    enable = true;
    shellInit = ''
      set fish_greeting ""
      alias dcl="docker-compose logs"
      alias dcd="docker-compose down"
      alias dcu="docker-compose up"
      alias dcp="docker-compose ps"
    '';
  };
}
