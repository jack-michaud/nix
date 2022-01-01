{ config, pkgs, ... }:
{
  imports =
    [ # Include the results of the hardware scan.
      ./hardware-configuration.nix
    ];

  # Use the Systemd boot loader.
  config = {
    boot.loader.systemd-boot.enable = true;
    nix.useSandbox = true;

    networking.hostName = "donxt";

    # Set your time zone.
    time.timeZone = "America/Los_Angeles";
  
    # The global useDHCP flag is deprecated, therefore explicitly set to false here.
    # Per-interface useDHCP will be mandatory in the future, so this generated config
    # replicates the default behaviour.
    networking.useDHCP = false;
    networking.interfaces.ens3.useDHCP = true;
  
    # Select internationalisation properties.
    i18n.defaultLocale = "en_US.UTF-8";
  
    # List packages installed in system profile. To search, run:
    # $ nix search wget
    environment.systemPackages = with pkgs; [
      vim # Do not forget to add an editor to edit configuration.nix! The Nano editor is also installed by default.
    #   wget
    #   firefox
  ];
  
    # Enable the OpenSSH daemon.
    services.openssh.enable = true;
    services.openssh.ports = [ 60022 ];
  
    # Open ports in the firewall.
    networking.firewall.allowedTCPPorts = [
      60022 8200 80 443
    ];
    # Or disable the firewall altogether.
    # networking.firewall.enable = false;
  
    # This value determines the NixOS release from which the default
    # settings for stateful data, like file locations and database versions
    # on your system were taken. It‘s perfectly fine and recommended to leave
    # this value at the release version of the first install of this system.
    # Before changing this value read the documentation for this option
    # (e.g. man configuration.nix or on https://nixos.org/nixos/options.html).
    system.stateVersion = "21.05"; # Did you read the comment?
  
    services.consul = {
      enable = true;
      extraConfig = {
        bootstrap_expect = 1;
        server = true;
      };
      interface = {
        bind = "ens3";
        advertise = "ens3";
      };
    };
    modules = {
      services = {
        vault = {
          enable = true;
          address = "192.168.101.204:8200";
        };
        ssh.enable = true;
        tailscale.enable = true;
      };
    };
  
    # Retrieve secrets from Vault. Namely:
    # - AWS creds for updating DNS with acme
    vault-secrets = {
      secrets = {
        donxt = {
          namespace = "hosts";
          environmentKey = "production";
          environmentFile = "/root/vault-secrets.sh";
          services = ["acme-internal.lomz.me"];
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
        credentialsFile = "/run/secrets/donxt/environment";
      };
    };
    services.gitea = {
      enable = true;
      domain = "git.internal.lomz.me";
      rootUrl = "https://git.internal.lomz.me";
      ssh = {
        enable = true;
        clonePort = 60022;
      };
    };
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
        "git.internal.lomz.me" = {
          forceSSL = true;
          locations."/" = {
            proxyPass = let
              host = config.services.gitea.httpAddress;
              port = config.services.gitea.httpPort;
            in 
              "http://" + host + ":" + toString port;
          };
          useACMEHost = "internal.lomz.me";
        };
        "vault.internal.lomz.me" = {
          forceSSL = true;
          locations."/" = {
            proxyPass = "http://192.168.101.204:8200";
          };
          useACMEHost = "internal.lomz.me";
        };
      };
    };
  };
}
