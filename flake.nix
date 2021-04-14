{
  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-20.09";
    nixpkgs-git.url = "github:NixOS/nixpkgs/master";
  };
  outputs = { self, nixpkgs, nixpkgs-git }:
    let 
      mkOverlay = system: import ./overlays {
        inherit system;
        nixpkgs = import nixpkgs-git {
          config = { allowUnfree = true; };
        };
      };
    in rec {
      nixosConfigurations = let
        system-config = name: system:
        let
          overlay = mkOverlay system;
        in {
          "${name}" = nixpkgs.lib.makeOverridable nixpkgs.lib.nixosSystem {
            inherit system;
            modules = [ 
              {
                nixpkgs.overlays = [ overlay ];
                nixpkgs.config.allowUnfree = true;
                nix.registry.nixpkgs.flake = nixpkgs;
              }
              (import (./hosts + "/${name}/default.nix"))
              (import (./hosts + "/${name}/hardware-configuration.nix"))
            ];
          };
        };
      in {}
      // (system-config "ajax" "x86_64-linux")
      ;
    };
}
