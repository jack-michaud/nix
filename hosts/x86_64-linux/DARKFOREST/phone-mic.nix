# iPhone mic -> DARKFOREST.
#
# SonoBus (GPLv3, iOS + Linux) streams the phone's mic over the LAN; a
# pw-loopback pair turns that into a "Phone Mic" PipeWire source any app can
# pick as an input. Point SonoBus's output at the "Phone Mic (sink)" sink
# (pavucontrol remembers it) and the audio comes out of the source.
{ pkgs, ... }:

let
  # SonoBus is a JUCE app: ALSA or JACK only, no native PipeWire backend. Nix's
  # alsa-lib does read Arch's /etc/alsa/conf.d/50-pipewire.conf, but the plugin
  # .so it names has to come from the nix side — same ALSA_PLUGIN_DIR trick
  # nixpkgs' own alsa-utils uses.
  alsaPluginDir = pkgs.symlinkJoin {
    name = "alsa-plugins-with-pipewire";
    paths = [ pkgs.alsa-plugins pkgs.pipewire ];
  };

  sonobus = pkgs.symlinkJoin {
    name = "sonobus-pipewire-${pkgs.sonobus.version}";
    paths = [ pkgs.sonobus ];
    nativeBuildInputs = [ pkgs.makeWrapper ];
    postBuild = ''
      wrapProgram $out/bin/sonobus \
        --set-default ALSA_PLUGIN_DIR ${alsaPluginDir}/lib/alsa-lib
    '';
  };

  # A script rather than an inline ExecStart: the props are SPA JSON and need
  # their double quotes intact, which systemd's own quoting would eat.
  phoneMicLoopback = pkgs.writeShellScript "phone-mic-loopback" ''
    exec ${pkgs.pipewire}/bin/pw-loopback \
      -m '[ FL, FR ]' \
      --capture-props='media.class=Audio/Sink node.name=phone_mic_sink node.description="Phone Mic (sink)"' \
      --playback-props='media.class=Audio/Source node.name=phone_mic node.description="Phone Mic"'
  '';
in
{
  home.packages = [ sonobus ];

  systemd.user.services.phone-mic-loopback = {
    Unit = {
      Description = "Phone Mic virtual PipeWire source (fed by SonoBus)";
      # The nodes live inside the daemon, so they go away with it.
      After = [ "pipewire.service" ];
      BindsTo = [ "pipewire.service" ];
    };
    Service = {
      ExecStart = "${phoneMicLoopback}";
      Restart = "on-failure";
      RestartSec = 2;
    };
    Install.WantedBy = [ "pipewire.service" ];
  };
}
