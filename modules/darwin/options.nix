# Darwin specific options and config
{ config, options, lib, home-manager, ... }:

with lib;
with lib.my;
{
  options = with types; {
  };
  config = {
    user.home = "/Users/${config.user.name}";
    # NOTE: /usr/local/bin is intentionally NOT prepended here — it's full of
    # 2018 Intel-homebrew relics (git 2.19 etc.) that would shadow nix
    # packages. macOS path_helper still appends it via /etc/paths.

    system.defaults = {
      dock = {
        show-recents = false;
        autohide = true;
      };
      finder = {
        # show desktop icons
        CreateDesktop = false;
        # warn on changing file extension
        FXEnableExtensionChangeWarning = false;
        # show file extensions
        AppleShowAllExtensions = true;
      };
      NSGlobalDomain = {
        # dark mode
        AppleInterfaceStyle = "Dark";
        # hide menu bar
        _HIHideMenuBar = mkDefault false;
      };
    };

  };
}
