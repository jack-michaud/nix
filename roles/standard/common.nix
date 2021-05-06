{ lib, config, pkgs, options, username, ... }:
{
  imports = [
    ./cachix
    ./neovim
    ./alacritty.nix
    ./git.nix
    ./fish.nix
  ];

  users.users.${username} = {};

  # List packages installed in system profile. To search, run:
  # $ nix search wget
  environment.systemPackages = with pkgs; [
    wget vim
    node
    ripgrep
    git
    ranger
    z-lua
  ];

  nix = {
    package = pkgs.nixFlakes;
    extraOptions = lib.optionalString (config.nix.package == pkgs.nixFlakes)
    "experimental-features = nix-command flakes";
  };
}


