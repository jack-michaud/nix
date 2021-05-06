{ lib, config, pkgs, options, username, ... }:
{
  imports = [
    ./cachix
    ./neovim
    ./alacritty.nix
    ./git.nix
    ./fish.nix
  ];

  users.users.${username} = {
    shell = pkgs.fish;
  };

  # List packages installed in system profile. To search, run:
  # $ nix search wget
  environment.systemPackages = with pkgs; [
    wget vim
    nodejs
    ripgrep
    git
    ranger
    z-lua
    fish
  ];

  nix = {
    package = pkgs.nixFlakes;
    extraOptions = lib.optionalString (config.nix.package == pkgs.nixFlakes)
    "experimental-features = nix-command flakes";
  };
}

