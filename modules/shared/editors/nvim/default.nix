{ config, options, lib, pkgs, ... }:

with lib;
with lib.my;
let cfg = config.modules.editors.nvim;
in {
  options.modules.editors.nvim = {
    enable = mkBoolOpt false;
  };

  config = mkIf cfg.enable {
    env.EDITOR = "nvim";

    environment.systemPackages = [
      pkgs.ag
      pkgs.vifm
      pkgs.terraform-ls
      pkgs.unstable.nodePackages.coc-rust-analyzer
    ];

    home.programs.neovim = {
      enable = true;
      viAlias = true;
      vimAlias = true;
      withNodeJs = true;
      withPython3 = true;
      extraConfig = (builtins.readFile "${config.dotfiles.configDir}/nvim/init.vim");
      plugins = (pkgs.unstable.callPackage ./_plugins/default.nix { inherit pkgs; }).plugins;
    };

    home.configFile."nvim/coc-settings.json" = {
      text = readFile ../../../../config/nvim/coc-settings.json;
    };

  };

  # Extra plugin config:
  imports = [./_plugins/black.nix];
}
