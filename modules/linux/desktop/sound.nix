{ config, options, lib, isDarwin, pkgs, ... }:

with lib;
with lib.my;

let cfg = config.modules.desktop.sound;
in {
  options.modules.desktop.sound = { enable = mkBoolOpt false; };

  config = mkIf cfg.enable {
    assertions = [{
      assertion = !isDarwin;
      message = "Cannot enable pulseaudio on darwin (desktop.sound)";
    }];
    # sound.enable = true;
    # hardware.pulseaudio = {
    #   enable = true;
    #   package = pkgs.pulseaudio.override { jackaudioSupport = true; };
    # };
  };
}
