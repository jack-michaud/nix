{ config, options, lib, pkgs, ... }:

with lib;
with lib.my;

let cfg = config.modules.shells.zsh;
in {
  options.modules.shells.zsh = {
    enable = mkBoolOpt false;
  };

  config = mkIf cfg.enable {
    # Equivalent of home-manager's mkOutOfStoreSymlink (which isn't reachable
    # through the darwin-level `home.file` alias): links to the live checkout
    # when dotfiles.dir is a non-store path, so edits apply without a rebuild.
    # Secrets stay out of the repo in ~/.zshrc.local, sourced at the end.
    home.file.".zshrc".source = pkgs.runCommandLocal "zshrc" { } ''
      ln -s ${escapeShellArg "${config.dotfiles.dir}/shared/shells/zsh/config/zshrc"} $out
    '';
  };
}
