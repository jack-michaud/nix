{ pkgs, ...  }:
with pkgs;
rec {
  # All of these scripts are added to systemPackages!
  nixos-rebuild-switch = writeShellScriptBin "nixos-rebuild-switch" ''
    # I want this to work, but no clue how.
    # https://discourse.nixos.org/t/how-to-do-a-flake-build-in-non-nixos-system/10450/7
    # https://discourse.nixos.org/t/build-nixos-config-without-environment-dependencies-and-have-nixos-option-nixos-rebuild-support/6940/3
  '';

  rofi-ask-pass = writeShellScriptBin "rofi-ask-pass" ''
    ${rofi}/bin/rofi -dmenu \
    	-password \
    	-no-fixed-num-lines \
    	-p "$(printf "$1" | sed s/://)"
  '';

  snip = writeShellScriptBin "snip" ''
    file=$(mktemp /tmp/screen.XXXX.png)
    ${maim}/bin/maim -s $file $@ && \
      ${xclip}/bin/xclip -sel clip -t image/png -i $file && \
      ${libnotify}/bin/notify-send -i $file "screenshot taken" &&
      rm $file
  '';

  pick = writeShellScriptBin "pick" ''
    color=$(${colorpicker}/bin/colorpicker --short --one-shot)
    echo $color | ${xclip}/bin/xclip -sel clipboard
    ${imagemagick}/bin/convert -size 50x50 xc:$color /tmp/color.png
    ${libnotify}/bin/notify-send -i /tmp/color.png \
      "Picked color $color"
  '';

  use-vpn = callPackage ./use-vpn.nix {
    inherit rofi-ask-pass;
  };
}
