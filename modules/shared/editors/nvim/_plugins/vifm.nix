{ pkgs, username, ... }:
{
  home-manager.users."${username}".programs.neovim.extraConfig = ''
    nnoremap <leader>r :Vifm<enter>
  '';
}

