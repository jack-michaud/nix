{ system, dwm }:
final: prev:
let
  inherit (prev) callPackage;
in {
  dwm = prev.dwm.overrideAttrs (oldAttrs: rec {
    src = dwm.defaultPackage.${system}.src;
    installPhase = dwm.defaultPackage.${system}.installPhase;
    buildInputs = dwm.defaultPackage.${system}.buildInputs;
  });
}
