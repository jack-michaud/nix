{ pkgs ? import <nixpkgs> {} }:
with pkgs;
let
  src = fetchFromGitHub {
    owner = "jack-michaud";
    repo = "cloner";
    rev = "main";
    sha256 = "0693zz824c3drgxpxw6zxqrgdkqnapa1qhql1dj5sd47wkwnqxr6";
  };
in 
  rustPlatform.buildRustPackage {
    inherit src;
    name = "cloner";
    version = "0.0.1";
    cargoHash = "sha256-dPkeDaITJlDuzdih4Ax8mk/Pv1KKsOMkT6Kf7KXuB3w=";
  }
