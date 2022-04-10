# Takes all lib files in this folder and folds them into a mylib.
# Can be consumed by extending nixpkgs.lib:
# lib = nixpkgs.lib.extend
#  (self: super: { my = import ./lib { inherit pkgs inputs; lib = self }; });
# lib = lib.my 
# 
# (source: https://github.com/hlissner/dotfiles/blob/1173284b76561d41edcb17062badccda012f7f2e/flake.nix#L42-L45)
{ inputs, lib, pkgs, darwin, ... }:

let
  inherit (lib) makeExtensible attrValues foldr;
  inherit (modules) mapModules;

  modules = import ./modules.nix {
    inherit lib;
    self.attrs = import ./attrs.nix { inherit lib; self = {}; };
  };

  mylib = makeExtensible (self:
    with self; mapModules ./.
      (file: import file { inherit self lib pkgs inputs darwin; }));
in
mylib.extend
  (self: super:
    foldr (a: b: a // b) {} (attrValues super))
