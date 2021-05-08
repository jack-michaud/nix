{ username, ... }:
{
  services.syncthing = {
    enable = true;
    user = username;
    openDefaultPorts = true;
    dataDir = "/home/${username}/Sync";
  };
}
