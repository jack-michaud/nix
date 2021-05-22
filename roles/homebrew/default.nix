{ config, pkgs, username, ... }:

let
  user_brew_taps = [
    "homebrew/cask"
    "homebrew/cask-drivers"
    "homebrew/cask-fonts"
    "homebrew/cask-versions"
    "homebrew/core"
    "homebrew/services"
  ];
  user_brew_formulae = [
    "choose-gui"
  ];
  user_brew_casks = [
    "bitwarden"
    "hiddenbar"
    "obsidian"
    "ransomwhere"
    "syncthing"
    "visual-studio-code"
  ];
  #user_mas_apps = {
  #  WireGuard = 1451685025;
  #};
in {
  homebrew = {
    enable = true;
    autoUpdate = true;
    cleanup = "zap";
    extraConfig = ''
      cask_args appdir: "~/Applications"
    '';
    taps = user_brew_taps;
    brews = user_brew_formulae;
    casks = user_brew_casks;
    #masApps = user_mas_apps;
  };
 
}
