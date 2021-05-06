{ lib, config, pkgs, options, ... }:
{
  imports = [
    ./common.nix
  ];

  boot.loader.systemd-boot.enable = true;

  environment.sessionVariables.EDITOR = "nvim";

  i18n.defaultLocale = "en_US.UTF-8";

  # Define a user account. Don't forget to set a password with ‘passwd’.
  users.users.jack = {
    isNormalUser = true;
    extraGroups = [ "wheel" ];
    initialPassword = "jack";
    openssh.authorizedKeys.keys = [
      "ecdsa-sha2-nistp521 AAAAE2VjZHNhLXNoYTItbmlzdHA1MjEAAAAIbmlzdHA1MjEAAACFBAHXhwJc/cmSfds8ZZmFPVZC7j7mEV8fqnU+IKqAo5fqEDZSOZ2Th949rn3B3+iaZ3yxNog2151Yp8h5ivez3PmFOAGon3qjC9gcWcmxzjcytkZHdJaxOmpHmiuJj44UFq87tETmj+V8+hbyTGvtqTuB5aPhYmVCfApOnQSfbBY1uAnRgA== jack@CASTOR"
    ];
    shell = pkgs.fish;
  };

  environment.systemPackages = with pkgs; [
    firefox
    discord
    obsidian
    vifm
  ];

}

