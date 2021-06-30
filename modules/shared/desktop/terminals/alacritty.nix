{ lib, config, options, pkgs, ... }:

with lib;
with lib.my;
let cfg = config.modules.desktop.terminals.alacritty;
in {
  options.modules.desktop.terminals.alacritty = {
    enable = mkBoolOpt false;
  };

  config = mkIf cfg.enable {
    fonts.fonts = [
      pkgs.iosevka-bin
    ];
    home.programs.alacritty = {
      enable = true;
      settings = {
        env = {
          "TERM" = "xterm-256color";
          "SHELL" = "fish";
        };
        window = {
          padding = {
            x = 10;
            y = 10;
          };
        };
        font = {
          normal.family = "Iosevka";
          size = 13.0;
        };
        colors = {
          primary = {
            background = "#2D2A2E";
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
  };
}
