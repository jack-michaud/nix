{ inputs, lib, pkgs, nix-darwin, self, ... }:

with lib;
with lib.my;
{
  mkHost = system: path: attrs @ { ... }:
    let
      isDarwin = strings.hasInfix "darwin" system;
      hostName = removeSuffix ".nix" (baseNameOf path);
      specialArgs = { inherit lib inputs isDarwin; generators = (import ../utils/generators.nix { inherit lib pkgs; }).mkGenerators system; }
        // optionalAttrs (attrs ? user) { inherit (attrs) user; };
    in
      if isDarwin then nix-darwin.lib.darwinSystem {
        specialArgs = specialArgs // { pkgs = pkgs system; };
        modules = [
          # Flake output name of this host, so shells can e.g. rebuild with
          # the right `--flake .#<host>` without guessing from `hostname`.
          { environment.variables.NIX_FLAKE_HOST = hostName; }
          (filterAttrs (n: v: !elem n [ "system" "user" ]) attrs)
          inputs.nix-homebrew.darwinModules.nix-homebrew
          ../.   # /default.nix
          (import path)
        ];
      } else (makeOverridable nixosSystem) {
        inherit system;
        specialArgs = specialArgs // { inherit system; };
        modules = [
          {
            nixpkgs.pkgs = pkgs system;
            networking.hostName = mkDefault hostName;
            environment.variables.NIX_FLAKE_HOST = hostName;
          }
          (filterAttrs (n: v: !elem n [ "system" ]) attrs)
          ../.   # /default.nix
          (import path)
        ];
      };

  # Assumes hosts dir has configurations of machines in the shape:
  # hosts/<system>/<hostname>/default.nix
  #
  # `attrs` are passed to every host. A `users` attr (hostname -> username)
  # is consumed here instead of forwarded: it sets each host's `user`
  # specialArg individually, so machines can have different accounts
  # (e.g. work `jack` vs personal `Jack`).
  mapHosts = dir: system: attrs @ { users ? { }, ... }:
    let baseAttrs = builtins.removeAttrs attrs [ "users" ];
    in mapModules dir
      (hostPath:
        let host = baseNameOf hostPath;
        in mkHost system hostPath
          (baseAttrs // optionalAttrs (users ? ${host}) { user = users.${host}; }));
}
