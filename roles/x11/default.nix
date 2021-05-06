{ lib, config, pkgs, options, dwm, ... }:
{
  imports = [
    ./rofi.nix
    ./sxhkd.nix
    ./light.nix
    ./picom.nix
    ./xresources.nix
  ];

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

  environment.systemPackages = with pkgs; [
    xclip
    xbrightness
    feh
  ];

  services.xserver.displayManager.sessionCommands = ''
    date > /tmp/date
    ${pkgs.feh}/bin/feh --bg-scale --no-xinerama ~/Downloads/yz6ggt7m18l41.png
    while true; do
      ${(pkgs.callPackage ./dwm-status.nix {})}/bin/dwmStatus
      sleep 3 &
    done &
  '';
  # Enable touchpad support (enabled default in most desktopManager).
  services.xserver.libinput.enable = true;
}
