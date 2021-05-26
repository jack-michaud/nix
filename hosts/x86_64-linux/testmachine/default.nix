{ config, ... }:
{
  imports = [
    ./hardware-configuration.nix
  ];


  config.modules = {
    wms.dwm = {
      enable = true;
    };
    editors.nvim = {
      enable = true;
    };
  };
  
}
