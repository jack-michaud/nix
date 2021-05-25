{ config, pkgs, ... }:
{
  imports = [
    ../../roles/standard/darwin.nix
    (import ../../roles/homebrew/default.nix { work = true; dev = true; personal = false; })
  ];
  system.stateVersion = 4;
  services.nix-daemon.enable = false;
}

