{ lib, config, pkgs, options, ... }:
{
  imports = [
    ./cachix
    ./neovim
    ./alacritty.nix
    ./git.nix
    ./fish.nix
  ];

  environment.sessionVariables.EDITOR = "nvim";

  # List packages installed in system profile. To search, run:
  # $ nix search wget
  environment.systemPackages = with pkgs; [
    wget vim
    ripgrep
    firefox
    discord
    git
    ranger
    vifm
    z-lua

    obsidian
  ];
}


