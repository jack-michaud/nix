{ config, options, lib, pkgs, ... }:

with lib;
with lib.my;
let cfg = config.modules.desktop.dunst;
in {
  options.modules.desktop.dunst = { enable = mkBoolOpt false; };

  config = mkIf cfg.enable {
    systemd.user.services."dunst" = {
      enable = true;
      description = "";
      wantedBy = [ "default.target" ];
      serviceConfig.Restart = "always";
      serviceConfig.RestartSec = 2;
      serviceConfig.ExecStart = "${pkgs.dunst}/bin/dunst";
    };
    home.configFile."dunst/dunstrc" = {
      text = readFile ../../config/dunst/dunstrc;
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
