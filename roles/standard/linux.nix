{ lib, config, pkgs, options, username, ... }:
{
  imports = [
    ./common.nix
  ];

  boot.loader.systemd-boot.enable = true;

  environment.sessionVariables.EDITOR = "nvim";

  i18n.defaultLocale = "en_US.UTF-8";

  # Define a user account. Don't forget to set a password with ‘passwd’.
  users.users.${username} = {
    isNormalUser = true;
    extraGroups = [ "wheel" ];
    initialPassword = "${username}";
    openssh.authorizedKeys.keys = [
      "ecdsa-sha2-nistp521 AAAAE2VjZHNhLXNoYTItbmlzdHA1MjEAAAAIbmlzdHA1MjEAAACFBAHXhwJc/cmSfds8ZZmFPVZC7j7mEV8fqnU+IKqAo5fqEDZSOZ2Th949rn3B3+iaZ3yxNog2151Yp8h5ivez3PmFOAGon3qjC9gcWcmxzjcytkZHdJaxOmpHmiuJj44UFq87tETmj+V8+hbyTGvtqTuB5aPhYmVCfApOnQSfbBY1uAnRgA== jack@CASTOR"
    ];
  };

  environment.systemPackages = with pkgs; [
    firefox
    obsidian
    vifm
    betterlockscreen
  ];
}

