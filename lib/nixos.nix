{ inputs, lib, pkgs, darwin, ... }:

with lib;
with lib.my;
{
  mkHost = system: path: attrs @ { ... }:
    let
      isDarwin = strings.hasInfix "darwin" system; 
    in
      (if isDarwin then darwin.lib.darwinSystem else nixosSystem) {
        inherit system;
        specialArgs = { inherit lib inputs system isDarwin; };
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
