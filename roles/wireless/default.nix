{ lib, config, pkgs, options, ... }:
{

  networking.networkmanager.enable = true;
  services.gnome3.gnome-keyring.enable = true;

  users.users.jack.extraGroups = [ "networkmanager" ];
}

