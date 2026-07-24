#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

host="${1:-DAMOCLES}"

# Build as the invoking user first: private git+ssh flake inputs (e.g.
# comment-trainer) need the user's ssh key, which root doesn't have. This
# puts the input sources and the system closure in the store, so root's
# eval below finds them there instead of fetching.
nix build --no-link ".#darwinConfigurations.${host}.system"

if command -v darwin-rebuild >/dev/null 2>&1; then
  sudo darwin-rebuild switch --flake ".#${host}"
else
  # First activation: darwin-rebuild isn't on PATH yet
  sudo nix run nix-darwin/master#darwin-rebuild -- switch --flake ".#${host}"
fi
