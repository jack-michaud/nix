# Standalone home-manager config for DARKFOREST (Arch Linux, non-NixOS).
#
# The shared modules (herdr, coding-agents) are written as NixOS/darwin
# *system* modules: they read `dotfiles.*`, `user.name`,
# `environment.variables.NIX_FLAKE_HOST`, and reach into
# `home-manager.users.<user>` for activation. None of those exist in a
# standalone home-manager evaluation, so this entrypoint provides a thin
# compat bridge that declares those options and re-injects the
# `home-manager.users.<user>.home.activation` block into the native
# `home.activation`. The shared modules are imported unchanged, so darwin
# (DAMOCLES/KRONOS) is unaffected.
{ config, lib, pkgs, ... }:

with lib;

let
  username = "jack";
  homeDir = "/home/${username}";
  # Live checkout on this machine. String (not a path) so the config-file
  # symlinks the modules emit resolve to the checkout — edits apply without a
  # rebuild, and nothing gets copied into the nix store.
  checkout = "/home/jack/Code/github.com/jack-michaud/nix";
in
{
  imports = [
    ../../../modules/shared/shells/herdr
    ../../../modules/shared/dev/coding-agents
  ];

  # ---- compat: system-module options the shared modules read -------------
  options = {
    user = mkOption {
      type = types.attrs;
      default = { };
      description = "Primary user; shared modules read `user.name`.";
    };
    dotfiles = {
      dir = mkOption { type = types.str; };
      modulesDir = mkOption { type = types.str; };
      vaultDir = mkOption { type = types.str; };
    };
    environment.variables = mkOption {
      type = types.attrsOf types.str;
      default = { };
      description = "System env vars; shared modules read NIX_FLAKE_HOST.";
    };
    # coding-agents defines `home-manager.users.<user>.home.activation`
    # (there's no `home.activation` alias at the system level). Catch it here
    # and fold it into the native HM `home.activation` below.
    home-manager.users = mkOption {
      type = types.attrsOf (types.submodule {
        options.home.activation = mkOption {
          type = types.attrs;
          default = { };
        };
      });
      default = { };
    };
  };

  config = {
    home.username = username;
    home.homeDirectory = homeDir;
    home.stateVersion = "26.05";

    user = {
      name = username;
      home = homeDir;
    };
    dotfiles = {
      dir = checkout;
      modulesDir = "${checkout}/modules";
      vaultDir = "${homeDir}/Vault";
    };
    environment.variables.NIX_FLAKE_HOST = "DARKFOREST";

    modules.shells.herdr.enable = true;
    modules.dev.coding-agents = {
      enable = true;
      role = "personal";
    };

    # Bridge: system modules add activation under home-manager.users.<user>;
    # in standalone HM those must land in the top-level home.activation.
    home.activation = mkMerge (mapAttrsToList
      (_user: u: u.home.activation)
      config.home-manager.users);
  };
}
