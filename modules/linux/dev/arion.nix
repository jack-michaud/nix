{ config, options, lib, pkgs, ... }:

with lib;
with lib.my;
let cfg = config.modules.dev.arion;
in {
  options.modules.dev.arion = {
    enable = mkBoolOpt false;
  };

  config = mkIf cfg.enable {
    # https://docs.hercules-ci.com/arion/
    environment.systemPackages = [
      pkgs.arion
      # Do install the docker CLI to talk to podman.
      # Not needed when virtualisation.docker.enable = true;
      pkgs.docker-client
    ];

    # Arion works with Docker, but for NixOS-based containers, you need Podman
    # since NixOS 21.05.
    #virtualisation.docker.enable = false;
    #virtualisation.podman.enable = true;
    #virtualisation.podman.dockerSocket.enable = true;
    #virtualisation.podman.defaultNetwork.dnsname.enable = true;

    # Use your username instead of `myuser`
    user.extraGroups = ["podman"];
  };
}

