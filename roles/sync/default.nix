{ username, ... }:
{
  services.syncthing = {
    # Research https://docs.syncthing.net/users/stdiscosrv.html
    # before turning on
    #enable = true;
    enable = false;
    user = username;
    openDefaultPorts = true;
    dataDir = "/home/${username}/Sync";
  };
}
