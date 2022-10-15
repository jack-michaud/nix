{ config, options, lib, pkgs, generators, ... }:
with lib;
with lib.my;

let cfg = config.modules.desktop.apps.obsidian;
in {
  config = mkIf cfg.enable {
    environment.systemPackages = [ pkgs.unstable.obsidian ];
  };
}
