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

    nix-homebrew.url = "github:zhaofengli/nix-homebrew";

  };
  outputs = inputs@{ self, nixpkgs, nix-darwin, nixpkgs-git, home-manager,... }:
    let
      inherit (lib.my) mapModules mapModulesRec mapHosts mkHost;
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
          inherit pkgs inputs nix-darwin;
          lib = self;
        };
      });

    in {
      lib = lib.my;

      mkOverlay = system: final: prev: {
        unstable = mkPkgs system nixpkgs-git [ ];
        my = self.mkPackages system;
      };

      mkPackages = system:
        let _pkgs = pkgs system;
        in mapModules ./packages (p: _pkgs.callPackage p { });
      mkPackagesWithOverlays = system: pkgs system;

      # Standalone home-manager for non-NixOS Linux hosts (e.g. Arch). The
      # shared modules are system modules, so hosts/x86_64-linux/<host>/home.nix
      # carries a compat bridge; see that file. Apply later (outside this task)
      # with `home-manager switch --flake .#"jack@DARKFOREST"`.
      homeConfigurations = let
        system = "x86_64-linux";
        # pkgs already carries the flake overlays (unstable, my); extend its
        # lib with `my` so the shared modules' `with lib.my;` resolves.
        basePkgs = pkgs system;
        hmPkgs = basePkgs // {
          lib = basePkgs.lib.extend (_final: _prev: { my = self.lib; });
        };
      in {
        "jack@DARKFOREST" = home-manager.lib.homeManagerConfiguration {
          pkgs = hmPkgs;
          modules = [ ./hosts/x86_64-linux/DARKFOREST/home.nix ];
        };
      };

      darwinConfigurations = mapHosts ./hosts/x86_64-darwin "x86_64-darwin" { }
        // mapHosts ./hosts/aarch64-darwin "aarch64-darwin" {
          # Per-machine user accounts, keyed by hostname.
          users = {
            DAMOCLES = "Jack";
          };
        } // {
          # Work laptop: same config as DAMOCLES, but the account is `jack`.
          KRONOS = mkHost "aarch64-darwin" ./hosts/aarch64-darwin/DAMOCLES {
            user = "jack";
            hostName = "KRONOS";
            # Work laptop: no hardware-hacking tools
            modules.dev.hardware-hacking.enable = false;
            modules.dev.coding-agents.role = "work";
          };
        };

    };
}
