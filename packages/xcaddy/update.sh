#!/usr/bin/env nix-shell
#!nix-shell -i bash -p wget nix-prefetch-git jq


set -euo pipefail
dirname="$(dirname "$0")"

function write_info_file {
  version=$1
  sha256=$2
  vendorSha256=$3

  echo "Writing ./package-info.json"
  cat <<EOF | tee $dirname/package-info.json
{
  "version": "$version",
  "vendorSha256": "$vendorSha256",
  "sha256": "$sha256"
}
EOF
}

# Get latest version
latest_release=$(curl --silent https://api.github.com/repos/caddyserver/xcaddy/releases/latest)
version=$(jq -r '.tag_name' <<< "$latest_release")
echo Got latest release version: $version

# get sha256 of source
sha256=$(nix-prefetch-git --quiet --rev ${version} https://github.com/caddyserver/xcaddy | jq -r .sha256)

echo Got sha256 of $version: $sha256

echo Getting vendorSha256...nullifying existing vendorSha256
write_info_file $version $sha256 "0000000000000000000000000000000000000000000000000000"
set +e
echo "Running build"
vendorSha256="$(nix build 2>&1 | grep "got:" | cut -d":" -f2 | xargs)"
echo "Got $vendorSha256"
write_info_file $version $sha256 $vendorSha256
set -e


