{ config, options, lib, pkgs, ... }:

with lib;
with lib.my;
let cfg = config.modules.desktop.apps.logseq;
in {
  options.modules.desktop.apps.logseq = {
    enable = mkBoolOpt true;
  };

  config = mkIf cfg.enable {
    user.packages = [ pkgs.logseq ];
  };
}

