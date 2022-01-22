{ pkgs, ... }:
let
  customPlugin = { repo, owner, rev, sha256 }:
  pkgs.unstable.vimUtils.buildVimPlugin {
    pname = repo;
    version = "N";
    src = pkgs.fetchFromGitHub {
      inherit owner repo rev sha256;
    };
    nativeBuildInputs = [ pkgs.neovim-unwrapped ];
    HOME = "/tmp/";
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
    {
      owner = "nvim-telescope";
      repo = "telescope-file-browser.nvim";
      rev = "e65a5674986dcaf27c0fd852b73f5fc66fa78181";
      sha256 = "0h76cc7mn7wmdhqk5bdgkaz3abvk15687mqkkp049xsqyjkfjzb2";
    }
    {
      owner = "nvim-telescope";
      repo = "telescope-github.nvim";
      rev = "36df6b281eb3cb47494933a3dc44c874086fa688";
      sha256 = "1lra7c38m3amqgdlb4gnl3rnvszwzn0yv624v2h4lhax8nzzq85j";
    }
  ];
  plugins = with pkgs.unstable.vimPlugins; [
    vim-fugitive
    vim-rhubarb
    vim-dispatch
    vim-sneak
    nvim-treesitter
    # Telescope
    telescope-nvim
    telescope-fzf-native-nvim
    # Coc
    coc-nvim
    coc-snippets
    coc-rust-analyzer
    # Theme
    vim-monokai-pro
    rust-vim
  ] ++ custom;
in 
  { inherit plugins; }
