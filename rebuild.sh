#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

host="${1:-DAMOCLES}"

# Build as the invoking user first: private git+ssh flake inputs (e.g.
# comment-trainer) need the user's ssh key, which root doesn't have. This
# puts the input sources and the system closure in the store, so root's
# eval below finds them there instead of fetching.
nix build --no-link ".#darwinConfigurations.${host}.system"

# git+ssh flake inputs (type=git, e.g. comment-trainer, agent-harness) always
# do a live git operation during evaluation to materialize/verify their tree,
# even when a matching store path is already cached from the build above — so
# root's eval below still needs real ssh access, not just a pre-warmed store.
# No ssh-agent/Keychain is in play on this machine (plain unencrypted key
# file), so point git straight at it rather than trying to forward an agent
# socket. Root can read the file fine (root ignores unix permission bits) —
# it just doesn't otherwise know the file exists, since sudo's env_reset
# resets $HOME to root's, so `~` in ~/.ssh/config resolves to /var/root.
export GIT_SSH_COMMAND="ssh -F /dev/null -i ${HOME}/.ssh/id_ecdsa -o IdentitiesOnly=yes -o UserKnownHostsFile=${HOME}/.ssh/known_hosts"

if command -v darwin-rebuild >/dev/null 2>&1; then
  sudo --preserve-env=GIT_SSH_COMMAND darwin-rebuild switch --flake ".#${host}"
else
  # First activation: darwin-rebuild isn't on PATH yet
  sudo --preserve-env=GIT_SSH_COMMAND nix run nix-darwin/master#darwin-rebuild -- switch --flake ".#${host}"
fi
