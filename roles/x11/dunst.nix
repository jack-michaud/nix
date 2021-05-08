{ home-manager, pkgs, utils, username, ... }:
{
  home-manager.users."${username}".services.dunst = {
    enable = true;
    settings = {
      global = {
        follow = "mouse";

        # The geometry of the window:
        # The geometry of the message window.
        # The height is measured in number of notifications everything else
        # in pixels.  If the width is omitted but the height is given
        # ("-geometry x2"), the message window expands over the whole screen
        # (dmenu-like).  If width is 0, the window expands to the longest
        # message displayed.  A positive x is measured from the left, a
        # negative from the right side of the screen.  Y is measured from
        # the top and down respectively.
        # The width can be negative.  In this case the actual width is the
        # screen width minus the width defined in within the geometry option.
        geometry = "300x5-30+40";

        # Show how many messages are currently hidden (because of geometry).
        indicate_hidden = "yes";

        # Shrink window if it's smaller than the width.  Will be ignored if
        # width is 0.
        shrink = "no";

        # The height of the entire notification.  If the height is smaller
        # than the font height and padding combined, it will be raised
        # to the font height and padding.

        notification_height = 0;

        # Draw a line of "separator_height" pixel height between two
        # notifications.
        # Set to 0 to disable.
        separator_height = 5;

        # Padding between text and separator.
        padding = 15;

        # Horizontal padding.
        horizontal_padding = 18;

        # Defines width in pixels of frame around the notification window.
        # Set to 0 to disable.
        frame_width = 2;

        # Defines color of the frame around the notification window.
        frame_color = "#447347";

        font = "Iosevka 12";

        # Possible values are:
        # full: Allow a small subset of html markup in notifications:
        #        <b>bold</b>
        #        <i>italic</i>
        #        <s>strikethrough</s>
        #        <u>underline</u>
        #
        #        For a complete reference see
        #        <http://developer.gnome.org/pango/stable/PangoMarkupFormat.html>.
        #
        # strip: This setting is provided for compatibility with some broken
        #        clients that send markup even though it's not enabled on the
        #        server. Dunst will try to strip the markup but the parsing is
        #        simplistic so using this option outside of matching rules for
        #        specific applications *IS GREATLY DISCOURAGED*.
        #
        # no:    Disable markup parsing, incoming notifications will be treated as
        #        plain text. Dunst will not advertise that it has the body-markup
        #        capability if this is set as a global setting.
        #
        # It's important to note that markup inside the format option will be parsed
        # regardless of what this is set to.
        markup = "full";
    
        # The format of the message.  Possible variables are:
        #   %a  appname
        #   %s  summary
        #   %b  body
        #   %i  iconname (including its path)
        #   %I  iconname (without its path)
        #   %p  progress value if set ([  0%] to [100%]) or nothing
        #   %n  progress value if set without any extra characters
        #   %%  Literal %
        # Markup is allowed
        format = "<b>%s</b>\n%b";
    
        # Alignment of message text.
        # Possible values are "left", "center" and "right".
        alignment = "left";
    
        # Show age of message if message is older than show_age_threshold
        # seconds.
        # Set to -1 to disable.
        show_age_threshold = 60;
    
        # Split notifications into multiple lines if they don't fit into
        # geometry.
        word_wrap = "yes";
    
        # When word_wrap is set to no, specify where to make an ellipsis in long lines.
        # Possible values are "start", "middle" and "end".
        ellipsize = "middle";
    
        # Ignore newlines '\n' in notifications.
        ignore_newline = "no";
    
        # Stack together notifications with the same content
        stack_duplicates = true;
    
        # Hide the count of stacked notifications with the same content
        hide_duplicate_count = false;
    
        # Display indicators for URLs (U) and actions (A).
        show_indicators = "yes";
    
        ### Icons ###
    
        # Align icons left/right/off
        icon_position = "left";
    
        # Scale larger icons down to this size, set to 0 to disable
        max_icon_size = 32;
    
        # Paths to default icons.
        #icon_path = "/usr/share/icons/gnome/16x16/status/:/usr/share/icons/gnome/16x16/devices/";
    
        ### History ###
    
        # Should a notification popped up from history be sticky or timeout
        # as if it would normally do.
        sticky_history = "yes";
    
        # Maximum amount of notifications kept in history
        history_length = 20;


      };

      shortcuts = {
        close = "ctrl+space";
        close_all = "ctrl+shift+space";
        history = "ctrl+grave";
        context = "ctrl+shift+period";
      };

      urgency_low = {
        background = "#0f1519";
        foreground = "#C7ABB1";
        timeout = 10;
      };
      urgency_normal = {
        background = "#0f1519";
        foreground = "#F1EBEB";
        timeout = 10;
      };
      urgency_critical = {
        background = "#D63E53";
        foreground = "#F1EBEB";
        frame_color = "#AE9DA3";
        timeout = 0;
      };
    };
  };
} 

