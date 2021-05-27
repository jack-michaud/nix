{ config, options, lib, ... }:

with lib;
with lib.my;

let cfg = config.modules.desktop.sound;
in {
  options.modules.desktop.sound = {
    enable = mkBoolOpt false;
  };

  config = mkIf cfg.enable {
    sound.enable = true;
    hardware.pulseaudio.enable = true;
  };
}

