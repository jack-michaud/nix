{ options, config, lib, pkgs, ... }:

with lib;
with lib.my;
{
  config = mkIf config.services.xserver.enable {
    # Configure keymap in X11
    services.xserver.layout = "us";
    fonts.fonts = [
      pkgs.font-awesome_5
    ];
    environment.systemPackages = with pkgs; [
      xclip
      xbrightness
      feh
      mesa_drivers
      libnotify
    ];

    home.file.".Xresources".source = "${config.dotfiles.configDir}/x/Xresources";
  };
}
