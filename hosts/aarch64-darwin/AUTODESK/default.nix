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

  # ~/.cargo/bin holds `cargo install`ed tools (jmos). Same two routes as
  # above: paths.d for path_helper (login shells, Cursor), and systemPath
  # for nix-darwin's /etc/zshenv, which non-interactive shells do read.
  environment.etc."paths.d/20-cargo".text = "/Users/${user}/.cargo/bin";
  environment.systemPath = [ "/Users/${user}/.cargo/bin" ];

  # `darwin-rebuild` runs Home Manager via `sudo -u`, which uses secure_path
  # and drops Determinate's nix. Keep nix on sudo PATH, and also bake a
  # nix-build into HM activation so the sanity check does not depend on sudo.
  security.sudo.extraConfig = ''
    Defaults secure_path="/nix/var/nix/profiles/default/bin:/run/current-system/sw/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"
  '';
  home-manager.users.${user}.home = {
    extraActivationPath = [ pkgs.nix ];

    # MaintainX monorepo worktrees don't get the gitignored mise.local.toml
    # that normally sets MX_SLUG, so export it globally. Reaches zsh via the
    # hm-session-vars.sh that config/zshrc sources.
    sessionVariables.MX_SLUG = "jackmichaud";
  };

  # System-level tools for the MaintainX skill-share repo. Its mise.toml
  # installs the language toolchains (go, node, yarn, python, uv, shellcheck,
  # lychee, rumdl), so only mise itself comes from nix here. awscli2 is for
  # the AWS CodeArtifact credentials skill-share's yarn setup needs. git and
  # gh are listed directly rather than via modules.dev.git, which also writes
  # a personal git identity that does not belong on this work laptop.
  user.packages = with pkgs; [
    mise
    git
    gh
    awscli2
  ];

  nix-homebrew = {
    enable = true;
    autoMigrate = true;
    inherit user;
  };
  homebrew = {
    enable = true;
    brews = [
      "gh"
      "neovim"
      "herdr"
      "agavra/tap/tuicr"  # TUI code-review tool from the agavra/tap third-party tap
      "ffmpeg"
      "fzf"
      "awscli"
      "tfenv"  # manages terraform versions; avoids homebrew-core's removal of terraform (BSL license)
    ];
  };

  modules = {
    # Apple clang must win for `cc`/`gcc` (e.g. native Ruby gems), so no Nix gcc.
    dev.nixGcc.enable = false;
    # jmos client config, as it is on this machine (./jmos-config.toml): a
    # local jmosd ("home") plus the jmosd on DAMOCLES ("personal"), whose To
    # Do's the primary workspace shows. The client is disabled on this host
    # (enable = false); the file applies as is if it is turned back on. The
    # token is this machine's secret JMOSD_TOKEN_AUTODESK (~/.zshrc.local or
    # `av`); the file only holds the `${KEY}` reference. DAMOCLES.house is
    # the house network name, not the tailnet one
    # (damocles.bison-draconis.ts.net), chosen by Jack on 2026-11-11. jmosd's
    # TCP has no TLS, so on that path the token and the replicated data are
    # not encrypted, and the personal server is only reachable while on the
    # house network.
    desktop.apps.jmos = {
      enable = false;
      configFile = ./jmos-config.toml;
    };
    # Shared AGENTS.md / CLAUDE.md and agent rules. The Personal vault is not
    # cloned on this laptop, so its section and vault.md rule are left out.
    # This is the MaintainX laptop, so it also gets the MaintainX rules.
    # withLocal points agents at ~/.agents/AGENTS.local.md, the work-only
    # instructions kept on this machine and never committed.
    dev.coding-agents = {
      enable = true;
      role = "work";
      withVault = false;
      withMaintainx = true;
      withLocal = true;
    };
    editors.nvim.enable = true;
    shells = {
      zsh.enable = true;
      herdr.enable = true;
      herdr.cursorStatus = true;
    };
  };
}
