# Do not modify this file!  It was generated by ‘nixos-generate-config’
# and may be overwritten by future invocations.  Please make changes
# to /etc/nixos/configuration.nix instead.
{ config, lib, pkgs, modulesPath, ... }:

{
  imports =
    [ (modulesPath + "/installer/scan/not-detected.nix")
    ];

  boot.initrd.availableKernelModules = [ "xhci_pci" "nvme" "rtsx_pci_sdmmc" ];
  boot.initrd.kernelModules = [ ];
  boot.kernelModules = [ "kvm-intel" ];
  boot.extraModulePackages = [ ];

  fileSystems."/" =
    { device = "/dev/disk/by-uuid/c7ac34b5-7010-49f0-a784-9c72613e55fc";
      fsType = "ext4";
    };

  boot.initrd.luks.devices."cryptroot".device = "/dev/disk/by-uuid/b0510e6f-bf46-4b94-b6d7-b786d9ad5e6f";

  fileSystems."/etc/pacman.d/gnupg" =
    { device = "tmpfs";
      fsType = "tmpfs";
    };

  fileSystems."/boot" =
    { device = "/dev/disk/by-uuid/1F9A-0CBC";
      fsType = "vfat";
    };

  fileSystems."/var/lib/docker/overlay2/ff9d3d24ae9c07377f5dbe53f202ea5fe8c72ec7bbcadf16dce6b179f729b142/merged" =
    { device = "overlay";
      fsType = "overlay";
    };

  fileSystems."/var/lib/docker/overlay2/dd6c060032d6df597e5b1e00948479eff61aae1f3b6f647a44052ad9f52ea95c/merged" =
    { device = "overlay";
      fsType = "overlay";
    };

  fileSystems."/var/lib/docker/overlay2/2c59ecd05113e75811cac9ee6cb553c4f4b0ad516fe7fd62befd284289f7e7cd/merged" =
    { device = "overlay";
      fsType = "overlay";
    };

  fileSystems."/var/lib/docker/overlay2/842b3815a88fe86d9e10ca0689ac76d16ee5a6358453ba7b640cdfdecfa1c53f/merged" =
    { device = "overlay";
      fsType = "overlay";
    };

  fileSystems."/var/lib/docker/overlay2/7b6505c1e4a715296fb5f8db4bb56048193ed17a662b8776c471f2c87c612a7f/merged" =
    { device = "overlay";
      fsType = "overlay";
    };

  fileSystems."/var/lib/docker/overlay2/61828ea3abea18ff3d9d17397bb24c416e0b9931aeb78b71384765a913295972/merged" =
    { device = "overlay";
      fsType = "overlay";
    };

  fileSystems."/var/lib/docker/overlay2/473035882f73a21d359a453548a1cfeec6339a7a2800991fb8bc6b6ae02c7664/merged" =
    { device = "overlay";
      fsType = "overlay";
    };

  fileSystems."/var/lib/docker/overlay2/052f4c43d6a0f047b5a7da190cdaa97546f7c357a407f1d89fe5995b9dc092f8/merged" =
    { device = "overlay";
      fsType = "overlay";
    };

  fileSystems."/var/lib/docker/overlay2/387618e71b1a7e49688e0f7c76df664c8032f1b62a9474797d2a4b80389217f1/merged" =
    { device = "overlay";
      fsType = "overlay";
    };

  fileSystems."/var/lib/docker/overlay2/87401413d685f28f9177636d113fbfc85b01d67305c0ceded8ac540372f00df0/merged" =
    { device = "overlay";
      fsType = "overlay";
    };

  fileSystems."/var/lib/docker/overlay2/582f0236b9ad7c07e1a06d8272ee8f79884fefbce2f08f424a823b07249382fd/merged" =
    { device = "overlay";
      fsType = "overlay";
    };

  fileSystems."/var/lib/docker/overlay2/967ca78b1a2f278da1d499e1ab303faddf2a6d57ee09e35179392d4690fb0faa/merged" =
    { device = "overlay";
      fsType = "overlay";
    };

  fileSystems."/var/lib/docker/overlay2/dc8a8384860cc9aa47ac9564bf6e3364923a345a8c5afccc15594265f7e6dc35/merged" =
    { device = "overlay";
      fsType = "overlay";
    };

  fileSystems."/var/lib/docker/overlay2/0f34ed7747862551a5ae04dbac8742150ebfcdba651ed435eb5504367fe67d9e/merged" =
    { device = "overlay";
      fsType = "overlay";
    };

  swapDevices =
    [ { device = "/dev/disk/by-uuid/6f8a776e-f825-42a2-ac66-c80a3a0d0138"; }
    ];

  powerManagement.cpuFreqGovernor = lib.mkDefault "powersave";
}