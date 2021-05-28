{ config, options, lib, isDarwin, ... }:

with lib;
with lib.my;

let cfg = config.modules.desktop.sound;
in {
  options.modules.desktop.sound = {
    enable = mkBoolOpt false;
  };

  config = if !isDarwin then (mkIf cfg.enable {
    assertions = [
      {
        assertion = !isDarwin;
        message = "Cannot enable pulseaudio on darwin (desktop.sound)";
      }
    ];
    sound.enable = true;
    hardware.pulseaudio.enable = true;
  }) else {};
}
