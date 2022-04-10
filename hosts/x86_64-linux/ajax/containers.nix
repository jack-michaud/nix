{ config, ... }:
{
  #containers.nginxtest = {
  #  ephemeral = true;
  #  autoStart = true;
  #  config = { pkgs, ... }: {
  #    services.nginx = {
  #      enable = true;
  #      virtualHosts."localhost" = {
  #        default = true;
  #        extraConfig = ''
  #          set_real_ip_from 0.0.0.0/0;
  #          set_real_ip_from ::0/0;
  #          real_ip_header X-Forwarded-For;
  #        '';
  #      };
  #    };
  #    networking.firewall.allowedTCPPorts = [ 80 ];
  #  };
  #};
}
