{ pkgs, ... }:
let
  customPlugin = { repo, owner, rev, sha256 }:
  pkgs.unstable.vimUtils.buildVimPlugin {
    pname = repo;
    version = "N";
    src = pkgs.fetchFromGitHub {
      inherit owner repo rev sha256;
    };
  };
  custom = map customPlugin [
    {
      owner = "vifm";
      repo = "vifm.vim";
      rev = "408476478f899ec56db26da40eae4735712d6ac5";
      sha256 = "1nqnfbq22650xfdg3q2hf4app8jf5p4922clrnyckls2rvpafgrr";
    }
    {
      owner = "psf";
      repo = "black";
      rev = "77d11bb4b4911c91ea97dd43047cf6021d173c65";
      sha256 = "0irgqk5rkd8yb5y1sb88w9y05kyz0s7vxvn461mc9a8a6nidbyzw";
    }
  ];
  plugins = with pkgs.unstable.vimPlugins; [
    vim-fugitive
    vim-rhubarb
    vim-dispatch
    vim-sneak
    fzf-vim
    coc-nvim
    coc-snippets
    coc-rust-analyzer
    # languages
    vim-terraform
    vim-nix
    vim-fish
    vim-monokai-pro
    rust-vim
  ] ++ custom;
in 
  { inherit plugins; }
