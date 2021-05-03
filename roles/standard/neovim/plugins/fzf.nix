{ ... }:
{
  home-manager.users.jack.programs.neovim.extraConfig = ''
    nnoremap <leader>F :Files<enter>
    nnoremap <leader>G :Rg<enter>
    nnoremap <leader>b :Buffers<enter>
    nnoremap <leader>S :cex system("rg --column ")<Left><Left>
  '';
}
