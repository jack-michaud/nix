{
  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-20.09";
    nixpkgs-git.url = "github:NixOS/nixpkgs/master";
    home-manager = {
      url = "github:nix-community/home-manager/release-20.09";
      inputs.nixpkgs.follows = "nixpkgs";
    };
    dwm = {
      url = "github:jack-michaud/dwm";
      inputs.nixpkgs.follows = "nixpkgs";
    };
  };
  outputs = { self, nixpkgs, nixpkgs-git, dwm, home-manager }:
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
            specialArgs = {
              inherit dwm;
            };
            modules = [ 
              {
                nixpkgs.overlays = [ 
                  overlay
                  # dwm overlay
                  (self: super: {
                    dwm = super.dwm.overrideAttrs (oldAttrs: rec {
                      src = dwm.defaultPackage.${system}.src;
                      installPhase = dwm.defaultPackage.${system}.installPhase;
                      buildInputs = dwm.defaultPackage.${system}.buildInputs;
                    });
                  })
                ];
                nixpkgs.config.allowUnfree = true;
                nix.registry.nixpkgs.flake = nixpkgs;
              }
              home-manager.nixosModules.home-manager 
              { home-manager.useGlobalPkgs = true; }
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
