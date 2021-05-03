{ home-manager, pkgs, utils, ... }:
{
  home-manager.users.jack.services.sxhkd = {
    enable = true;

    keybindings = {
      "super + w" = "${pkgs.firefox}/bin/firefox";
      "super + a" = "${pkgs.pavucontrol}/bin/pavucontrol";
    };
  };

} 
