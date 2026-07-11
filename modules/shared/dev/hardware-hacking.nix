{ config, options, lib, pkgs, ... }:
with lib;
with lib.my;

let cfg = config.modules.dev.hardware-hacking;
in {
  options.modules.dev.hardware-hacking = {
    enable = mkBoolOpt false;
  };
}
