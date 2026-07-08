#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

host="${1:-DAMOCLES}"

if command -v darwin-rebuild >/dev/null 2>&1; then
  sudo darwin-rebuild switch --flake ".#${host}"
else
  # First activation: darwin-rebuild isn't on PATH yet
  sudo nix run nix-darwin/master#darwin-rebuild -- switch --flake ".#${host}"
fi
