{ lib, config, pkgs, options, ... }:
{ lib, config, pkgs, options, username, ... }:
{ 
  imports = [
    ./common.nix
    ../homebrew
  ];

  environment.shells = [ pkgs.zsh "/Users/jack/.nix-profile/bin/fish" ];
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
