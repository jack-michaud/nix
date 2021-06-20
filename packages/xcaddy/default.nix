{ pkgs, lib }:

let
  info = builtins.fromJSON (builtins.readFile ./package-info.json);
in
  pkgs.buildGoModule rec {
    pname = "xcaddy";
    version = info.version;
    vendorSha256 = info.vendorSha256;

    src = pkgs.fetchFromGitHub {
      owner = "caddyserver";
      repo = "xcaddy";
      rev = "v${version}";
      sha256 = info.sha256;
    };
    subPackages = [ "cmd/xcaddy" ];

    meta = with lib; {
      description = "A command line tool to make it easy to make custom builds of the Caddy Web Server";
      homepage = "https://github.com/caddyserver/xcaddy";
      license = licenses.asl20;
    };
  }
