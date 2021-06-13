# Default overrides for Raspberry Pi 4 machines.
# https://nixos.wiki/wiki/NixOS_on_ARM/Raspberry_Pi_4

{ config, options, lib, pkgs, ... }:

with lib;
with lib.my;
let cfg = config.modules.raspberrypi4;
in {
  options.modules.raspberrypi4 = {
    enable = mkBoolOpt false;
  };

  config = mkIf cfg.enable {

    boot = {
      kernelPackages = pkgs.linuxPackages_rpi4;
      tmpOnTmpfs = true;
      initrd.availableKernelModules = [ "usbhid" "usb_storage" ];
      kernelParams = [
        "8250.nr_uarts=1"
        "console=ttyAMA0,115200"
        "console=tty1"
        # Some gui programs need this
        "cma=128M"
      ];

    };

    boot.loader.raspberryPi = {
      enable = true;
      version = 4;
    };
    boot.loader.grub.enable = false;
    boot.loader.generic-extlinux-compatible.enable = true;

    # Required for the Wireless firmware
    hardware.enableRedistributableFirmware = true;

    nix = {
      autoOptimiseStore = true;
      gc = {
        automatic = true;
        dates = "weekly";
        options = "--delete-older-than 30d";
      };
      # Free up to 1GiB whenever there is less than 100MiB left.
      extraOptions = ''
        min-free = ${toString (100 * 1024 * 1024)}
        max-free = ${toString (1024 * 1024 * 1024)}
      '';
    };
  };
}

