{ pkgs }:
let
  # Reuse the repository fixture: it evaluates the real coding-agents module
  # with only build primitives stubbed, and asserts unchanged neutral/settings.
  distribution = import ../../lavish-priorities-review/tests/_test_distribution.nix {
    inherit pkgs;
  };
  name = ".prime/agent/skills/cross-project-feature";
in
assert distribution.passed;
assert builtins.elem name distribution.primeLinks;
assert !(builtins.elem ".agents/skills/cross-project-feature" distribution.neutralLinks);
distribution // {
  checkedSkill = name;
  activation = false;
}
