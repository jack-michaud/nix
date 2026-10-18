# Called by Home Manager with an absolute Herdr binary and trusted sources.
# Presence-only: leave installed versions and disabled plugins to Herdr/user.
if [ "$#" -lt 1 ]; then
  echo "usage: install-herdr-plugins HERDR [OWNER/REPO[/SUBDIR] ...]" >&2
  exit 2
fi
herdr_bin=$1
shift

for plugin in "$@"; do
  wanted=$(jq -nr --arg source "$plugin" '
    $source | if test("^[A-Za-z0-9][A-Za-z0-9_.-]*/[A-Za-z0-9][A-Za-z0-9_.-]*(/[A-Za-z0-9_.-]+)*$")
    then split("/") | .[0:2] |= map(ascii_downcase) | join("/")
    else error("expected OWNER/REPO[/SUBDIR]") end
  ')
  installed=$("$herdr_bin" plugin list --json </dev/null | jq -ce '
    .result.plugins | if type == "array" then .
    else error("invalid Herdr plugin list response") end
  ')
  if jq -e --arg wanted "$wanted" '
    any(.[];
      .source.kind == "github" and
      (([.source.owner, .source.repo] | map(ascii_downcase) | join("/"))
        + (if (.source.subdir // "") == "" then "" else "/" + .source.subdir end)) == $wanted)
  ' <<<"$installed" >/dev/null; then
    echo "Herdr plugin $plugin already installed; leaving its version and enablement unchanged"
    continue
  fi

  # One-time migration from this module's former store-built plugins. Herdr
  # refuses a GitHub install over a local link. Never unlink a development
  # checkout, another plugin, or a disabled plugin without an owner decision.
  legacy_id=""
  legacy_suffix=""
  case "$wanted" in
    nathanflurry/herdr-plugin-jj-workspace)
      legacy_id=nathanflurry.jj-workspace
      legacy_suffix=-herdr-plugin-jj-workspace-dir
      ;;
    eliasstravik/herdr-projects)
      legacy_id=herdr-projects
      legacy_suffix=-herdr-projects-plugin-dir
      ;;
  esac
  legacy_root=""
  if [ -n "$legacy_id" ]; then
    legacy=$(jq -c --arg id "$legacy_id" --arg suffix "$legacy_suffix" '
      [.[] | select(.plugin_id == $id and .source.kind == "local"
        and (.plugin_root | test("^/nix/store/[0-9a-z]{32}-[^/]+$") and endswith($suffix)))]
      | if length > 1 then error("duplicate legacy plugin id") else .[0] // empty end
    ' <<<"$installed")
    if [ -n "$legacy" ]; then
      if ! jq -e '.enabled == true' <<<"$legacy" >/dev/null; then
        echo "Herdr plugin $legacy_id is a disabled legacy Nix link; leaving it untouched. Unlink it yourself when ready to adopt native installs." >&2
        exit 1
      fi
      legacy_root=$(jq -r '.plugin_root' <<<"$legacy")
      # Unlink uses Herdr's API: a legacy migration needs a running server;
      # fresh installs do not. Do not start/restart a server from activation.
      "$herdr_bin" plugin unlink "$legacy_id" </dev/null
    fi
  fi

  if "$herdr_bin" plugin install --yes "$plugin" </dev/null; then
    echo "Installed Herdr plugin $plugin (versions are now managed by Herdr)"
  else
    status=$?
    if [ -n "$legacy_root" ]; then
      echo "Install failed; restoring the previous Nix link for $legacy_id" >&2
      "$herdr_bin" plugin link "$legacy_root" </dev/null || echo "Could not restore $legacy_root; relink it manually" >&2
    fi
    exit "$status"
  fi
done
