{ config, options, lib, pkgs, ... }:
with lib;
with lib.my;
let cfg = config.modules.shells.fish;
in {
  config = mkIf cfg.enable {
    environment.shells = [ "/Users/jack/.nix-profile/bin/fish" ];

    # Make Fish the default shell
    programs.fish.enable = true;
    # Needed to address bug where $PATH is not properly set for fish:
    # https://github.com/LnL7/nix-darwin/issues/122
    programs.fish.shellInit = ''
      for p in (string split : ${config.environment.systemPath})
        if not contains $p $fish_user_paths
          set -g fish_user_paths $fish_user_paths $p
        end
      end
    '';
    env.SHELL = "fish";
    
  };
}