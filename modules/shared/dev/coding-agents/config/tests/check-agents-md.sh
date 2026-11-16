#!/usr/bin/env bash
# Build each host's deployed CLAUDE.md and check the vault section is present
# only where withVault is on. Run from the repo root: modules/shared/dev/coding-agents/config/tests/check-agents-md.sh
set -uo pipefail
export PATH=/nix/var/nix/profiles/default/bin:$PATH
fail=0
check() { # host user expect(yes|no)
  f=$(nix build --no-link --print-out-paths ".#darwinConfigurations.$1.config.home-manager.users.$2.home.file.\".claude/CLAUDE.md\".source" 2>/dev/null) || { echo "BUILD FAIL $1"; fail=1; return; }
  has=no; grep -q "Obsidian vault" "$f" && has=yes
  grep -q -e '<!--' -e '@[a-zA-Z]*@' "$f" && { echo "FAIL $1: markers left in $f"; fail=1; }
  grep -q "ui-sdk.dev" "$f" || { echo "FAIL $1: no ui-sdk section"; fail=1; }
  if [ "$has" = "$3" ]; then echo "ok   $1 vault=$has $f"; else echo "FAIL $1 vault=$has want $3 $f"; fail=1; fi
}
check DAMOCLES Jack yes
check KRONOS jack yes
check AUTODESK michauj no
exit $fail
