{ config, pkgs, ... }:
{
  config = {
    system.stateVersion = 4;
    services.nix-daemon.enable = false;

    modules = {
      homebrew.enable = true;
      dev = {
        git.enable = true;
        cloner.enable = false;
      };
      editors = {
        nvim.enable = false;
      };
      shells = {
        fish.enable = true;
      };
      desktop = {
        terminals.alacritty.enable = true;
        apps = {
          obsidian.enable = true;
          code.enable = true;
          spotify.enable = true;
        };
      };
      services = {
        syncthing.enable = true;
      };
    };
  };

}

