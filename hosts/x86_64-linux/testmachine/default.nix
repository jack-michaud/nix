{ config, ... }:
{
  imports = [
    ./hardware-configuration.nix
  ];

  config.modules.editors.nvim = {
    enable = true;
  };
  
}
