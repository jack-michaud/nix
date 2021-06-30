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
    ];

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
        fzf-vim
        coc-nvim
        coc-snippets
        coc-rust-analyzer
        # languages
        vim-nix
        vim-fish
        vim-monokai-pro
        rust-vim
        pkgs.nodePackages.coc-rust-analyzer
      ];
    };
  };
}
