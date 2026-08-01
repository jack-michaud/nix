{ config, options, lib, pkgs, inputs, ... }:

with lib;
with lib.my;
let
  cfg = config.modules.dev.agent-harness;
  agent-harness = inputs.agent-harness.packages.${pkgs.system}.agent-harness;
  # Expose the agent-harness CLI under the `aether-lance` alias on PATH, so
  # it works in any shell (a zsh alias would only exist interactively).
  aether-lance = pkgs.runCommand "aether-lance" { } ''
    mkdir -p $out/bin
    ln -s ${agent-harness}/bin/agent-harness $out/bin/aether-lance
  '';
in {
  options.modules.dev.agent-harness = {
    enable = mkBoolOpt false;
  };

  config = mkIf cfg.enable {
    environment.systemPackages = [
      agent-harness
      aether-lance
    ];
  };
}
