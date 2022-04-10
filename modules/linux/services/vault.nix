{ config, options, lib, pkgs, ... }:

with lib;
with lib.my;
let cfg = config.modules.services.vault;
in {
  # Consul backed vault.
  options.modules.services.vault = {
    enable = mkBoolOpt false;
    address = mkOption {
      type = types.str;
      default = "localhost:8200";
      description = "ip:port to put Vault on";
    };
    consulAddress = mkOption {
      type = types.str;
      default = "localhost:8500";
      description = "Address to access consul for vault storage";
    };
  };

  config = mkIf cfg.enable {
    services.vault = {
      enable = true;

      package = pkgs.vault-bin;
      storageBackend = "consul";
      storageConfig = ''
        path = "vault"
        address = "${cfg.consulAddress}"
      '';
      address = cfg.address;

      extraConfig = ''
        ui = true
      '';
    };
  };
}

