{ pkgs, username, ... }:
let
  customPlugin = { repo, owner, rev, sha256 }:
  pkgs.vimUtils.buildVimPlugin {
    name = repo;
    src = pkgs.fetchFromGitHub {
      inherit owner repo rev sha256;
    };
  };
  custom = map customPlugin [
    {
      owner = "vifm";
      repo = "vifm.vim";
      rev = "822ce3f18dbe6d801a3cd135403a828ed2ccb0d6";
      sha256 = "0apf28b569qz4vik23jl0swka37qwmbxxiybfrksy7i1yaq6d38g";
    }
  ];
  plugins = with pkgs.vimPlugins; [
    vim-fugitive
    vim-dispatch
    vim-sneak
    vim-nix
    fzf-vim
    coc-nvim
  ] ++ custom;
in {
  imports = [
    ./fzf.nix
    ./fugitive.nix
    ./vifm.nix
  ];
  home-manager.users."${username}".programs.neovim.plugins = plugins;
}
