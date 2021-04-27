{ lib, config, pkgs, options, ... }:
{
  fonts.fonts = [
    (pkgs.callPackage ./iosevka.nix {})
  ];

  home-manager.users.jack.programs.alacritty = {
    enable = true;
    settings = {
      env = {
        "TERM" = "xterm-256color";
      };
      window = {
        padding = {
          x = 10;
          y = 10;
        };
      };
      font = {
        normal.family = "Iosevka Fixed";
        size = 11.0;
      };
      colors = {
        primary = {
          background = "#272822";
          foreground = "#f1ebeb";
        };
      };
      key_bindings = [
        {
          key = "V";
          mods = "Alt";
          action = "Paste";
        }
        {
          key = "C";
          mods = "Alt";
          action = "Copy";
        }
        {
          key = "U";
          mods = "Alt";
          action = "ScrollPageUp";
        }
        {
          key = "D";
          mods = "Alt";
          action = "ScrollPageDown";
        }
        {
          key = "N";
          mods = "Alt";
          action = "ScrollToBottom";
        }
      ];
    };
  };
}
