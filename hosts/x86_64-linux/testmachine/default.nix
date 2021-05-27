{ config, ... }:
{
  imports = [
    ./hardware-configuration.nix
  ];


  config.modules = {
    dev = {
      docker = {
        enable = true;
      };
    };
    desktop = {
      sound.enable = true;
      terminals = {
        alacritty = {
          enable = true;
        };
      };
      sxhkd = {
        enable = true;
      };
    };
    wms.dwm = {
      enable = false;
    };
    editors.nvim = {
      enable = true;
    };
    shells.fish.enable = true;
    services = {
      syncthing.enable = true;
      ssh.enable = true;
    };
  };
  
}
