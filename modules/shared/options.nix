# Shared options and config
{ config, options, lib, home-manager, ... }:

with lib;
with lib.my;
{
  options = with types; {
    user = mkOpt attrs {};
    dotfiles = let t = either str path; in {
      dir = mkOpt t
        (findFirst pathExists (toString ../.) [
          "${config.user.home}/.config/dotfiles"
          "/etc/dotfiles"
        ]);
      modulesDir = mkOpt t "${config.dotfiles.dir}/modules";
      binDir = mkOpt t "${config.dotfiles.dir}/bin";
      configDir = mkOpt t "${config.dotfiles.dir}/../config";
      vaultDir = mkOpt t "${config.user.home}/Vault";
    };

    home = {
      file       = mkOpt' attrs {} "Files to place directly in $HOME";
      programs   = mkOpt' attrs {} "Programs to enable via home-manager";
      services   = mkOpt' attrs {} "Services to enable via home-manager";
      configFile = mkOpt' attrs {} "Files to place in $XDG_CONFIG_HOME";
      dataFile   = mkOpt' attrs {} "Files to place in $XDG_DATA_HOME";
      xsession   = mkOpt' attrs {} "Xsession settings";
    };

    env = mkOption {
      type = attrsOf (oneOf [ str path (listOf (either str path)) ]);
      apply = mapAttrs
        (n: v: if isList v
               then concatMapStringsSep ":" (x: toString x) v
               else (toString v));
      default = {};
      description = "TODO";
    };
  };

  config = {
    user =
      let user = builtins.getEnv "USER";
          name = if elem user [ "" "root" ] then "jack" else user;
      in {
        inherit name;
        description = "The primary user account";
        home = "/home/${name}";

      };

    home-manager = {
      #   home.programs    ->  home-manager.users.jack.programs
      #   home.services    ->  home-manager.users.jack.services
      #   home.file        ->  home-manager.users.jack.home.file
      #   home.configFile  ->  home-manager.users.jack.home.xdg.configFile
      #   home.dataFile    ->  home-manager.users.jack.home.xdg.dataFile
      #   home.xsession     ->  home-manager.users.jack.xsession
      users.${config.user.name} = {
        programs = mkAliasDefinitions options.home.programs;
        services = mkAliasDefinitions options.home.services;
        xsession = mkAliasDefinitions options.home.xsession;
        home = {
          file = mkAliasDefinitions options.home.file;
          # Necessary for home-manager to work with flakes, otherwise it will
          # look for a nixpkgs channel.
          stateVersion = "21.05";
        };
        xdg = {
          configFile = mkAliasDefinitions options.home.configFile;
          dataFile   = mkAliasDefinitions options.home.dataFile;
        };
      };
    };

    users.users.${config.user.name} = mkAliasDefinitions options.user;

    nix = let users = [ "root" config.user.name ]; in {
      trustedUsers = users;
      allowedUsers = users;
    };

    # must already begin with pre-existing PATH. Also, can't use binDir here,
    # because it contains a nix store path.
    env.PATH = [ "$DOTFILES_BIN" "$XDG_BIN_HOME" "$PATH" ];

    environment.extraInit =
      concatStringsSep "\n"
        (mapAttrsToList (n: v: "export ${n}=\"${v}\"") config.env);
  };
}
