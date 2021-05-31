# Linux specific options and config
{ config, options, lib, home-manager, ... }:

with lib;
with lib.my;
{
  config = {
    user = {
      extraGroups = [ "wheel" ];
      isNormalUser = true;
      group = "users";
      uid = 1000;
      initialPassword = "${config.user.name}";
      home = "/home/${config.user.name}";
    };

    # Install user packages to /etc/profiles instead. Necessary for
    # nixos-rebuild build-vm to work.
    home-manager = {
      useUserPackages = true;
    };
  };
}
