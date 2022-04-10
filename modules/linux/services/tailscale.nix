{ options, config, lib, pkgs, ... }:
with lib;
with lib.my;
let cfg = config.modules.services.tailscale;
in {
  options.modules.services.tailscale = {
    enable = mkBoolOpt false;
  };

  config = mkIf cfg.enable {
    services.tailscale = {
      enable = true;
    };
    environment.systemPackages = [
      pkgs.tailscale
    ];
  };
}
