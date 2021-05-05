{ home-manager, pkgs, utils, ... }:
{
  home-manager.users.jack.services.sxhkd = {
    enable = true;

    keybindings = {
      "super + w" = "${pkgs.firefox}/bin/firefox";
      "super + a" = "${pkgs.pavucontrol}/bin/pavucontrol";
      "super + n" = "${pkgs.gnome3.networkmanagerapplet}/bin/nm-connection-editor";

      # Brightness
      "F5" = "/run/current-system/sw/bin/light -U 5";
      "F6" = "/run/current-system/sw/bin/light -A 5";
    };
  };

} 
