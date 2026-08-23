{ config, options, lib, pkgs, inputs, ... }:

with lib;
with lib.my;
let
  cfg = config.modules.dev.treehouse;
  # Upstream kunchenguid/treehouse (v2.3.0 release), built from source by
  # the input's own flake. v2.3.0 is the first release with the merged
  # Jujutsu (jj) backend; which backend runs is selected at runtime by
  # TREEHOUSE_VCS (unset = git, the pre-2.3.0 behaviour).
  #
  # nativeCheckInputs is extended with python3 because v2.3.0's checkPhase
  # executes the repo's real no-mistakes CI gate script, whose attestation
  # parser needs python3 on PATH (it reports UNPARSEABLE without it).
  # Upstream's flake omits it since GitHub's ubuntu-latest runner has
  # python3 ambiently; the nix build sandbox does not, so the gate tests
  # fail there. Adding the interpreter keeps the tests running instead of
  # disabling doCheck.
  treehouse = inputs.treehouse.packages.${pkgs.system}.default.overrideAttrs
    (old: {
      nativeCheckInputs = (old.nativeCheckInputs or [ ]) ++ [ pkgs.python3 ];
    });
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
      # this treehouse keeps its default git backend.
      home.sessionVariables.TREEHOUSE_VCS = "jj";
    };
  };
}
