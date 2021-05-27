{ pkgs, username, ... }:
{
  home-manager.users."${username}".programs.neovim.extraConfig = ''
    nnoremap <leader>r :Vifm<enter>
    let g:vifm_exec = '${pkgs.vifm}/bin/vifm'
  '';
}

