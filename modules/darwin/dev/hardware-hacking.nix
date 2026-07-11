{ config, options, lib, pkgs, ... }:
with lib;
with lib.my;

let cfg = config.modules.dev.hardware-hacking;
in {
  config = mkIf cfg.enable {
    homebrew.brews = [
      "mpremote"  # MicroPython remote control: REPL, file transfer over USB serial
    ];
  };
}
