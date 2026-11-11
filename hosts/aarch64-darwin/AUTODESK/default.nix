{ user, pkgs, ... }:
{
  # Determinate already manages the Nix daemon, so nix-darwin shouldn't.
  nix.enable = false;

  nixpkgs.config.allowUnfree = true;
  nixpkgs.hostPlatform = "aarch64-darwin";

  system.primaryUser = user;
  # Live checkout path so herdr/zsh config symlinks stay out of the store.
  # Edits in this repo apply without a rebuild.
  dotfiles.dir = "/Users/${user}/Code/github.com/jack-michaud/nix";
  users.users.${user} = {
    home = "/Users/${user}";
  };
  system.stateVersion = 6;

  # path_helper (login shells, Cursor) only keeps entries from /etc/paths.d.
  # Determinate's snippet lives in /etc/zshrc, which non-interactive shells skip.
  environment.etc."paths.d/10-nix-determinate".text =
    "/nix/var/nix/profiles/default/bin";

  # `darwin-rebuild` runs Home Manager via `sudo -u`, which uses secure_path
  # and drops Determinate's nix. Keep nix on sudo PATH, and also bake a
  # nix-build into HM activation so the sanity check does not depend on sudo.
  security.sudo.extraConfig = ''
    Defaults secure_path="/nix/var/nix/profiles/default/bin:/run/current-system/sw/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"
  '';
  home-manager.users.${user}.home.extraActivationPath = [ pkgs.nix ];

  nix-homebrew = {
    enable = true;
    autoMigrate = true;
    inherit user;
  };
  homebrew = {
    enable = true;
    brews = [
      "neovim"
      "herdr"
    ];
  };

  modules = {
    # jmos as a client of the jmosd on DAMOCLES, To Do's only. The token is
    # this machine's secret JMOSD_TOKEN_AUTODESK (~/.zshrc.local or `av`).
    desktop.apps.jmos = {
      enable = true;
      server = {
        host = "DAMOCLES.house";
        tokenKey = "JMOSD_TOKEN_AUTODESK";
      };
    };
    editors.nvim.enable = true;
    shells = {
      zsh.enable = true;
      herdr.enable = true;
    };
  };
}
