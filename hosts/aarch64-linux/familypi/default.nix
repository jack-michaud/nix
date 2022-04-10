# Edit this configuration file to define what should be installed on
# your system.  Help is available in the configuration.nix(5) man page
# and in the NixOS manual (accessible by running ‘nixos-help’).

{ config, pkgs, ... }:

{
  imports =
    [ # Include the results of the hardware scan.
      ./hardware-configuration.nix
    ];

  config = {

    # The global useDHCP flag is deprecated, therefore explicitly set to false here.
    # Per-interface useDHCP will be mandatory in the future, so this generated config
    # replicates the default behaviour.
    networking.useDHCP = false;
    networking.interfaces.eth0.useDHCP = true;
    networking.interfaces.wlan0.useDHCP = true;
    networking.firewall.allowedTCPPorts = [ 22 80 443 5000 8080 ];

    #hardware.raspberry-pi."4".fkms-3d.enable = true;

    services.octoprint = {
      enable = true;
      port = 5000;
      plugins = plugins: with plugins; [
        stlviewer printtimegenius
      ];
      extraConfig = {
        reverseProxy = {
          trustedDownstream = ["192.168.101.204"];
        };
      };
    };
    boot.kernelModules = [ "bcm2835-v4l2" ];


    systemd.services.streamer = {
      wantedBy = ["multi-user.target"];
      description = "A stream of the CSI camera attached to my 3d printer";
      serviceConfig = {
        Type = "simple";
        ExecStart = "${pkgs.mjpg-streamer}/bin/mjpg_streamer -i 'input_uvc.so -d /dev/video0 -r 1280x720' -o 'output_http.so -p 8080'";
      };
    };

    # This value determines the NixOS release from which the default
    # settings for stateful data, like file locations and database versions
    # on your system were taken. It‘s perfectly fine and recommended to leave
    # this value at the release version of the first install of this system.
    # Before changing this value read the documentation for this option
    # (e.g. man configuration.nix or on https://nixos.org/nixos/options.html).
    system.stateVersion = "21.05"; # Did you read the comment?
    vault-secrets = {
      secrets = {
        familypi = {
          namespace = "hosts";
          environmentKey = "production";
          environmentFile = "/root/vault-secrets.sh";
          services = ["acme-internal.lomz.me"];
        };
      };
    };
  };


  config.modules = {
    raspberrypi4.enable = true;
    #editors.nvim.enable = true;
    shells.fish.enable = true;
    services = {
    #  nextcloud = {
    #    enable = true;
    #    host = "nextcloud.internal.lomz.me";
    #    port = 8081;
    #  };
      ssh.enable = true;
    };
    #dev.arion.enable = true;
    #dev.docker.enable = true;
    wireless.enable = true;
  };

}

