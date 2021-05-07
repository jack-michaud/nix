{ pkgs, home-manager, username, ... }:
{
  home-manager.users."${username}".programs.fish = {
    enable = true;
    shellInit = ''
      set fish_greeting ""
    '';
  };
}
