{
  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    nixpkgs-git.url = "github:NixOS/nixpkgs/master";
    nixpkgs-darwin.url = "github:NixOS/nixpkgs/nixpkgs-20.09-darwin";
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
      mkUtilScripts = system: import ./utilScripts.nix {
        pkgs = import nixpkgs-git {
          inherit system;
          config = { allowUnfree = true; };
        };
      };
    in rec {
      nixosConfigurations = let
        system-config = hostname: username: system:
        let
          myoverlay = mkOverlay system;
          utilScripts = mkUtilScripts system;
        in {
          "${hostname}" = nixpkgs.lib.makeOverridable nixpkgs.lib.nixosSystem {
            inherit system;
            specialArgs = rec {
              inherit hostname username utilScripts;
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
              (import (./hosts + "/${hostname}/default.nix"))
              (import (./hosts + "/${hostname}/hardware-configuration.nix"))
            ];
          };
        };
      in {}
      // (system-config "ajax" "jack" "x86_64-linux")
      ;

      darwinConfigurations = let 
        darwin-system-config = hostname: username: system: 
        let
          myoverlay = mkOverlay system;
        in {
          "${hostname}" = darwin.lib.darwinSystem {
            # inherit system;
            specialArgs = {
              inherit hostname username;
            };
            modules = [
              {
                nixpkgs.overlays = [ myoverlay ];
                nixpkgs.config.allowUnfree = true;
                nix.registry.nixpkgs.flake = nixpkgs-darwin;
              }
              home-manager.darwinModules.home-manager 
              { 
                home-manager.useGlobalPkgs = true;
              }
              (import (./hosts + "/${hostname}/configuration.nix"))
            ];
          };
        };
      in {}
      // darwin-system-config "DAHDEE" "Jack" "x86_64-darwin"
      // darwin-system-config "Jack-Michaud" "jack" "aarch64-darwin"
      ;
    };
}
