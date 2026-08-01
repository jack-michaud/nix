#!/usr/bin/env bash
set -euo pipefail

# This test deliberately runs rebuild.sh with only disposable command shims in
# front of PATH. It does not need Nix, darwin-rebuild, or SSH keys installed.
root_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
test_dir=$(mktemp -d)
trap 'rm -rf "$test_dir"' EXIT
mock_bin="$test_dir/bin"
mkdir -p "$mock_bin"
# Keep rebuild.sh's PATH completely isolated while allowing /usr/bin/env bash
# in the command shims to resolve.
ln -s "$(command -v bash)" "$mock_bin/bash"
ln -s "$(command -v dirname)" "$mock_bin/dirname"

cat > "$mock_bin/nix" <<'MOCK_NIX'
#!/usr/bin/env bash
set -euo pipefail
log=${REBUILD_TEST_LOG:?}
case "${1:-}" in
  build)
    printf 'nix build GIT_SSH_COMMAND=%s\n' "${GIT_SSH_COMMAND-}" >> "$log"
    ;;
  run)
    printf 'nix run GIT_SSH_COMMAND=%s args=%s\n' "${GIT_SSH_COMMAND-}" "$*" >> "$log"
    ;;
  *)
    printf 'unexpected nix operation: %s\n' "${1:-}" >&2
    exit 1
    ;;
esac
MOCK_NIX

cat > "$mock_bin/sudo" <<'MOCK_SUDO'
#!/usr/bin/env bash
set -euo pipefail
log=${REBUILD_TEST_LOG:?}
if [[ ${1:-} != --preserve-env=GIT_SSH_COMMAND ]]; then
  printf 'sudo did not preserve GIT_SSH_COMMAND: %s\n' "$*" >&2
  exit 1
fi
shift
printf 'sudo GIT_SSH_COMMAND=%s command=%s args=%s\n' \
  "${GIT_SSH_COMMAND-}" "${1:-}" "$*" >> "$log"
exec "$@"
MOCK_SUDO

cat > "$mock_bin/darwin-rebuild" <<'MOCK_DARWIN'
#!/usr/bin/env bash
set -euo pipefail
printf 'darwin-rebuild GIT_SSH_COMMAND=%s args=%s\n' \
  "${GIT_SSH_COMMAND-}" "$*" >> "${REBUILD_TEST_LOG:?}"
MOCK_DARWIN
chmod +x "$mock_bin/nix" "$mock_bin/sudo" "$mock_bin/darwin-rebuild"

assert_log_line() {
  local log=$1
  local expected=$2
  grep -F -- "$expected" "$log" >/dev/null || {
    printf 'expected log entry not found:\n%s\nactual log:\n%s' \
      "$expected" "$(cat "$log")" >&2
    exit 1
  }
}

run_supported_case() {
  local host=$1
  local key_name=$2
  local activation_path=$3
  local home="$test_dir/home-$host-$activation_path"
  local log="$test_dir/$host-$activation_path.log"
  local expected_ssh

  mkdir -p "$home/.ssh"
  : > "$log"
  expected_ssh="ssh -F /dev/null -i $home/.ssh/$key_name -o IdentitiesOnly=yes -o UserKnownHostsFile=$home/.ssh/known_hosts"

  # Presence of this command selects rebuild.sh's existing darwin-rebuild
  # branch. Removing it below selects the first-activation nix-run branch.
  if [[ $activation_path == darwin-rebuild ]]; then
    :
  else
    rm -f "$mock_bin/darwin-rebuild"
  fi

  if ! HOME="$home" PATH="$mock_bin" REBUILD_TEST_LOG="$log" \
      bash "$root_dir/rebuild.sh" "$host"; then
    printf 'supported host failed: %s (%s)\n' "$host" "$activation_path" >&2
    exit 1
  fi

  # The build shim only succeeds after receiving the SSH environment. Its
  # first log entry also proves assignment happened before build invocation.
  assert_log_line "$log" "nix build GIT_SSH_COMMAND=$expected_ssh"
  if [[ $activation_path == darwin-rebuild ]]; then
    assert_log_line "$log" "sudo GIT_SSH_COMMAND=$expected_ssh command=darwin-rebuild"
    assert_log_line "$log" "darwin-rebuild GIT_SSH_COMMAND=$expected_ssh"
  else
    assert_log_line "$log" "sudo GIT_SSH_COMMAND=$expected_ssh command=nix"
    assert_log_line "$log" "nix run GIT_SSH_COMMAND=$expected_ssh"
  fi

  [[ $(sed -n '1p' "$log") == "nix build GIT_SSH_COMMAND=$expected_ssh" ]]
  [[ $(wc -l < "$log") -eq 3 ]]

  # Restore the command for the next case if this case tested first activation.
  if [[ $activation_path != darwin-rebuild ]]; then
    chmod +x "$mock_bin/darwin-rebuild" 2>/dev/null || true
    cat > "$mock_bin/darwin-rebuild" <<'MOCK_DARWIN'
#!/usr/bin/env bash
set -euo pipefail
printf 'darwin-rebuild GIT_SSH_COMMAND=%s args=%s\n' \
  "${GIT_SSH_COMMAND-}" "$*" >> "${REBUILD_TEST_LOG:?}"
MOCK_DARWIN
    chmod +x "$mock_bin/darwin-rebuild"
  fi
}

run_unsupported_case() {
  local home="$test_dir/home-unsupported"
  local log="$test_dir/unsupported.log"
  mkdir -p "$home/.ssh"
  : > "$log"

  if HOME="$home" PATH="$mock_bin" REBUILD_TEST_LOG="$log" \
      bash "$root_dir/rebuild.sh" NOT_A_HOST >"$test_dir/unsupported.out" 2>"$test_dir/unsupported.err"; then
    printf 'unsupported host unexpectedly succeeded\n' >&2
    exit 1
  fi
  grep -F 'Unsupported host: NOT_A_HOST' "$test_dir/unsupported.err" >/dev/null
  [[ ! -s "$log" ]] || {
    printf 'unsupported host invoked a mocked operation:\n%s' "$(cat "$log")" >&2
    exit 1
  }
}

run_supported_case DAMOCLES id_rsa darwin-rebuild
run_supported_case KRONOS id_ecdsa nix-run
run_unsupported_case
printf 'rebuild host-key tests passed\n'
