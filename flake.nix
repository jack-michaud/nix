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
    doom-emacs.url = "github:vlaci/nix-doom-emacs";
    doom-emacs.inputs.emacs-overlay.follows = "emacs-overlay";
    emacs-overlay.url = "github:nix-community/emacs-overlay";

    kyle-sferrazza-nix = {
      url = "https://gitlab.com/kylesferrazza/nix/-/archive/main/nix-main.tar.gz";
      inputs.nixpkgs.follows = "nixpkgs";
      inputs.nixpkgs-master.follows = "nixpkgs-git";
    };


    # nix-darwin input
    darwin.url = "github:lnl7/nix-darwin/master";
    darwin.inputs.nixpkgs.follows = "nixpkgs";
  };
  outputs = inputs@{ self, nixpkgs, nixpkgs-git, dwm, home-manager, darwin, doom-emacs, kyle-sferrazza-nix, ... }:
    let 
      inherit (lib.my) mapModules mapModulesRec mapHosts;
      mkPkgs = system: pkgs: extraOverlays: import pkgs {
        inherit system;
        config.allowUnfree = true;
        overlays = extraOverlays;
      };
      pkgs = system: mkPkgs system nixpkgs ([ 
        (self.mkOverlay system) 
      ] ++ (if system == "x86_64-linux" then [
        (final: prev: {
          kyle = (kyle-sferrazza-nix.overlay final prev).mine;
        })
      ] else []));
      pkgs' = system: mkPkgs system nixpkgs-git [];

      lib = nixpkgs.lib.extend (self: super: {
        # helpful library extensions.
        my = import ./lib {
          inherit pkgs inputs darwin;
          lib = self; 
        }; 
      });

    in {
      lib = lib.my;
      mkOverlay = system: final: prev: {
        unstable = pkgs' system;
        dwm = prev.dwm.overrideAttrs (oldAttrs: rec {
          src = dwm.defaultPackage.${system}.src;
          installPhase = dwm.defaultPackage.${system}.installPhase;
          buildInputs = dwm.defaultPackage.${system}.buildInputs;
        });
        my = self.mkPackages system;
      };

      mkPackages = system: let
        _pkgs = pkgs system;
      in
        mapModules ./packages (p: _pkgs.callPackage p {});

      nixosConfigurations = 
        mapHosts ./hosts/x86_64-linux "x86_64-linux" {} //
        mapHosts ./hosts/aarch64-linux "aarch64-linux" {};

      darwinConfigurations = 
        mapHosts ./hosts/x86_64-darwin "x86_64-darwin" {} // mapHosts ./hosts/aarch64-darwin "aarch64-darwin" {};
    };
}
