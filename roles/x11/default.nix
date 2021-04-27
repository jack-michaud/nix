{ lib, config, pkgs, options, dwm, ... }:
{

  # Enable the X11 windowing system.
  services.xserver.enable = true;
  # Configure keymap in X11
  services.xserver.layout = "us";

  services.xserver.displayManager.lightdm.enable = true;
  services.xserver.windowManager.dwm.enable = true;
  #services.xserver.windowManager.i3 = {
  #  enable = true;
  #  package = pkgs.i3-gaps;
  #};

  fonts.fonts = [
    pkgs.font-awesome_5
  ];

  # Enable touchpad support (enabled default in most desktopManager).
  services.xserver.libinput.enable = true;
}
