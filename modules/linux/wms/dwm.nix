{ options, config, lib, pkgs, ... }:

with lib;
with lib.my;
let cfg = config.modules.wms.dwm;
in {
  options.modules.wms.dwm = { enable = mkBoolOpt false; };

  config = mkIf cfg.enable {
    #assertions = [
    #  {
    #    assertion = isStorePath "${pkgs.dwm}/bin/dwmStatus";
    #    message = "Must provide dwmStatus binary in dwm package. Is dwm being properly overlayed?"; 
    #  }
    #];
    # Enable the X11 windowing system.
    services.xserver.enable = true;
    security.pam.services.lightdm.enableGnomeKeyring = true;
    services.xserver.windowManager.dwm.enable = true;
    services.xserver.displayManager.sessionCommands = ''
      ${pkgs.feh}/bin/feh --bg-scale --no-xinerama ${
        ../themes/dark-blue/wallpaper/image.png
      }
      while true; do
        ${pkgs.dwm}/bin/dwmStatus
        sleep 3 &
      done &
    '';

    home.xsession = {
      enable = true;
      windowManager.command = "${pkgs.dwm}/bin/dwm";
    };

    systemd.user.services."dunst" = {
      enable = true;
      description = "";
      wantedBy = [ "default.target" ];
      serviceConfig.Restart = "always";
      serviceConfig.RestartSec = 2;
      serviceConfig.ExecStart = "${pkgs.dunst}/bin/dunst";
    };
    home.configFile."dunst/dunstrc" = {
      text = readFile ../../../config/dunst/dunstrc;
      onChange = ''
        pkillVerbose=""
        if [[ -v VERBOSE ]]; then
          pkillVerbose="-e"
        fi
        $DRY_RUN_CMD ${pkgs.procps}/bin/pkill -u $USER $pkillVerbose dunst || true
        unset pkillVerbose
      '';
    };

    # Enable touchpad support (enabled default in most desktopManager).
    services.xserver.libinput.enable = true;

  };
}
