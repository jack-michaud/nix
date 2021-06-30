{ config, lib, pkgs, ... }:
{
  imports =
    [ # Include the results of the hardware scan.
      ./hardware-configuration.nix
    ];

  config = {
    networking = {
      hostName = "ajax"; # Define your hostname.
    };

    # Set your time zone.
    time.timeZone = "America/Los_Angeles";

    # The global useDHCP flag is deprecated, therefore explicitly set to false here.
    # Per-interface useDHCP will be mandatory in the future, so this generated config
    # replicates the default behaviour.
    networking.useDHCP = false;
    networking.interfaces.enp0s25.useDHCP = true;
    networking.interfaces.wlp4s0.useDHCP = true;

    # Some programs need SUID wrappers, can be configured further or are
    # started in user sessions.
    # programs.mtr.enable = true;
    # programs.gnupg.agent = {
    #   enable = true;
    #   enableSSHSupport = true;
    # };

    # Open ports in the firewall.
    networking.firewall.allowedTCPPorts = [ 
      22 # ssh
      8200 # vault
    ];
    # Or disable the firewall altogether.
    # networking.firewall.enable = false;

    # This value determines the NixOS release from which the default
    # settings for stateful data, like file locations and database versions
    # on your system were taken. It‘s perfectly fine and recommended to leave
    # this value at the release version of the first install of this system.
    # Before changing this value read the documentation for this option
    # (e.g. man configuration.nix or on https://nixos.org/nixos/options.html).
    #system.stateVersion = "20.09"; # Did you read the comment?
    services.consul = {
      enable = true;
      extraConfig = {
        bootstrap_expect = 1;
        server = true;
      };
      interface = {
        bind = "wlp4s0";
        advertise = "wlp4s0";
      };
    };

    vault-secrets = {
      secrets = {
        ajax = {
          namespace = "hosts";
          environmentFile = "/root/vault-secrets.sh";
          user = config.user.name;
          group = "nobody";
        };
      };
    };
  };

  config.modules = {
    dev = {
      docker.enable = true;
      git.enable = true;
      cloner.enable = true;
      python.enable = true;
      go.enable = true;
    };
    desktop = {
      sound.enable = true;
      bitwarden-rofi.enable = true;
      terminals = {
        alacritty = {
          enable = true;
        };
      };
      apps = {
        firefox.enable = true;
        rofi.enable = true;
        discord.enable = true;
        signal.enable = true;
        slack.enable = true;
        steam.enable = true;
        spotify.enable = true;
        gimp.enable = true;

        # writing 
        obsidian.enable = true;
        logseq.enable = true;

        code.enable = true;
        # Doom is kinda broken.
        emacs.enable = false;

        email.enable = true;
      };
      sxhkd = {
        enable = true;
      };
    };
    wms.dwm.enable = true;
    editors.nvim.enable = true;
    shells.fish.enable = true;
    services = {
      syncthing.enable = true;
      ssh.enable = true;
      vault = {
        enable = true;
        address = "192.168.0.7:8200";
      };
      duplicati = {
        enable = true;
        parameters = ''
          --verbose=true
          --webservice-port=8201
        '';
      };
    };
    wireless.enable = true;
    tools.wireguard.enable = true;
    tools.openvpn.enable = true;
  };
}

