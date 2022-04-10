# Darwin specific options and config
{ config, options, lib, home-manager, ... }:

with lib;
with lib.my;
{
  options = with types; {
  };
  config = {
    user.home = "/Users/${config.user.name}";
    environment.systemPath = [ "/usr/local/bin/" ];

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
        _HIHideMenuBar = false;
      };
    };

  };
}
