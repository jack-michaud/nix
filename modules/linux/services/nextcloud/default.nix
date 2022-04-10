{ config, options, lib, pkgs, ... }:

with lib;
with lib.my;
let cfg = config.modules.services.nextcloud;
in {
  options.modules.services.nextcloud = {
    enable = mkBoolOpt false;

    port = mkOption {
      default = 8081;
      type = types.int;
      description = ''
        Port that nextcloud is hosted on.
      '';
    };

    host = mkOption {
      default = "localhost:${toString cfg.port}";
      type = types.string;
      description = ''
        http host header 
      '';
    };
  };

  config = mkIf cfg.enable {
    users.groups.nextcloud = {};
    users.users.nextcloud = {
      isSystemUser = true;
      extraGroups = ["secrets" "docker"];
    };
    systemd.services.nextcloud = let 
      arionCompose = pkgs.arion.build { modules = [ (import ./_arion-compose.nix { port = cfg.port; host = cfg.host; }) ]; inherit pkgs; };
      composeWrapper = pkgs.writeShellScriptBin "composeWrapper" ''
          ${pkgs.docker-compose}/bin/docker-compose -f ${arionCompose} $@
        '';
      in {
        wantedBy = [ "multi-user.target" ];
        after = [ "network.target" ];
        description = "Nextcloud docker fleet";
        serviceConfig = {
          Type = "simple";
          WorkingDirectory = "/var/lib/nextcloud/";
          StateDirectory = "nextcloud";
          StateDirectoryMode = "750";
          User = "nextcloud";
          Group = "nextcloud";
          ExecStart = "${composeWrapper}/bin/composeWrapper up";
          ExecStop = "${composeWrapper}/bin/composeWrapper down";
        };
      };
    vault-secrets = {
      secrets = {
        nextcloud = {
          namespace = "services";
          environmentKey = "production";
          environmentFile = "/root/vault-secrets.sh";
          group = "nextcloud";
          user = "nextcloud";
        };
      };
    };
  };
}

