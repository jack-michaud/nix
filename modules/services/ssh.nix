{ options, config, lib, ... }:
with lib;
with lib.my;
let cfg = config.modules.services.ssh;
in {
  options.modules.services.ssh = {
    enable = mkBoolOpt false;
  };

  config = mkIf cfg.enable {
    services.openssh = {
      enable = true;
      forwardX11 = true;
      permitRootLogin = lib.mkForce "no";
      passwordAuthentication = false;
    };

    user = {
      openssh.authorizedKeys.keys = [
        "ecdsa-sha2-nistp521 AAAAE2VjZHNhLXNoYTItbmlzdHA1MjEAAAAIbmlzdHA1MjEAAACFBAHXhwJc/cmSfds8ZZmFPVZC7j7mEV8fqnU+IKqAo5fqEDZSOZ2Th949rn3B3+iaZ3yxNog2151Yp8h5ivez3PmFOAGon3qjC9gcWcmxzjcytkZHdJaxOmpHmiuJj44UFq87tETmj+V8+hbyTGvtqTuB5aPhYmVCfApOnQSfbBY1uAnRgA== jack@CASTOR"
        ];
    };
    networking = {
      firewall = {
        enable = true;
        allowedTCPPorts = [ 22 ];
      };
    };
  };
}
