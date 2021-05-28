{ config, options, lib, ... }:

with lib;
with lib.my;
let cfg = config.modules.services.syncthing;
    username = config.user.name;
in {
  options.modules.services.syncthing = {
    enable = mkBoolOpt false;
  };
  config = mkIf cfg.enable {
    services.syncthing = {
      enable = true;
      user = username;
      openDefaultPorts = true;
      dataDir = "/home/${username}/Sync";
    };
  };
}

