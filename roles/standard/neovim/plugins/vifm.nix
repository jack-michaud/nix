{ pkgs, ... }:
{
  home-manager.users.jack.programs.neovim.extraConfig = ''
    nnoremap <leader>r :Vifm<enter>
    let g:vifm_exec = '${pkgs.vifm}/bin/vifm'
  '';
}

