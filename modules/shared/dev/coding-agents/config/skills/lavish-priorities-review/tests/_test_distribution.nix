{ pkgs }:
let
  baseLib = pkgs.lib;
  lib = baseLib // {
    my = {
      mkBoolOpt = default: baseLib.mkOption { type = baseLib.types.bool; inherit default; };
      mkOpt = type: default: baseLib.mkOption { inherit type default; };
    };
  };
  skillsDir = ../.;
  names = builtins.attrNames (lib.filterAttrs (_: type: type == "directory")
    (builtins.readDir (skillsDir + "/..")));
  module = import ../../../../default.nix;
  fakePkgs = {
    runCommandLocal = name: attrs: script: { inherit name script; };
    writeText = name: text: { inherit name text; };
    writeShellScript = name: text: { inherit name text; };
    jq = "/mock/jq";
  };
  evaluate = enabled: (lib.evalModules {
    specialArgs = { inherit lib; pkgs = fakePkgs; };
    modules = [
      ({ ... }: {
        options = {
          dotfiles = lib.mkOption { type = lib.types.attrs; };
          environment = lib.mkOption { type = lib.types.attrs; };
          user = lib.mkOption { type = lib.types.attrs; };
          home.file = lib.mkOption { type = lib.types.attrs; default = {}; };
          home-manager = lib.mkOption { type = lib.types.attrs; default = {}; };
        };
        config = {
          dotfiles = { modulesDir = "/mock/modules"; dir = "/mock/checkout"; vaultDir = "/mock/vault"; };
          environment.variables.NIX_FLAKE_HOST = "mock-host";
          user.name = "mock-user";
          modules.dev.coding-agents.enable = enabled;
        };
      })
      module
    ];
  }).config;
  files = (evaluate true).home.file;
  neutral = lib.filter (lib.hasPrefix ".agents/skills/") (builtins.attrNames files);
  prime = lib.filter (lib.hasPrefix ".prime/agent/skills/") (builtins.attrNames files);
  neutralName = ".agents/skills/lavish-priorities-review";
  target = "/mock/modules/shared/dev/coding-agents/config/skills/";
in
assert neutral == [ neutralName ];
assert prime == map (name: ".prime/agent/skills/${name}") names;
assert builtins.all (name: lib.hasInfix "ln -s ${target}${name} $out"
  files.".prime/agent/skills/${name}".source.script) names;
assert lib.hasInfix "ln -s ${target}lavish-priorities-review $out" files.${neutralName}.source.script;
assert files.${neutralName}.source.name == "lavish-priorities-review-neutral";
assert (evaluate false).home.file == {};
assert files.".pi/agent/AGENTS.md".source.name == "pi-AGENTS.md";
assert lib.hasInfix "ln -s /mock/modules/shared/dev/coding-agents/config/pi/AGENTS.md $out"
  files.".pi/agent/AGENTS.md".source.script;
assert builtins.hasAttr ".pi/agent/extensions/agent-rules.ts" files;
assert !(builtins.hasAttr ".pi/agent/settings.json" files);
{
  passed = true;
  neutralLinks = neutral;
  primeLinks = prime;
  note = "Real module evaluated with build primitives stubbed; not activation.";
}
