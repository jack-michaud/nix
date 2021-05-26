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
      sxhkd = {
        enable = true;
      };
    };
    wms.dwm = {
      enable = true;
    };
    editors.nvim = {
      enable = true;
    };
  };
  
}
