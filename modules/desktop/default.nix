{ options, config, lib, pkgs, ... }:

with lib;
with lib.my;
{
  config = mkIf config.services.xserver.enable {
    # Configure keymap in X11
    services.xserver.layout = "us";
    services.xserver.displayManager.lightdm.enable = true;
    fonts.fonts = [
      pkgs.font-awesome_5
    ];
    environment.systemPackages = with pkgs; [
      xclip
      xbrightness
      feh
      mesa_drivers
    ];

    services.xserver.displayManager.sessionCommands = ''
      ${pkgs.xorg.xrdb}/bin/xrdb -merge <${pkgs.writeText "Xresources" ''
        rofi.eh: 2
        rofi.bw: 0
        rofi.lines: 5
        rofi.padding: 100
        rofi.fullscreen: false
        rofi.font: Iosevka 12
        rofi.color-window: argb:cc2f343f, argb:cc2f343f, argb:cc2f343f
        rofi.color-normal: argb:031d1f21, #f3f4f5, argb:031d1f21, argb:031d1f21, #9575cd 
        rofi.color-urgent: argb:031d1f21, #f3f4f5, argb:bc303541, argb:031d1f21, #9575cd
        rofi.color-active: argb:031d1f21, #f3f4f5, argb:031d1f21, argb:031d1f21, #9575cd 
        rofi.color-enabled: true
        
        ! special
        *.foreground:   #f1ebeb
        *.background:   #150F13
        *.cursorColor:  #f1ebeb
        
        ! black
        *.color0:       #1F2430
        *.color8:       #151821
        !*.color0:       #48483e
        !*.color8:       #76715e
        
        ! red
        *.color1:       #dc2566
        *.color9:       #fa2772
        
        ! green
        *.color2:       #8fc029
        *.color10:      #a7e22e
        
        ! yellow
        *.color3:       #d4c96e
        *.color11:      #e7db75
        
        ! blue
        *.color4:       #55bcce
        *.color12:      #66d9ee
        
        ! magenta
        *.color5:       #9358fe
        *.color13:      #ae82ff
        
        ! cyan
        *.color6:       #56b7a5
        *.color14:      #66efd5
        
        ! white
        *.color7:       #acada1
        *.color15:      #cfd0c2

      ''}
    '';
  };
}
