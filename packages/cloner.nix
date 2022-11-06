{ pkgs ? import <nixpkgs> { } }:
with pkgs;
let
  src = fetchFromGitHub {
    owner = "jack-michaud";
    repo = "cloner";
    rev = "main";
    sha256 = "0rckskppv9i47q1nr56jhdhf11ia0r1zl9mc3vp0biwwn5h0kcyi";
  };
in rustPlatform.buildRustPackage {
  inherit src;
  name = "cloner";
  version = "0.0.1";
  cargoHash = "sha256-dPkeDaITJlDuzdih4Ax8mk/Pv1KKsOMkT6Kf7KXuB3w=";
}
