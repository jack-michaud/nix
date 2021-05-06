{ pkgs, home-manager, username, ... }:
{
  home-manager.users."${username}".programs.fish = {
    shellInit = ''
      set fish_greeting ""
    '';
  };
}
