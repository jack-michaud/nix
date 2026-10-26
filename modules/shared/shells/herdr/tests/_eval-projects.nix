# Standalone module tests; deliberately prefixed '_' to avoid repo auto-import.
{ flake }:
let
  pkgs = flake.mkPackagesWithOverlays builtins.currentSystem;
  lib = pkgs.lib;
  evaluate = overrides: lib.evalModules {
    specialArgs = { inherit pkgs; };
    modules = [
      ../_projects.nix
      ({ ... }: {
        options = {
          modules.shells.herdr.enable = lib.mkOption { type = lib.types.bool; default = true; };
          user.name = lib.mkOption { type = lib.types.str; default = "fixture"; };
          home.file = lib.mkOption { type = lib.types.attrs; default = { }; };
          home-manager.users = lib.mkOption { type = lib.types.attrs; default = { }; };
        };
      })
      overrides
    ];
  };
  prepared = (evaluate {
    modules.shells.herdr.projects = {
      enable = true;
      includePolicy = false;
      defaults.instructions = "shared";
      main.instructions = "main only";
      machine.instructions = "machine only";
      perProject.dotfiles.instructions = "project only";
    };
  }).config;
  default = (evaluate { modules.shells.herdr.projects.enable = true; }).config;
  manifest = builtins.fromJSON prepared.home.file.".config/herdr-projects-nix/declarations.json".text;
  specification = builtins.fromJSON (builtins.unsafeDiscardStringContext prepared.home.file.".config/herdr-projects-nix/automation.json".text);
  defaultManifest = builtins.fromJSON default.home.file.".config/herdr-projects-nix/declarations.json".text;
  invalid = (evaluate { modules.shells.herdr.projects.defaults.instructions = 7; }).config.modules.shells.herdr.projects.defaults.instructions;
in {
  results = assert (evaluate { }).config.home.file == { };
    assert manifest.scopes.defaults."coordinator.instructions" == "shared";
    assert manifest.scopes.main."coordinator.instructions" == "main only";
    assert manifest.scopes.machine."coordinator.instructions" == "machine only";
    assert manifest.scopes."project:dotfiles"."coordinator.instructions" == "project only";
    assert defaultManifest.scopes.main == { };
    assert defaultManifest.scopes.machine == { };
    assert lib.hasInfix "Jack's coordinator routing policy" defaultManifest.scopes.defaults."coordinator.instructions";
    assert specification.ready == false && specification.requested == false && specification.activationCommand == null;
    assert specification.target.machine == "DAMOCLES";
    assert !(builtins.tryEval (builtins.deepSeq invalid true)).success;
    assert !(prepared.home-manager.users.fixture.home ? activation);
    "all module declaration assertions passed";
  packages = pkgs.symlinkJoin {
    name = "herdr-projects-prepared-tools-test";
    paths = prepared.home-manager.users.fixture.home.packages;
  };
  inherit manifest specification defaultManifest;
}
