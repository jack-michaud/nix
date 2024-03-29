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

    deploy-rs.url = "github:serokell/deploy-rs";

    # nix-darwin input
    darwin.url = "github:lnl7/nix-darwin/master";
    darwin.inputs.nixpkgs.follows = "nixpkgs";
    hyprland.url = "github:hyprwm/Hyprland/main";

    hyprland-contrib = {
      url = "github:hyprwm/contrib";
      inputs.nixpkgs.follows = "nixpkgs";
    };
    hyprpicker = {
      url = "github:hyprwm/hyprpicker";
      inputs.nixpkgs.follows = "nixpkgs";
    };
    hyprpaper = {
      url = "github:hyprwm/hyprpaper";
      inputs.nixpkgs.follows = "nixpkgs";
    };
  };
  outputs = inputs@{ self, nixpkgs, nixpkgs-git, dwm, home-manager, darwin
    , doom-emacs, deploy-rs, flutter-nix, ... }:
    let
      inherit (lib.my) mapModules mapModulesRec mapHosts;
      mkPkgs = system: pkgs: extraOverlays:
        import pkgs {
          inherit system inputs;
          config.allowUnfree = true;
          config.android_sdk.accept_license = true;
          # Temporary fix https://github.com/NixOS/nixpkgs/issues/158956
          config.permittedInsecurePackages = [ "electron-13.6.9" ];
          overlays = extraOverlays;
        };
      pkgs = system:
        mkPkgs system nixpkgs ([
          (self.mkOverlay system)
          inputs.hyprpicker.outputs.overlays.default
          inputs.hyprpaper.outputs.overlays.default
          inputs.hyprland-contrib.outputs.overlays.default
        ]);
      lib = nixpkgs.lib.extend (self: super: {
        # helpful library extensions.
        my = import ./lib {
          inherit pkgs inputs darwin;
          lib = self;
        };
      });

    in {
      lib = lib.my;
      mkOverlay = system: final: prev:
        {
          unstable = mkPkgs system nixpkgs-git [ ];
          dwm = prev.dwm.overrideAttrs (oldAttrs: rec {
            src = dwm.defaultPackage.${system}.src;
            installPhase = dwm.defaultPackage.${system}.installPhase;
            buildInputs = dwm.defaultPackage.${system}.buildInputs;
          });
          my = self.mkPackages system;
          flutter-nix = flutter-nix.packages;
        } // (if system == "x86_64-linux" then
          {
            # Add custom overlays here

          }
        else
          { });

      mkPackages = system:
        let _pkgs = pkgs system;
        in mapModules ./packages (p: _pkgs.callPackage p { });
      mkPackagesWithOverlays = system: pkgs system;

      nixosConfigurations = mapHosts ./hosts/x86_64-linux "x86_64-linux" { }
        // mapHosts ./hosts/aarch64-linux "aarch64-linux" { };

      deploy.nodes = {
        donxt = {
          #hostname = "192.168.101.204";
          hostname = "donxt";
          sshUser = "root";
          sshOpts = [ "-p 60022" ];
          autoRollback = false;
          profiles.system = {
            user = "root";
            path = deploy-rs.lib.x86_64-linux.activate.nixos
              self.nixosConfigurations.donxt;
          };
        };
        familypi = {
          sshUser = "root";
          hostname = "aarch64-builder";
          profiles.system = {
            user = "root";
            path = deploy-rs.lib.aarch64-linux.activate.nixos
              self.nixosConfigurations.familypi;
          };
        };

        ajax = {
          hostname = "localhost";
          profiles.system = {
            user = "root";
            path = deploy-rs.lib.x86_64-linux.activate.nixos
              self.nixosConfigurations.ajax;
          };
        };

      };
      # deploy-rs post deploy checks:
      # This is highly advised, and will prevent many possible mistakes
      #checks = builtins.mapAttrs (system: deployLib: deployLib.deployChecks self.deploy) deploy-rs.lib;

      darwinConfigurations = mapHosts ./hosts/x86_64-darwin "x86_64-darwin" { }
        // mapHosts ./hosts/aarch64-darwin "aarch64-darwin" { };

      devShell.x86_64-linux = let pkgs = nixpkgs.legacyPackages.x86_64-linux;
      in pkgs.mkShell {
        buildInputs = [
          # get nixops from github
          deploy-rs.defaultPackage.x86_64-linux
        ];
      };
    };
}
