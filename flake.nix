{
  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixpkgs-unstable";

    nix-darwin.url = "github:nix-darwin/nix-darwin/master";
    nix-darwin.inputs.nixpkgs.follows = "nixpkgs";

    nixpkgs-git.url = "github:NixOS/nixpkgs/master";

    home-manager = {
      url = "github:nix-community/home-manager";
      inputs.nixpkgs.follows = "nixpkgs";
    };

  };
  outputs = inputs@{ self, nixpkgs, nix-darkwin, nixpkgs-git, home-manager,... }:
    let
      inherit (lib.my) mapModules mapModulesRec mapHosts;
      mkPkgs = system: pkgs: extraOverlays:
        import pkgs {
          inherit system;
          config.allowUnfree = true;
          config.android_sdk.accept_license = true;
          overlays = extraOverlays;
        };
      pkgs = system: mkPkgs system nixpkgs ([ (self.mkOverlay system) ]);
      lib = nixpkgs.lib.extend (self: super: {
        # helpful library extensions.
        my = import ./lib {
          inherit pkgs inputs darwin;
          lib = self;
        };
      });

    in {
      lib = lib.my;

      mkPackages = system:
        let _pkgs = pkgs system;
        in mapModules ./packages (p: _pkgs.callPackage p { });
      mkPackagesWithOverlays = system: pkgs system;

      darwinConfigurations = mapHosts ./hosts/x86_64-darwin "x86_64-darwin" { }
        // mapHosts ./hosts/aarch64-darwin "aarch64-darwin" { };

    };
}
