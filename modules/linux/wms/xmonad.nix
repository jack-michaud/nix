{ config, options, lib, pkgs, ... }:

with lib;
with lib.my;
let cfg = config.modules.wms.xmonad;
in {
  options.modules.wms.xmonad = { enable = mkBoolOpt false; };

  config = mkIf cfg.enable {
    security.pam.services.gdm.enableGnomeKeyring = true;
    services.xserver = {
      enable = true;
      libinput.enable = true;
      windowManager = {
        xmonad = {
          enable = true;
          enableContribAndExtras = true;
          extraPackages = haskellPackages: [
            haskellPackages.dbus
            haskellPackages.List
            haskellPackages.monad-logger
            haskellPackages.xmonad
            haskellPackages.xmonad-contrib
          ];
          config = ./../../../config/xmonad;
        };
      };
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
  };
}
