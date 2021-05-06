{ pkgs, home-manager, username, ... }:
{
  imports = [
    ./plugins
  ];
  home-manager.users."${username}".programs.neovim = {
    enable = true;
    viAlias = true;
    vimAlias = true;
    withNodeJs = true;
    withPython3 = true;
    extraConfig = ''
      let mapleader = "`"
      map <Space> <leader>

      inoremap jk <Esc>

      " Copy to clipboard
      vnoremap  <leader>y  "+y
      nnoremap  <leader>Y  "+yg_
      nnoremap  <leader>y  "+y
      nnoremap  <leader>yy  "+yy

      " Paste from clipboard
      nnoremap <leader>p "+p
      nnoremap <leader>P "+P
      vnoremap <leader>p "+p
      vnoremap <leader>P "+P

      " File Browser
      let g:netrw_liststyle = 3
      let g:netrw_banner = 0
      let g:netrw_browse_split = 4
      let g:netrw_winsize = 20
      let g:netrw_altv = 20
      noremap <leader>r :Vexplore<Enter>

    '';
  };
}
