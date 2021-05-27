{ config, options, lib, pkgs, ... }:

with lib;
with lib.my;
let cfg = config.modules.editors.nvim;
in {
  options.modules.editors.nvim = {
    enable = mkBoolOpt false;
  };

  config = mkIf cfg.enable {
    environment.sessionVariables.EDITOR = "nvim";

    home.programs.neovim = {
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

        " Fuzzy find
        nnoremap <leader>F :Files<enter>
        nnoremap <leader>G :Rg<enter>
        nnoremap <leader>b :Buffers<enter>
        nnoremap <leader>S :cex system("rg --column ")<Left><Left>

        " Opens Git link for selected line or region in browser
        noremap <leader>gb  :Gbrowse<Enter>
        " Adding hunks with :Gstatus - https://vi.stackexchange.com/a/21410
        "  - Press "=" on an file (shows git diff)
        "  - Press "-" on a hunk or visual selection to stage/unstage
        "  - "cvc" to commit verbosely
        noremap <leader>gs  :Git<Enter>
        noremap <leader>gl  :Glog<Enter>
      '';
      plugins = with pkgs.vimPlugins; [
        vim-fugitive
        vim-rhubarb
        vim-dispatch
        vim-sneak
        vim-nix
        fzf-vim
        coc-nvim
      ];
    };
  };
}
