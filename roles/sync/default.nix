{ username, ... }:
{
  services.syncthing = {
    enable = true;
    user = username;
    openDefaultPorts = true;
    dataDir = "/home/${username}/Sync";
    #declarative = {
    #  folders = {
    #    "/home/${username}/Vault" = {
    #      id = "ussmr-jztfp";
    #    };
    #    "/home/${username}/Sync" = {
    #      id = "default";
    #    };
    #    "/home/${username}/wg-configs" = {
    #      id = "gs6lj-dorhv";
    #    };
    #    "/home/${username}/openvpn-configs" = {
    #      id = "jmsgr-rwdno";
    #    };
    #  };
    #};
  };
}
