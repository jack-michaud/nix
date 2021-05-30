{ config, pkgs, ... }:
{
  imports = [
    ../../../roles/standard/darwin.nix
    (import ../../../roles/homebrew/default.nix { work = true; dev = true; personal = false; })
  ];
  config = {
    system.stateVersion = 4;
    services.nix-daemon.enable = false;

    modules = {
      dev = {
        git.enable = true;
        cloner.enable = true;
      };
      editors = {
        nvim.enable = true;
      };
      shells = {
        fish.enable = true;
      };
      desktop = {
        terminals.alacritty.enable = true;
        apps = {
          obsidian.enable = true;
        };
      };
    };
  };

}

