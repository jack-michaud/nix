{ config, options, lib, pkgs, ... }:

with lib;
with lib.my;
let cfg = config.modules.dev.nixGcc;
in {
  options.modules.dev.nixGcc = {
    enable = mkBoolOpt true;
  };

  config = mkIf cfg.enable {
    environment.systemPackages = [ pkgs.gcc ];
  };
}
