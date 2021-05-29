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

    home.programs.neovim = {
      enable = true;
      viAlias = true;
      vimAlias = true;
      withNodeJs = true;
      withPython3 = true;
      extraConfig = (builtins.readFile "${config.dotfiles.configDir}/nvim/init.vim");
      plugins = with pkgs.vimPlugins; [
        vim-fugitive
        vim-rhubarb
        vim-dispatch
        vim-sneak
        vim-nix
        fzf-vim
        coc-nvim
        coc-snippets
      ];
    };
  };
}
