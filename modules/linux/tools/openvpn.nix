{ config, options, lib, pkgs, ... }:

with lib;
with lib.my;

let cfg = config.modules.tools.openvpn;
in {
  options.modules.tools.openvpn = {
    enable = mkBoolOpt false;
  };

  config = mkIf cfg.enable {
    environment.systemPackages = [
      pkgs.openvpn
    ];
  };
}
