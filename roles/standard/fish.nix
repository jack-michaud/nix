{ pkgs, home-manager, ... }:
{
  home-manager.users.jack.programs.fish = {
    shellInit = ''
      set fish_greeting ""
    '';
  };
}
