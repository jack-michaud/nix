{ lib, config, pkgs, options, ... }:
{ 
  imports = [
    ./common.nix
  ];

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
  environment.variables.SHELL = "fish";

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

}
