{ options, config, lib, pkgs, ... }:

with lib;
with lib.my; {
  config = mkIf config.services.xserver.enable {
    # Configure keymap in X11
    services.xserver.layout = "us";
    fonts.fonts = [ pkgs.font-awesome_5 ];
    environment.systemPackages = with pkgs; [
      xclip
      xbrightness
      feh
      mesa.drivers
      libnotify
      jq
    ];

    home.file.".Xresources".source =
      "${config.dotfiles.configDir}/x/Xresources";

    # Enables gnome keyring to unlock on login.
    security.pam.services.jack.enableGnomeKeyring = true;
    services.gnome.gnome-keyring.enable = true;
  };
}
