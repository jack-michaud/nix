{ config, options, lib, pkgs, ... }:

let cfg = options.modules.tools.openvpn;
in {
  options.modules.tools.openvpn = {
    enable = mkBoolOpt false;
  };

  config = mkIf cfg.enable {
    environment.systemPackages = [
      openvpn
    ];
  };
}
