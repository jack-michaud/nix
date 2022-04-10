{ config, options, lib, ... }:

with lib;
with lib.my;
let cfg = config.modules.services.syncthing;
    username = config.user.name;
in {
  options.modules.services.syncthing = {
    enable = mkBoolOpt false;
  };
}

