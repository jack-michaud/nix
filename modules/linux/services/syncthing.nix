{ config, options, lib, ... }:

with lib;
with lib.my;
let cfg = config.modules.services.syncthing;
    username = config.user.name;
in {
  config = mkIf cfg.enable {
    services.syncthing = {
      enable = true;
      user = username;
      openDefaultPorts = true;
      dataDir = "/home/${username}/Sync";
    };
  };
}

