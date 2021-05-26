{ lib, config, pkgs, options, ... }:
{

  networking.networkmanager.enable = true;
  services.gnome.gnome-keyring.enable = true;

  users.users.jack.extraGroups = [ "networkmanager" ];
}

