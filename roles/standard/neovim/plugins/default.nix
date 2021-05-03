{ pkgs, ... }:
let
  plugins = with pkgs.vimPlugins; [
    vim-fugitive
    vim-nix
    fzf-vim
    coc-nvim
    vim-easymotion
  ];
in {
  imports = [
    ./fzf.nix
    ./fugitive.nix
  ];
  home-manager.users.jack.programs.neovim.plugins = plugins;
}
