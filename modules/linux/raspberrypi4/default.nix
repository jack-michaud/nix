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
      initrd.availableKernelModules = [ "usbhid" "usb_storage" ];
      tmpOnTmpfs = false; # Low ram systems have trouble building (no space left)
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
    boot.loader.systemd-boot.enable = false;

    # These two parameters are the important ones to get the
    # camera working. 
    # This option actually doesn't work to append things to /boot/config.txt. 
    # https://github.com/NixOS/nixpkgs/issues/67792
    # You can manually update the config.txt by mounting the firmware and updating the config manually.
    # mount /dev/disk/by-label/FIRMWARE /mnt
    # cat /mnt/config.txt
    boot.loader.raspberryPi.firmwareConfig = ''
      start_x=1
      gpu_mem=128
    '';


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

