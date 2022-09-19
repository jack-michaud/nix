{ config, options, lib, pkgs, ... }:

with lib;
with lib.my;
let cfg = config.modules.wms.xmonad;
in {
  options.modules.wms.xmonad = { enable = mkBoolOpt false; };

  config = mkIf cfg.enable {

    environment.systemPackages = [ pkgs.betterlockscreen ];
    services.xserver = {
      enable = true;
      libinput.enable = true;
      windowManager.xmonad.enable = true;
      displayManager.defaultSession = "none+xmonad";
    };
    security.pam.services.gdm.enableGnomeKeyring = true;
    home.xsession = {
      enable = true;
      windowManager.xmonad = {
        enable = true;
        enableContribAndExtras = true;
        config = ../../../config/xmonad/Main.hs;
        extraPackages = haskellPackages: [
          haskellPackages.dbus
          haskellPackages.List
          haskellPackages.monad-logger
          haskellPackages.xmonad
          haskellPackages.xmonad-contrib
          haskellPackages.containers_0_6_6
          haskellPackages.xmobar
        ];
      };
    };
    home.programs.xmobar = {
      enable = true;
      extraConfig = ''
        Config
        { font        = "Iosevka"
        , borderColor = "#d0d0d0"
        , border      = FullB
        , borderWidth = 3
        , bgColor     = "#222"
        , fgColor     = "grey"
        , position    = TopSize C 99 30
        , commands    =
            [ Run Weather "KASH"
              [ "--template", "<weather> <tempF>°F"
                          , "-L", "30"
                          , "-H", "80"
                          , "--low"   , "lightblue"
                          , "--normal", "#f8f8f2"
                          , "--high"  , "red"
                          ] 36000
            , Run Cpu ["-t", "cpu: <fc=#4eb4fa><bar> <total>%</fc>"] 10
            , Run Network "enp0s25" ["-S", "True", "-t", "eth: <fc=#4eb4fa><rx></fc>/<fc=#4eb4fa><tx></fc>"] 10
            , Run Memory ["-t","mem: <fc=#4eb4fa><usedbar> <usedratio>%</fc>"] 10
            , Run Date "date: <fc=#4eb4fa>%a %d %b %Y %H:%M:%S </fc>" "date" 10
            , Run Battery ["-a", "notify-send -u critical 'Battery running out!!'"
            ] 180

            , Run XMonadLog
            ]
        , sepChar     = "%"
        , alignSep    = "}{"
        , template    = "  %XMonadLog% | %cpu% | %memory% | %enp0s25%  }{ %KASH% | %date% | %battery%"
        }
      '';
    };
  };
}
