#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

# Determinate puts nix on PATH from /etc/zshrc, which login-only / GUI shells
# (Cursor, non-interactive) never read. Make the script self-sufficient.
if ! command -v nix >/dev/null 2>&1; then
  if [ -x /nix/var/nix/profiles/default/bin/nix ]; then
    export PATH="/nix/var/nix/profiles/default/bin:$PATH"
  elif [ -e /nix/var/nix/profiles/default/etc/profile.d/nix-daemon.sh ]; then
    # shellcheck disable=SC1091
    . /nix/var/nix/profiles/default/etc/profile.d/nix-daemon.sh
  fi
fi
if ! command -v nix >/dev/null 2>&1; then
  printf 'nix not found on PATH. Source /nix/var/nix/profiles/default/etc/profile.d/nix-daemon.sh and retry.\n' >&2
  exit 1
fi

if [ -n "${1:-}" ]; then
  host="$1"
else
  case "$(hostname -s)" in
    ADSKDGYJY10G7W) host="AUTODESK" ;;
    KRONOS) host="KRONOS" ;;
    *) host="DAMOCLES" ;;
  esac
fi

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
  AUTODESK|ADSKDGYJY10G7W)
    host="AUTODESK"
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
nix_bin="$(command -v nix)"
nix build --no-link ".#darwinConfigurations.${host}.system"

# sudo's secure_path ignores the caller's PATH (and --preserve-env=PATH),
# so pass PATH via env and invoke nix/darwin-rebuild by absolute path.
sudo_cmd=(sudo --preserve-env=GIT_SSH_COMMAND env "PATH=${PATH}")
if command -v darwin-rebuild >/dev/null 2>&1; then
  "${sudo_cmd[@]}" "$(command -v darwin-rebuild)" switch --flake ".#${host}"
else
  # First activation: darwin-rebuild isn't on PATH yet
  "${sudo_cmd[@]}" "${nix_bin}" run nix-darwin/master#darwin-rebuild -- switch --flake ".#${host}"
fi
