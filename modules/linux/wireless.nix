{ config, options, lib, ... }:

with lib;
with lib.my;
let cfg = config.modules.wireless;
in {
  options.modules.wireless = { enable = mkBoolOpt false; };

  config = mkIf cfg.enable {
    networking.networkmanager.enable = true;
    #services.gnome.gnome-keyring.enable = true;
    user.extraGroups = [ "networkmanager" ];
  };
}
