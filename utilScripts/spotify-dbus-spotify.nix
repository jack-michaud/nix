{ pkgs, ... }:
with pkgs;
let
  pythonPackages = python-packages: with python-packages; [
    setuptools
    dbus-python
    six
  ];
  pythonEnv = python3.withPackages pythonPackages;
  src = fetchFromGitHub {
    owner = "Jackevansevo";
    repo = "spotify-dbus-status";
    rev = "master";
    sha256 = "7ROTbU8pKo9gmaSpIODV8gWHpQoMaISlmKvavVJlimY=";
  };
in 
  writeShellScriptBin "spotify-dbus-status" ''
    ${pythonEnv}/bin/python ${src}/spotify_dbus_status.py $@
  ''
