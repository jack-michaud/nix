{
  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    nixpkgs-git.url = "github:NixOS/nixpkgs/master";
    home-manager = {
      url = "github:nix-community/home-manager";
      inputs.nixpkgs.follows = "nixpkgs";
    };
    dwm = {
      url = "github:jack-michaud/dwm";
      inputs.nixpkgs.follows = "nixpkgs";
    };

    # nix-darwin input
    darwin.url = "github:lnl7/nix-darwin/master";
    darwin.inputs.nixpkgs.follows = "nixpkgs";
  };
  outputs = inputs@{ self, nixpkgs, nixpkgs-git, dwm, home-manager, darwin }:
    let 
      mkOverlay = system: import ./overlays {
        inherit system dwm;
        nixpkgs = import nixpkgs-git {
          inherit system;
          config = { allowUnfree = true; };
        };
      };
    in rec {
      nixosConfigurations = let
        system-config = name: system:
        let
          myoverlay = mkOverlay system;
        in {
          "${name}" = nixpkgs.lib.makeOverridable nixpkgs.lib.nixosSystem {
            inherit system;
            specialArgs = {
              username = "jack";
            };
            modules = [ 
              {
                nixpkgs.overlays = [ myoverlay ];
                nixpkgs.config.allowUnfree = true;
                nix.registry.nixpkgs.flake = nixpkgs;
              }
              home-manager.nixosModules.home-manager 
              { 
                home-manager.useGlobalPkgs = true;
              }
              (import (./hosts + "/${name}/default.nix"))
              (import (./hosts + "/${name}/hardware-configuration.nix"))
            ];
          };
        };
      in {}
      // (system-config "ajax" "x86_64-linux")
      ;

      darwinConfigurations = let 
        darwin-system-config = name: username: system: 
        {
          "${name}" = darwin.lib.darwinSystem {
            specialArgs = {
              inherit username;
            };
            modules = [
              home-manager.darwinModules.home-manager 
              { 
                home-manager.useGlobalPkgs = true;
              }
              (import (./hosts + "/${name}/configuration.nix"))
            ];
          };
        };
      in {}
      // darwin-system-config "DAHDEE" "Jack" "x86_64-darwin"
      // darwin-system-config "Jack-Michaud" "jack" "aarch64-darwin"
      ;
    };
}
