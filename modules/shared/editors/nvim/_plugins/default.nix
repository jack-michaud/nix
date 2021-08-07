{ pkgs, ... }:
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
      rev = "408476478f899ec56db26da40eae4735712d6ac5";
      sha256 = "1nqnfbq22650xfdg3q2hf4app8jf5p4922clrnyckls2rvpafgrr";
    }
  ];
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
  ] ++ custom;
in 
  { inherit plugins; }
