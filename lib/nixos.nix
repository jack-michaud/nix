{ inputs, lib, pkgs, darwin, self, ... }:

with lib;
with lib.my;
{
  mkHost = system: path: attrs @ { ... }:
    let
      isDarwin = strings.hasInfix "darwin" system; 
      specialArgs = { inherit lib inputs isDarwin; generators = (import ../utils/generators.nix { inherit lib pkgs; }).mkGenerators system; };
    in
      if isDarwin then darwin.lib.darwinSystem {
        inherit specialArgs;
        modules = [
          (filterAttrs (n: v: !elem n [ "system" ]) attrs)
          ../.   # /default.nix
          (import path)
        ];
      } else nixosSystem {
        inherit system;
        specialArgs = specialArgs // { inherit system; };
        modules = [
          {
            nixpkgs.pkgs = pkgs system;
            networking.hostName = mkDefault (removeSuffix ".nix" (baseNameOf path));
          }
          (filterAttrs (n: v: !elem n [ "system" ]) attrs)
          ../.   # /default.nix
          (import path)
        ];
      };

  # Assumes dir has configurations of machines in the shape:
  mapHosts = dir: system: attrs @ { ... }:
    mapModules dir
      (hostPath: mkHost system hostPath attrs);
}
