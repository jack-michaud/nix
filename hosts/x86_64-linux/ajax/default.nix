{ config, pkgs, lib, ... }:
{
  imports =
    [ # Include the results of the hardware scan.
      ./hardware-configuration.nix
      #../../../roles/standard/linux.nix
      #../../../roles/ssh
      #../../../roles/x11
      #../../../roles/sound
      #../../../roles/wireless
      #../../../roles/sync
      #../../../roles/personal-messaging
      #../../../roles/dev
    ];

  config = {
    networking = {
      hostName = "ajax"; # Define your hostname.
      nameservers = [ "192.168.0.250" "1.1.1.1" ];
    };

    # Set your time zone.
    time.timeZone = "America/Los_Angeles";

    # The global useDHCP flag is deprecated, therefore explicitly set to false here.
    # Per-interface useDHCP will be mandatory in the future, so this generated config
    # replicates the default behaviour.
    networking.useDHCP = false;
    networking.interfaces.enp0s25.useDHCP = true;
    networking.interfaces.wlp4s0.useDHCP = true;

    virtualisation.docker.enable = true;

    # Some programs need SUID wrappers, can be configured further or are
    # started in user sessions.
    # programs.mtr.enable = true;
    # programs.gnupg.agent = {
    #   enable = true;
    #   enableSSHSupport = true;
    # };

    # Open ports in the firewall.
    # networking.firewall.allowedUDPPorts = [ ... ];
    # Or disable the firewall altogether.
    # networking.firewall.enable = false;

    # This value determines the NixOS release from which the default
    # settings for stateful data, like file locations and database versions
    # on your system were taken. It‘s perfectly fine and recommended to leave
    # this value at the release version of the first install of this system.
    # Before changing this value read the documentation for this option
    # (e.g. man configuration.nix or on https://nixos.org/nixos/options.html).
    #system.stateVersion = "20.09"; # Did you read the comment?
  };

  config.modules = {
    dev = {
      docker.enable = true;
      git.enable = true;
    };
    desktop = {
      sound.enable = true;
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
        obsidian.enable = true;
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
    };
    wireless.enable = true;
    tools.wireguard.enable = true;
  };
}

