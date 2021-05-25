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
    #emacs = {
    #  url = "github:jack-michaud/doom.d";
    #};

    # nix-darwin input
    darwin.url = "github:lnl7/nix-darwin/master";
    darwin.inputs.nixpkgs.follows = "nixpkgs";
  };
  outputs = inputs@{ self, nixpkgs, nixpkgs-git, dwm, home-manager, darwin }:
    let 
      inherit (lib.my) mapModules mapModulesRec mapHosts;
      lib = nixpkgs.lib.extend (self: super: {
        # helpful library extensions.
        my = import ./lib {
          inherit pkgs inputs darwin;
          lib = self; 
        }; 
      });

      mkPkgs = system: pkgs: extraOverlays: import pkgs {
        inherit system;
        config.allowUnfree = true;
        overlays = extraOverlays;
      };
      pkgs  = system: mkPkgs system nixpkgs [ (self.mkOverlay system) ];
      pkgs' = system: mkPkgs system nixpkgs-git [];

      #mkOverlay = system: import ./overlays {
      #  inherit system dwm;
      #  nixpkgs = import nixpkgs-git {
      #    inherit system;
      #    config = { allowUnfree = true; };
      #  };
      #};
      #mkUtilScripts = system: import ./utilScripts {
      #  pkgs = import nixpkgs-git {
      #    inherit system;
      #    config = { allowUnfree = true; };
      #  };
      #};
    in rec {
      lib = lib.my;
      mkOverlay = 
        system: final: prev: {
          unstable = pkgs' system;
        };

      nixosConfigurations = 
        mapHosts ./hosts/x86_64-linux "x86_64-linux" {};

      darwinConfigurations = 
        mapHosts ./hosts/x86_64-darwin "x86_64-darwin" {} // mapHosts ./hosts/aarch64-darwin "aarch64-darwin" {};


      #nixosConfigurations = let
      #  system-config = hostname: username: system:
      #  let
      #    myoverlay = mkOverlay system;
      #    utilScripts = mkUtilScripts system;
      #  in {
      #    "${hostname}" = nixpkgs.lib.makeOverridable nixpkgs.lib.nixosSystem {
      #      inherit system;
      #      specialArgs = rec {
      #        inherit hostname username utilScripts;
      #      };
      #      modules = [ 
      #        {
      #          nixpkgs.overlays = [ myoverlay ];
      #          nixpkgs.config.allowUnfree = true;
      #          nix.registry.nixpkgs.flake = nixpkgs;
      #        }
      #        home-manager.nixosModules.home-manager 
      #        {
      #          home-manager.useGlobalPkgs = true;
      #        }
      #        (import (./hosts + "/${hostname}/default.nix"))
      #        (import (./hosts + "/${hostname}/hardware-configuration.nix"))
      #      ];
      #    };
      #  };
      #in {}
      #// (system-config "ajax" "jack" "x86_64-linux")
      #// (system-config "CASTOR" "jack" "x86_64-linux")
      #;

      #darwinConfigurations = let 
      #  darwin-system-config = hostname: username: system: 
      #  let
      #    myoverlay = mkOverlay system;
      #  in {
      #    "${hostname}" = darwin.lib.darwinSystem {
      #      specialArgs = {
      #        inherit hostname username;
      #      };
      #      modules = [
      #        {
      #          nixpkgs.overlays = [ myoverlay ];
      #          nixpkgs.config.allowUnfree = true;
      #          nix.registry.nixpkgs.flake = nixpkgs;
      #        }
      #        home-manager.darwinModules.home-manager 
      #        { 
      #          home-manager.useGlobalPkgs = true;
      #        }
      #        (import (./hosts + "/${hostname}/configuration.nix"))
      #      ];
      #    };
      #  };
      #in {}
      #// darwin-system-config "DAHDEE" "Jack" "x86_64-darwin"
      #// darwin-system-config "Jack-Michaud" "jack" "aarch64-darwin"
      #;
    };
}
