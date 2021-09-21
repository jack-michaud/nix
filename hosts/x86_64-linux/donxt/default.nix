{ config, pkgs, ... }:
{
  imports =
    [ # Include the results of the hardware scan.
      ./hardware-configuration.nix
    ];

  # Use the Systemd boot loader.
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
  networking.firewall.allowedTCPPorts = [ 60022 ];
  # Or disable the firewall altogether.
  # networking.firewall.enable = false;

  # This value determines the NixOS release from which the default
  # settings for stateful data, like file locations and database versions
  # on your system were taken. It‘s perfectly fine and recommended to leave
  # this value at the release version of the first install of this system.
  # Before changing this value read the documentation for this option
  # (e.g. man configuration.nix or on https://nixos.org/nixos/options.html).
  system.stateVersion = "21.05"; # Did you read the comment?

  users.users.root = {
    openssh.authorizedKeys.keys = [
      "ecdsa-sha2-nistp521 AAAAE2VjZHNhLXNoYTItbmlzdHA1MjEAAAAIbmlzdHA1MjEAAACFBADtu5UDZalYPNDPW2cJVu/6T+DbwYDKNT9eCsvEuy8Lh4HC9UOywhXvEc/2qs5oPdqw2S3SmxZkq6DhB6PI5Q10GQGv7+Czntrtlas9qvAKxH9Uu8UcXeshFhvmng8JU9n+4KLysGNo6gA6W/Cjp8z45nJFJs2xgjF9qgwiuQV+ZD/W1w== jack@ajax"
    ];
  };
}
