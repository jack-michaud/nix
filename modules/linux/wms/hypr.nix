{ inputs, options, config, lib, pkgs, ... }:

with lib;
with lib.my;
let
  cfg = config.modules.wms.hypr;
  hypr = inputs.hyprland;
in {
  options.modules.wms.hypr = { enable = mkBoolOpt false; };

  config = mkIf cfg.enable {
    security.pam.services.gdm.enableGnomeKeyring = true;
    programs = {
      hyprland.enable = true;
      light.enable = true;
    };

    nixpkgs.overlays = [ hypr.overlays.default ];
    environment.systemPackages = with pkgs; [
      wofi
      waybar-hyprland
      pipewire
      wireplumber
      xdg-desktop-portal-hyprland
      hyprpicker
      wl-clipboard
      hyprpaper
      grimblast
      grim
      slurp
    ];
  };
}
