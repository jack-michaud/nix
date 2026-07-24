{ config, options, lib, pkgs, inputs, ... }:

with lib;
with lib.my;
let
  cfg = config.modules.dev.agent-harness;
in {
  options.modules.dev.agent-harness = {
    enable = mkBoolOpt false;
  };

  config = mkIf cfg.enable {
    environment.systemPackages = [
      inputs.agent-harness.packages.${pkgs.system}.agent-harness
    ];
  };
}
