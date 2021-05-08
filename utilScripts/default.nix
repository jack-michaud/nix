{ pkgs, ...  }:
{
  # All of these scripts are added to systemPackages!
  nixos-rebuild-switch = pkgs.writeShellScriptBin "nixos-rebuild-switch" ''
    # I want this to work, but no clue how.
    # https://discourse.nixos.org/t/how-to-do-a-flake-build-in-non-nixos-system/10450/7
    # https://discourse.nixos.org/t/build-nixos-config-without-environment-dependencies-and-have-nixos-option-nixos-rebuild-support/6940/3
  '';

  test-script = pkgs.writeShellScriptBin "test-script" ''
    echo 'testo scripto'
  '';

  spotify-dbus-status = callPackage ./spotify-dbus-spotify.nix {};
}
