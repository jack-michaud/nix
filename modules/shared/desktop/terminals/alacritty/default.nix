{ config, options, lib, pkgs, ... }:

with lib;
with lib.my;

let cfg = config.modules.desktop.terminals.alacritty;
in {
  options.modules.desktop.terminals.alacritty = {
    enable = mkBoolOpt false;
  };

  config = mkIf cfg.enable {
    fonts.packages = [ pkgs.nerd-fonts.iosevka ];

    # Installs the nixpkgs alacritty (>=0.15, fixes the kitty-keyboard-protocol
    # double Enter/Backspace bug in 0.14). Settings stay empty so home-manager
    # doesn't generate a config file; the live checkout is symlinked instead.
    home.programs.alacritty.enable = true;

    # Equivalent of home-manager's mkOutOfStoreSymlink (which isn't reachable
    # through the darwin-level `home.file` alias): links to the live checkout
    # when dotfiles.dir is a non-store path, so edits apply without a rebuild.
    home.file.".config/alacritty/alacritty.toml".source =
      pkgs.runCommandLocal "alacritty-config" { } ''
        ln -s ${escapeShellArg "${config.dotfiles.modulesDir}/shared/desktop/terminals/alacritty/config/alacritty.toml"} $out
      '';
  };
}
