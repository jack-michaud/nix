{ config, options, lib, isDarwin, pkgs, ... }:

with lib;
with lib.my;

let cfg = config.modules.desktop.bluetooth;
in {
  options.modules.desktop.bluetooth = { enable = mkBoolOpt false; };

  config = mkIf cfg.enable {
    sound.enable = true;
    services.blueman.enable = true;
    hardware.bluetooth.enable = true;
    hardware.pulseaudio = { };

    hardware.pulseaudio.extraConfig = ''
      load-module module-bluetooth-policy
      load-module module-bluetooth-discover
      ## module fails to load with 
      ##   module-bluez5-device.c: Failed to get device path from module arguments
      ##   module.c: Failed to load module "module-bluez5-device" (argument: ""): initialization failed.
      # load-module module-bluez5-device
      # load-module module-bluez5-discover
    '';
  };
}
