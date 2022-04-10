{ pkgs, lib, stdenv }:
pkgs.buildGoModule rec {
  name = "caddy-route53-dns";
  version = "0.0.1";
  vendorSha256 = "sha256-ogaPLMFxmOhTsvv+dOWDGGOKjsGhboatC7yw6YOsltE=";

  buildInputs = [
    pkgs.go
  ];

  # pointing to this directory because src is needed
  src = ./.;
  buildPhase = ''
    ${pkgs.go}/bin/go build -o caddy
  '';

  installPhase = ''
    mkdir -p $out/bin
    mv caddy $out/bin
  '';
}
