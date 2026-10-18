# Match package identities, not prefixes (which also match other repositories).
# Only normalize the GitHub forms used by these declarations; leave other
# sources alone. Strip a ref only after the repository, never the SSH user.
def identity:
  ($aliases[.] // .)
  | if startswith("npm:") then
      sub("@[^/@]+$"; "")
    elif test("^(git:|https://github.com/)") then
      sub("^git:"; "")
      | sub("^(https://|ssh://git@|git@)github.com[:/]"; "github.com/")
      | sub("@[^/]+$"; "")
      | sub("\\.git$"; "")
    else . end;
def source: if type == "string" then . else .source end;

# Keep filters, including [] (disabled resources), and all other user fields.
# Prefer an object over a duplicate string when adopting an existing package.
reduce $packages[0][] as $pin (.;
  ($pin | identity) as $id
  | [(.packages // [])[] | select((source | identity) == $id)] as $old
  | (($old | map(select(type == "object")) | first) // $pin) as $entry
  | .packages = (
      [(.packages // [])[] | select((source | identity) != $id)]
      + [if ($entry | type) == "object" then $entry + {source: $pin} else $pin end]
    )
)
