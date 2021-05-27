{ config, options, lib, pkgs, ... }:
with lib;
with lib.my;
let cfg = config.modules.desktop.messaging;
in { 
  options.modules.desktop.messaging = {
    discord = mkBoolOpt false;
    slack = mkBoolOpt false;
    signal = mkBoolOpt false;
  };

  config = (mkIf cfg.discord {
    environment.systemPackages = [
      pkgs.discord
    ];
  }) 
  // (mkIf cfg.signal {
    environment.systemPackages = [
      pkgs.signal-desktop
    ];
  })
  // (mkIf cfg.slack {
    environment.systemPackages = [
      pkgs.slack
    ];
  });
}
