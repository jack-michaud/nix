{ lib, config, pkgs, options, ... }:
{ 
  imports = [
    ./common.nix
    ../homebrew
  ];

  environment.shells = [ pkgs.zsh "/Users/jack/.nix-profile/bin/fish" ];
}
