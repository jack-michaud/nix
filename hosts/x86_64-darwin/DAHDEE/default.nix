{ config, pkgs, ... }:
{
  imports = [
    ../../roles/standard/darwin.nix
  ];
  system.stateVersion = 4;
}
