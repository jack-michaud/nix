{ pkgs ? import <nixpkgs> {} }:
with pkgs;
let
  src = fetchFromGitHub {
    owner = "jack-michaud";
    repo = "cloner";
    rev = "main";
    sha256 = "1cwwivdj2bahdcxmzczlk80hq6mmwz1r4260y2k1vkgjpf2qydvx";
  };
in 
  rustPlatform.buildRustPackage {
    inherit src;
    name = "cloner";
    version = "0.0.1";
    cargoHash = "sha256-dPkeDaITJlDuzdih4Ax8mk/Pv1KKsOMkT6Kf7KXuB3w=";
  }
