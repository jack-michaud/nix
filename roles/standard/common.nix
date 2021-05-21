{ lib, config, pkgs, options, username, hostname, utilScripts, ... }:
let
  common_packages = with pkgs; [
    wget vim
    nodejs
    ripgrep
    git
    ranger
    z-lua
    fish
    github-cli
    fzf
    wireguard-tools
  ];
in {
  imports = [
    ./cachix
    ./neovim
    ./alacritty.nix
    ./git.nix
    ./fish.nix
  ];

  users.users.${username} = {
    shell = pkgs.fish;
    packages = common_packages;
  };


  # List packages installed in system profile. To search, run:
  # $ nix search wget
  # environment.systemPackages = common_packages;

  nix = {
    package = pkgs.nixFlakes;
    extraOptions = lib.optionalString (config.nix.package == pkgs.nixFlakes)
    "experimental-features = nix-command flakes";
  };
}
