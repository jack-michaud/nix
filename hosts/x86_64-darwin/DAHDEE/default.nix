{ config, pkgs, ... }:
{
  # Without a platform, nix-darwin's eval aborts before it gets anywhere
  # ("Neither nixpkgs.hostPlatform nor ... nixpkgs.system has been set"), so
  # `nix flake check` could never cover this host. Intel machine.
  nixpkgs.hostPlatform = "x86_64-darwin";
  # modules/darwin/options.nix sets user-scoped `system.defaults` for every
  # darwin host, and nix-darwin now requires naming the user those apply to.
  # `config.user.name` resolves to "jack" here (the pure-eval fallback in
  # modules/shared/options.nix; this host gets no `user` specialArg).
  system.primaryUser = config.user.name;
  system.stateVersion = 4;
}
