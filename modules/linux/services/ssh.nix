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
      passwordAuthentication = false;
    };

    user = {
      openssh.authorizedKeys.keys = [
        "ecdsa-sha2-nistp521 AAAAE2VjZHNhLXNoYTItbmlzdHA1MjEAAAAIbmlzdHA1MjEAAACFBAHXhwJc/cmSfds8ZZmFPVZC7j7mEV8fqnU+IKqAo5fqEDZSOZ2Th949rn3B3+iaZ3yxNog2151Yp8h5ivez3PmFOAGon3qjC9gcWcmxzjcytkZHdJaxOmpHmiuJj44UFq87tETmj+V8+hbyTGvtqTuB5aPhYmVCfApOnQSfbBY1uAnRgA== jack@CASTOR"
        "ecdsa-sha2-nistp521 AAAAE2VjZHNhLXNoYTItbmlzdHA1MjEAAAAIbmlzdHA1MjEAAACFBADtu5UDZalYPNDPW2cJVu/6T+DbwYDKNT9eCsvEuy8Lh4HC9UOywhXvEc/2qs5oPdqw2S3SmxZkq6DhB6PI5Q10GQGv7+Czntrtlas9qvAKxH9Uu8UcXeshFhvmng8JU9n+4KLysGNo6gA6W/Cjp8z45nJFJs2xgjF9qgwiuQV+ZD/W1w== jack@ajax"
      ];
    };
    users.users.root = {
      openssh.authorizedKeys.keys = [
        "ecdsa-sha2-nistp521 AAAAE2VjZHNhLXNoYTItbmlzdHA1MjEAAAAIbmlzdHA1MjEAAACFBADtu5UDZalYPNDPW2cJVu/6T+DbwYDKNT9eCsvEuy8Lh4HC9UOywhXvEc/2qs5oPdqw2S3SmxZkq6DhB6PI5Q10GQGv7+Czntrtlas9qvAKxH9Uu8UcXeshFhvmng8JU9n+4KLysGNo6gA6W/Cjp8z45nJFJs2xgjF9qgwiuQV+ZD/W1w== jack@ajax"
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
