{ user, pkgs, ... }:
{
    # Determinate already manages the Nix daemon, so nix-darwin shouldn't.
  nix.enable = false;

  nixpkgs.config.allowUnfree = true;
  nixpkgs.hostPlatform = "aarch64-darwin"; # use x86_64-darwin for Intel CPU

  system.primaryUser = user;
  # Plain string (not a path) so it never gets copied into the nix store.
  # Config symlinks (nvim, tmux) resolve here, so edits in the checkout
  # apply without a rebuild — same effect as mkOutOfStoreSymlink.
  dotfiles.dir = "/Users/${user}/.config/dotfiles";
  users.users.${user} = {
    home = "/Users/${user}";
  };
  system.stateVersion = 6;
  fonts.packages = [ pkgs.nerd-fonts.iosevka ];
  system.defaults = {
    NSGlobalDomain = {
      AppleInterfaceStyle = "Dark";
      KeyRepeat = 2;          # fast key repeat
      InitialKeyRepeat = 15;  # short delay before repeat
      _HIHideMenuBar = true;  # auto-hide the menu bar
      AppleShowAllExtensions = true;
    };
    dock.autohide = true;
    finder.FXPreferredViewStyle = "Nlsv";  # list view by default
    finder.CreateDesktop = false;          # clean desktop
    trackpad.Clicking = true;              # tap to click
  };
  nix-homebrew = {
    enable = true;
    autoMigrate = true;
    inherit user;
  };
  homebrew = {
    enable = true;
    onActivation.cleanup = "zap";  # remove anything not listed here
    onActivation.autoUpdate = true;
    onActivation.extraFlags = [ "--force" ];
    brews = [
      "gh"
      "herdr"
      "agavra/tap/tuicr"  # TUI code-review tool from the agavra/tap third-party tap
      "tmux"
      "neovim"
      "jj"
      "starship"
      "fzf"
      "pyenv"
      "libb2"  # pyenv-built Python links _blake2 against this; zap cleanup removes it otherwise
      "awscli"
      "postgresql@15"
      "tfenv"  # manages terraform versions; avoids homebrew-core's removal of terraform (BSL license)
      "terragrunt"
    ];
    casks = [
      "claude-code"
    ];
  };
  modules = {
    homebrew.enable = false; # Defined inline
    editors = {
      nvim.enable = true;
    };
    shells = {
      tmux.enable = true;
      zsh.enable = true;
      herdr.enable = true;
    };
    desktop = {
      terminals.alacritty.enable = true;
      jankyborders.enable = true;
    };
  };
}
