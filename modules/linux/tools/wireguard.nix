{ config, options, lib, pkgs, ... }:
with lib;
with lib.my;

let cfg = config.modules.tools.wireguard;
in { 
  options.modules.tools.wireguard = {
    enable = mkBoolOpt false;
  };

  config = mkIf cfg.enable {
    networking = {
      wireguard.enable = true;
      # if packets are still dropped, they will show up in dmesg
      firewall = {
        logReversePathDrops = true;
        # wireguard trips rpfilter up
        extraCommands = ''
          ip46tables -t raw -I nixos-fw-rpfilter -p udp -m udp --sport 51820 -j RETURN
          ip46tables -t raw -I nixos-fw-rpfilter -p udp -m udp --dport 51820 -j RETURN
        '';
        extraStopCommands = ''
          ip46tables -t raw -D nixos-fw-rpfilter -p udp -m udp --sport 51820 -j RETURN || true
          ip46tables -t raw -D nixos-fw-rpfilter -p udp -m udp --dport 51820 -j RETURN || true
        '';
      };
    };
    environment.systemPackages = [
      pkgs.wireguard-tools
    ];
  };
}
