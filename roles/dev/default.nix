{ pkgs, username, ... }:
{
  environment.systemPackages = with pkgs; [
    docker-compose
  ];
  users.users.${username} = {
    extraGroups = [ "docker" ];
  };
}
