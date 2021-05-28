{ lib, config, pkgs, options, ... }:
{ 

  environment.shells = [ pkgs.zsh "/Users/jack/.nix-profile/bin/fish" ];
  environment.systemPath = [ "/usr/local/bin/" ];

  # Make Fish the default shell
  programs.fish.enable = true;
  # Needed to address bug where $PATH is not properly set for fish:
  # https://github.com/LnL7/nix-darwin/issues/122
  programs.fish.shellInit = ''
    for p in (string split : ${config.environment.systemPath})
      if not contains $p $fish_user_paths
        set -g fish_user_paths $fish_user_paths $p
      end
    end
  '';
  env.SHELL = "fish";

  system.defaults = {
    dock = {
      show-recents = false;
      autohide = true;
    };
    finder = {
      # show desktop icons
      CreateDesktop = false;
      # warn on changing file extension
      FXEnableExtensionChangeWarning = false;
      # show file extensions
      AppleShowAllExtensions = true;
    };
    NSGlobalDomain = {
      # dark mode
      AppleInterfaceStyle = "Dark";
      # hide menu bar
      _HIHideMenuBar = false;
    };
  };

  services.yabai.enable = false;
  services.yabai.package = pkgs.yabai;
  services.yabai.extraConfig = ''
    yabai -m config mouse_follows_focus          off
    yabai -m config focus_follows_mouse          off
    yabai -m config window_placement             second_child
    yabai -m config window_topmost               off
    yabai -m config window_shadow                on
    yabai -m config window_opacity               off
    yabai -m config window_opacity_duration      0.0
    yabai -m config active_window_opacity        1.0
    yabai -m config normal_window_opacity        0.90
    yabai -m config window_border                off
    yabai -m config window_border_width          6
    yabai -m config active_window_border_color   0xff775759
    yabai -m config normal_window_border_color   0xff555555
    yabai -m config insert_feedback_color        0xffd75f5f
    yabai -m config split_ratio                  0.50
    yabai -m config auto_balance                 off
    yabai -m config mouse_modifier               fn
    yabai -m config mouse_action1                move
    yabai -m config mouse_action2                resize
    yabai -m config mouse_drop_action            swap

    yabai -m config layout                       bsp
    yabai -m config top_padding                  12
    yabai -m config bottom_padding               12
    yabai -m config left_padding                 12
    yabai -m config right_padding                12
    yabai -m config window_gap                   06
  '';
}
