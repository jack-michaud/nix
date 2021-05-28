{ inputs, config, lib, pkgs, isDarwin, ... }:

with lib;
with lib.my;
{
  imports =
    # Home manager
    [ 
      (if isDarwin then inputs.home-manager.darwinModules.home-manager else inputs.home-manager.nixosModules.home-manager) 
    ]
    # All my personal modules
    ++ (mapModulesRec' (toString ./modules/shared) import)
    ++ (mapModulesRec' (toString (if isDarwin then ./modules/darwin else ./modules/linux)) import);

  # Common config for all nixos machines; and to ensure the flake operates
  # soundly
  environment.variables.DOTFILES = config.dotfiles.dir;
  environment.variables.DOTFILES_BIN = config.dotfiles.binDir;

  # Configure nix and nixpkgs
  environment.variables.NIXPKGS_ALLOW_UNFREE = "1";
  nix =
    let filteredInputs = filterAttrs (n: _: n != "self") inputs;
        nixPathInputs  = mapAttrsToList (n: v: "${n}=${v}") filteredInputs;
        registryInputs = mapAttrs (_: v: { flake = v; }) filteredInputs;
    in {
      package = pkgs.nixFlakes;
      extraOptions = "experimental-features = nix-command flakes";
      # Fix for https://github.com/NixOS/nixpkgs/issues/124215
      sandboxPaths = [ "/bin/sh=${pkgs.bash}/bin/sh" ];
      nixPath = nixPathInputs ++ [
        "nixpkgs-overlays=${config.dotfiles.dir}/overlays"
        "dotfiles=${config.dotfiles.dir}"
      ];
      binaryCaches = [
        "https://nix-community.cachix.org"
        "https://jack-michaud-ajax.cachix.org"
      ];
      binaryCachePublicKeys = [
        "nix-community.cachix.org-1:mB9FSh9qf2dCimDSUo8Zy7bkq5CX+/rkCWyvRCYg3Fs="
        "jack-michaud-ajax.cachix.org-1:/AsBHtSL31exwTiTTnyPBiDA00HE+BkBAnl7NiwRQpw="
      ];
      registry = registryInputs // { dotfiles.flake = inputs.self; };
      
    } // (if !isDarwin then {
      autoOptimiseStore = true;
    } else {});
  system.configurationRevision = with inputs; mkIf (self ? rev) self.rev;

  # Just the bear necessities...
  environment.systemPackages = with pkgs; [
    bind
    coreutils
    git
    vim
    fzf
    wget
    gnumake
    unzip
    ripgrep
    ranger
    nodejs
    python3
  ];
} // (if isDarwin then {
  system.stateVersion = 4;
} else {
  system.stateVersion = "21.05";
  ## Some reasonable, global defaults
  # This is here to appease 'nix flake check' for generic hosts with no
  # hardware-configuration.nix or fileSystem config.
  fileSystems."/".device = mkDefault "/dev/disk/by-label/nixos";

  # Use the latest kernel
  boot = {
    kernelPackages = mkDefault pkgs.linuxPackages_5_10;
    loader = {
      efi.canTouchEfiVariables = mkDefault true;
      systemd-boot.configurationLimit = 10;
      systemd-boot.enable = mkDefault true;
    };
  };
})
