{ config, options, lib, pkgs, ... }:

with lib;
with lib.my;
let cfg = config.modules.dev.docker;
in {
  options.modules.dev.docker = {
    enable = mkBoolOpt false;
  };

  config = mkIf cfg.enable {
    virtualisation.docker.enable = true;
    environment.systemPackages = with pkgs; [
      docker-compose
    ];
    user.extraGroups = [ "docker" ];
  };
}
