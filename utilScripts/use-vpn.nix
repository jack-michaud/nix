{ pkgs, rofi-ask-pass, ... }:
with pkgs;
writeShellScriptBin "use-vpn" ''
  openvpn_pid_file=~/.cache/.openvpn.pid
  wireguard_config_file=~/.cache/.wireguardconfig
  export SUDO_ASKPASS=${rofi-ask-pass}/bin/rofi-ask-pass
  
  function killoldopenvpn {
    if [ -f $openvpn_pid_file ]; then
      sudo -A kill $(cat $openvpn_pid_file)
      ${libnotify}/bin/notify-send "killing openvpn..."
      sleep 0.25
      rm $openvpn_pid_file
    fi
  }

  
  function killoldwireguard {
    # wireguard config
    if [ -f $wireguard_config_file ]; then
      oldconfig=$(cat $wireguard_config_file)
      sudo -A ${wireguard-tools}/bin/wg-quick down $oldconfig
      ${libnotify}/bin/notify-send "wg-quick down $oldconfig..."
      sleep 0.25
      rm $wireguard_config_file
    fi
  }
  
  function selectopenvpn {
    if [ -z $OPENVPN_CONFIGS_PATH ]; then
      OPENVPN_CONFIGS_PATH=~/openvpn-configs
    fi
  
    basename=$(ls $OPENVPN_CONFIGS_PATH | ${rofi}/bin/rofi -dmenu -p "Which config?")
    fullpath=$OPENVPN_CONFIGS_PATH/$basename
  
    if [[ -z $basename ]]; then
      exit 1
    fi
  
    sudo -A ${openvpn}/bin/openvpn $fullpath &
    pid=$!
  
    sleep 1
    if ps -p $pid > /dev/null ; then 
      ${libnotify}/bin/notify-send "Activated vpn for $basename (pid: $pid)"
      echo $pid > $openvpn_pid_file
    else
      ${libnotify}/bin/notify-send "Failed :("
    fi
  }
  
  function selectwireguard {
    if [ -z $WIREGUARD_CONFIGS_PATH ]; then
      WIREGUARD_CONFIGS_PATH=~/wg-configs/keys/
    fi
  
    basename=$(ls $WIREGUARD_CONFIGS_PATH | rofi -dmenu -p "Which config?")
    fullpath=$WIREGUARD_CONFIGS_PATH/$basename
  
    if [[ -z $basename ]]; then
      exit 1
    fi
  
    (sudo -A wg-quick up $fullpath && \
      ${libnotify}/bin/notify-send "Activated vpn for $basename (config: $fullpath)" \
      && echo $fullpath > $wireguard_config_file) ||
      ${libnotify}/bin/notify-send "failed :("
      
  }
  
  
  killoldopenvpn
  killoldwireguard
  
  vpntype=$(echo -e "wireguard\nopenvpn\n" | rofi -dmenu -p "Which type of VPN?")
  
  case $vpntype in
    wireguard)
      selectwireguard
      ;;
    openvpn)
      selectopenvpn
      ;;
    "*")
      exit 1
      ;;
  esac

''
