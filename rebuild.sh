#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

host="${1:-DAMOCLES}"

# Each machine uses a different GitHub account. Resolve the host before doing
# anything that could evaluate the flake, since an unknown host must never
# fall through to a key belonging to another machine.
case "$host" in
  DAMOCLES)
    github_key="${HOME}/.ssh/id_rsa"
    ;;
  KRONOS)
    github_key="${HOME}/.ssh/id_ecdsa"
    ;;
  *)
    printf 'Unsupported host: %s\n' "$host" >&2
    exit 2
    ;;
esac

# Keep this setting in the invoking user's environment for the build and
# explicitly preserve it when sudo runs the activation as root. In
# particular, use an explicit known_hosts file because sudo changes HOME.
export GIT_SSH_COMMAND="ssh -F /dev/null -i ${github_key} -o IdentitiesOnly=yes -o UserKnownHostsFile=${HOME}/.ssh/known_hosts"

# Build as the invoking user first: private git+ssh flake inputs (e.g.
# comment-trainer) need the user's ssh key, which root doesn't have. This
# puts the input sources and the system closure in the store, so root's
# eval below finds them there instead of fetching.
nix build --no-link ".#darwinConfigurations.${host}.system"

if command -v darwin-rebuild >/dev/null 2>&1; then
  sudo --preserve-env=GIT_SSH_COMMAND darwin-rebuild switch --flake ".#${host}"
else
  # First activation: darwin-rebuild isn't on PATH yet
  sudo --preserve-env=GIT_SSH_COMMAND nix run nix-darwin/master#darwin-rebuild -- switch --flake ".#${host}"
fi
