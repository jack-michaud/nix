#!/usr/bin/env bash
# Build each host's deployed CLAUDE.md and check the vault section is present
# only where withVault is on and the MaintainX section only where withMaintainx is on. Run from the repo root: modules/shared/dev/coding-agents/config/tests/check-agents-md.sh
set -uo pipefail
export PATH=/nix/var/nix/profiles/default/bin:$PATH
fail=0
check() { # host user vault(yes|no) maintainx(yes|no)
  f=$(nix build --no-link --print-out-paths ".#darwinConfigurations.$1.config.home-manager.users.$2.home.file.\".claude/CLAUDE.md\".source" 2>/dev/null) || { echo "BUILD FAIL $1"; fail=1; return; }
  has=no; grep -q "Obsidian vault" "$f" && has=yes
  grep -q -e '<!--' -e '@[a-zA-Z]*@' "$f" && { echo "FAIL $1: markers left in $f"; fail=1; }
  grep -q "ui-sdk.dev" "$f" || { echo "FAIL $1: no ui-sdk section"; fail=1; }
  mx=no; grep -q "Git branch names at MaintainX" "$f" && mx=yes
  if [ "$has" = "$3" ] && [ "$mx" = "$4" ]; then echo "ok   $1 vault=$has maintainx=$mx $f"; else echo "FAIL $1 vault=$has want $3, maintainx=$mx want $4 $f"; fail=1; fi
}
check DAMOCLES Jack yes no
check KRONOS jack yes no
check AUTODESK michauj no yes
exit $fail
