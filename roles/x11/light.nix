{ pkgs, ... }:
{
  programs.light.enable = true;
  users.users.jack.extraGroups = [ "video" ];
}
