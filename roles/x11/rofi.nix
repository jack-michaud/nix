{ home-manager, pkgs, username, ... }:
{
  
  home-manager.users."${username}".programs.rofi = {
    enable = true;
    # Theming was done in xresources
    extraConfig = {
      modi = "drun,emoji";
      kb-primary-paste = "Alt+V";
      kb-primary-copy = "Alt+C";
    };

    package = pkgs.rofi.override {
      plugins = [ pkgs.rofi-emoji ];
    };
  };
}
