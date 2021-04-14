{ lib, config, pkgs, options, ... }:
{
  # Enable the OpenSSH daemon.
  services.openssh = {
    enable = true;
    forwardX11 = true;
    permitRootLogin = lib.mkForce "no";
    passwordAuthentication = false;
  };

}
