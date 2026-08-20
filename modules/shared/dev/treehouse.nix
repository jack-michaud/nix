{ config, options, lib, pkgs, inputs, ... }:

with lib;
with lib.my;
let
  cfg = config.modules.dev.treehouse;
  # Jack's fork of kunchenguid/treehouse (vcs-seam branch), built from source
  # by the input's own flake. The fork adds a Jujutsu (jj) backend; which
  # backend runs is selected at runtime by TREEHOUSE_VCS (unset = git, same
  # behaviour as upstream).
  treehouse = inputs.treehouse.packages.${pkgs.system}.default;
in {
  options.modules.dev.treehouse = {
    enable = mkBoolOpt false;
  };

  # Everything goes through `home-manager.users.<user>` rather than system
  # options: the binary is a per-user dev tool, and `home.sessionVariables`
  # is what the repo's zshrc actually sources (via hm-session-vars.sh), so
  # the variable reaches login shells on darwin. DARKFOREST's standalone
  # home-manager bridge folds this namespace back into its native `home.*`
  # (see hosts/x86_64-linux/DARKFOREST/home.nix), including sessionVariables.
  config = mkIf cfg.enable {
    home-manager.users.${config.user.name} = {
      home.packages = [ treehouse ];

      # Opt treehouse into its jj backend for Jack's repositories. Without
      # this the fork behaves exactly like upstream git treehouse.
      home.sessionVariables.TREEHOUSE_VCS = "jj";
    };
  };
}
