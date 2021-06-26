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

    services.nginx = {
      enable = true;
      virtualHosts = {
        "internal.lomz.me" = {
          forceSSL = true;
          root = "/var/www/internal.lomz.me";
          useACMEHost = "internal.lomz.me";
        };
        "docs.internal.lomz.me" = {
          forceSSL = true;
          root = "${pkgs.nix.doc}/share/doc/nix/manual";
          useACMEHost = "internal.lomz.me";
        };
        "vault.internal.lomz.me" = {
          forceSSL = true;
          locations."/" = {
            proxyPass = "http://192.168.0.7:8200";
          };
          useACMEHost = "internal.lomz.me";
        };
      };
    };
    security.acme = {
      acceptTerms = true;
      email = "jack@lomz.me";
      certs."internal.lomz.me" = {
        domain = "*.internal.lomz.me";
        extraDomainNames = [ "internal.lomz.me" ];
        dnsProvider = "route53";
        group = "nginx";
        credentialsFile = "/run/secrets/familypi/environment";
      };
    };

    # The global useDHCP flag is deprecated, therefore explicitly set to false here.
    # Per-interface useDHCP will be mandatory in the future, so this generated config
    # replicates the default behaviour.
    networking.useDHCP = false;
    networking.interfaces.eth0.useDHCP = true;
    networking.interfaces.wlan0.useDHCP = true;
    networking.firewall.allowedTCPPorts = [ 80 443 ];

    #hardware.raspberry-pi."4".fkms-3d.enable = true;

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
    editors.nvim.enable = true;
    shells.fish.enable = true;
    services.ssh.enable = true;
    dev.podman.enable = true;
  };

}

