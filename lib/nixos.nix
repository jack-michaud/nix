{ inputs, lib, pkgs, darwin, self, ... }:

with lib;
with lib.my; {
  mkHost = system: path:
    attrs@{ ... }:
    let
      isDarwin = strings.hasInfix "darwin" system;
      specialArgs = {
        inherit lib inputs isDarwin;
        generators =
          (import ../utils/generators.nix { inherit lib pkgs; }).mkGenerators
          system;
      };
    in if isDarwin then
      darwin.lib.darwinSystem {
        specialArgs = specialArgs // { pkgs = pkgs system; };
        modules = [
          (filterAttrs (n: v: !elem n [ "system" ]) attrs)
          ../. # /default.nix
          (import path)
        ];
      }
    else
      (makeOverridable nixosSystem) {
        inherit system;
        specialArgs = specialArgs // { inherit system; };
        modules = [
          {
            nixpkgs.pkgs = pkgs system;
            networking.hostName =
              mkDefault (removeSuffix ".nix" (baseNameOf path));
          }
          (filterAttrs (n: v: !elem n [ "system" ]) attrs)
          ../. # /default.nix
          (import path)
          # External modules
          inputs.hyprland.nixosModules.default
        ];
      };

  # Assumes hosts dir has configurations of machines in the shape:
  # hosts/<system>/<hostname>/default.nix
  mapHosts = dir: system:
    attrs@{ ... }:
    mapModules dir (hostPath: mkHost system hostPath attrs);
}
