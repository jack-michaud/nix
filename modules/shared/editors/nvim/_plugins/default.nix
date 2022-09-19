{ pkgs, ... }:
let
  customPlugin = inputs@{ fetcher ? pkgs.fetchFromGitHub, ... }:
    pkgs.unstable.vimUtils.buildVimPlugin {
      pname = inputs.repo;
      version = "N";
      src = fetcher inputs;
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
    #{
    #  fetcher = inputs@{ url, sha256, ... }:
    #    pkgs.fetchzip { inherit url sha256; };
    #  repo = "copilot.vim";
    #  url =
    #    "https://git.internal.lomz.me/jack/copilot.vim/archive/47c5cc4f8f0d5be2b2d572950ebe4110e18451b5.tar.gz";
    #  sha256 = "0ni232b8m4da5hcarpk0w1qskaywqlyxiib88qk4mgq8lclx11zx";
    #}
    {
      owner = "zbirenbaum";
      repo = "copilot-cmp";
      rev = "a549a24eab37d6803555f40f292280ba01e686de";
      sha256 = "0a558q0rimhajlaq16ll8kc18h42k536jjh7sslzm4f2hmijaks8";
    }
    {
      owner = "zbirenbaum";
      repo = "copilot.lua";
      rev = "3d3f6a312e49c8333681c8163dc32f88b120ede5";
      sha256 = "1g885k9mnjb8yvypbvc18vhjhr74hrmy7i1jm2z4g691c88gxhvs";
    }
  ];
  plugins = with pkgs.unstable.vimPlugins;
    [
      vim-fugitive
      vim-rhubarb
      vim-dispatch
      vim-sneak
      # neovim packages
      null-ls-nvim
      nvim-treesitter
      feline-nvim
      plenary-nvim
      gitsigns-nvim
      # Telescope
      telescope-nvim
      telescope-fzf-native-nvim
      # Coc
      packer-nvim
      nvim-lspconfig
      cmp-nvim-lsp
      cmp-buffer
      cmp-path
      cmp-cmdline
      nvim-cmp
      copilot-vim
      # Theme
      vim-monokai-pro
      rust-vim
    ] ++ custom;
in { inherit plugins; }
