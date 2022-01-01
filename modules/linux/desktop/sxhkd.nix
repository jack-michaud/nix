{ config, options, lib, pkgs, ... }:

with lib;
with lib.my;
let cfg = config.modules.desktop.sxhkd;
in {
  options.modules.desktop.sxhkd = {
    enable = mkBoolOpt false;
  };

  config = mkIf cfg.enable {
    programs.light.enable = true;
    user.extraGroups = [ "video" ];
    home.services.sxhkd = {
      enable = true;

      keybindings = {
        "super + w" = "${pkgs.unstable.google-chrome}/bin/google-chrome-stable";
        "super + a" = "${pkgs.pavucontrol}/bin/pavucontrol";
        "super + n" = "${pkgs.gnome3.networkmanagerapplet}/bin/nm-connection-editor";
        "super + x" = "${pkgs.betterlockscreen}/bin/betterlockscreen -l dim";
        "ctrl + space" = "${pkgs.dunst}/bin/dunstctl close";
        "ctrl + shift + space" = "${pkgs.dunst}/bin/dunstctl close-all";

        # Brightness
        "F5" = "/run/current-system/sw/bin/light -U 5";
        "shift + F5" = "/run/current-system/sw/bin/light -U 1";
        "F6" = "/run/current-system/sw/bin/light -A 5";
        "shift + F6" = "/run/current-system/sw/bin/light -A 1";
      };
    };
  };
}
