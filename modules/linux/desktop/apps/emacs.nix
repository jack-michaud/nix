{ config, options, pkgs, inputs, lib, doom-emacs, ... }:
with lib;
with lib.my;

let cfg = config.modules.desktop.apps.emacs;
in {
  options.modules.desktop.apps.emacs = {
    enable = mkBoolOpt false;
  };

  config = mkIf cfg.enable {
    env.PATH = [ "$XDG_CONFIG_HOME/emacs/bin" ];
    #nixpkgs.overlays = [ inputs.emacs-overlay.overlay ];

    user.packages = with pkgs; let 
      doom-emacs = callPackage (fetchFromGitHub {
        owner = "vlaci";
        repo = "nix-doom-emacs";
        rev = "master";
        sha256 = "0a9df4sg9bq13zvd6cgc1qidmzd9lll55fx25d9frm5fl7jrn561";
      }) {
        doomPrivateDir = ../../../../config/doom.d;
      };
    in [
      doom-emacs
      #emacsPgtkGcc
      git
      imagemagick         # for image-dired
      zstd                # for undo-fu-session/undo-tree compression
      (aspellWithDicts (ds: with ds; [
        en en-computers en-science
      ]))
      pinentry_emacs # in-emacs gnupg prompts
    ];

    fonts.fonts = [ pkgs.emacs-all-the-icons-fonts ];

    #home.configFile = let 
    #  doom-emacs = pkgs.fetchFromGitHub {
    #    owner = "hlissner";
    #    repo = "doom-emacs"; 
    #    rev = "develop";
    #    sha256 = "07mfxi3h0c66w7jx3a5vbfs0w3rglbdkk3hc7cnk7zsygiv2f235";
    #  }; 
    #in {
    #  emacs.source = doom-emacs.outPath;
    #  doom.source = ../../../config/doom.d;
    #};
  };
}
