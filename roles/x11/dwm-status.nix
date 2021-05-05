{ pkgs, ... }:
with pkgs;
let
  dwmStatus = pkgs.writeShellScriptBin "dwmStatus" ''
    normal="\x01"
    red="\x05"
    yellow="\x06"
    green="\x07"
    blue="\x0A"
    
    
    getBattery() {
        perc=$(${acpi}/bin/acpi -b | awk '/Battery/ {print $4}' | cut -d% -f1)
        time=$(${acpi}/bin/acpi -b | awk '/Battery/ {print " (" substr($5,1,5)")"}')
        is_charging=$(${acpi}/bin/acpi -a | awk '/Adapter/ {print $3}')
    
        #echo -ne "BAT: $perc $is_charging"
    
        if [ "$is_charging" != "on-line" ]; then
            if [ $perc -eq "100" ]; then
                echo -ne ""
            elif [ $perc -le "25" ]; then
                echo -ne "$normal $red$perc% $time"
            elif [ $perc -le "50" ]; then
                echo -ne "$normal $yellow$perc%"
            elif [ $perc -le "76" ]; then
                echo -ne "$normal $yellow$perc%"
            elif [ $perc -le "100" ]; then
                echo -ne " $green$perc%"
            fi
        else
          echo -ne ""
        fi
    }
    
    getCPU() {
        cpu=$(${sysstat}/bin/mpstat -P ALL 1 1 | awk '/Average:/ && $2 ~ /all/ {print $3}' | awk -F '.' '{ print $1 }')
        cpu=$(printf "%3s" $cpu)
        echo -ne " $cpu%"
    }
    
    getMEM() {
        total=$(free -m | awk '/Mem:/ {print $2}')
        mem="$(${bc}/bin/bc <<< $total-$(free -m | awk '/Mem:/ {print $7}'))"
    
        mem=$(${bc}/bin/bc <<< $mem*100/$total)
        mem=$(printf "%3s" $mem)
        echo -ne  $mem%
     }
    
    #getMusic() {
    #    music_str=`python /home/jack/Programs/polybar-spotify/spotify_status.py -f '{artist} - {song}'`
    #    if [[ ! -z $music_str ]]; then
    #      echo -ne " $music_str "
    #    fi
    #}
    
    getTime() {
        tme="$(date '+%A %D %H:%M')"
        echo -ne "$tme"
    }
    
    while true; do
        # getUpdates &
        xsetroot -name "   $(getMusic)  $(getBattery)  $(getCPU)  $(getMEM)  $(getTime)  "
        sleep 1
    done
  '';
in 
  dwmStatus

