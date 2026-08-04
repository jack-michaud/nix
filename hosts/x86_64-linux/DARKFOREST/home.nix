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
    ../../../modules/shared/dev/agent-harness.nix
    ../../../modules/shared/dev/comment-trainer.nix
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
    # agent-harness / comment-trainer install via `environment.systemPackages`
    # (a NixOS/darwin option). Declare it here and fold it into the native
    # `home.packages` below.
    environment.systemPackages = mkOption {
      type = types.listOf types.package;
      default = [ ];
      description = "System packages; mapped to home.packages below.";
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

    # herdr's config module never installs the herdr binary — on darwin that
    # comes from Homebrew. On Linux take it from the `unstable` overlay
    # (nixpkgs master), which tracks a newer herdr than the pinned nixpkgs
    # ships. Setting `package` also makes the plugin-link activation reference
    # the store path directly: home-manager's activation script replaces PATH
    # with a fixed set of store paths, so a `command -v herdr` lookup there
    # would never find the profile-installed binary.
    modules.shells.herdr = {
      enable = true;
      package = pkgs.unstable.herdr;
    };
    modules.dev.coding-agents = {
      enable = true;
      role = "personal";
    };
    # Private tools from flake inputs (built from source), mirroring DAMOCLES.
    modules.dev.agent-harness.enable = true;
    modules.dev.comment-trainer.enable = true;

    home.packages = config.environment.systemPackages
      ++ [ config.modules.shells.herdr.package ];

    # Bridge: system modules add activation under home-manager.users.<user>;
    # in standalone HM those must land in the top-level home.activation.
    home.activation = mkMerge (mapAttrsToList
      (_user: u: u.home.activation)
      config.home-manager.users);
  };
}
