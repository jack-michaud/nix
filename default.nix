{ inputs, config, lib, pkgs, isDarwin, ... }:

with lib;
with lib.my;
{
  imports =
    # Home manager
    [
      (if isDarwin then
        inputs.home-manager.darwinModules.home-manager
      else
        inputs.home-manager.nixosModules.home-manager)
    ]
    # All my personal modules
    ++ (mapModulesRec' (toString ./modules/shared) import) ++ (mapModulesRec'
      (toString (if isDarwin then ./modules/darwin else ./modules/linux))
      import);

  # Common config for all nixos machines; and to ensure the flake operates
  # soundly
  environment.variables.DOTFILES = config.dotfiles.dir;

  # Install home-manager packages through the system profile
  # (/etc/profiles/per-user) instead of a per-user nix profile, which
  # doesn't exist under a Determinate-managed daemon.
  home-manager.useUserPackages = true;

  # Configure nix and nixpkgs
  environment.variables.NIXPKGS_ALLOW_UNFREE = "1";
  nix = let
    filteredInputs = filterAttrs (n: _: n != "self") inputs;
    nixPathInputs = mapAttrsToList (n: v: "${n}=${v}") filteredInputs;
    registryInputs = mapAttrs (_: v: { flake = v; }) filteredInputs;
  in {
    package = pkgs.nixFlakes;
    extraOptions = ''
      experimental-features = nix-command flakes
      builders-use-substitutes = true
    '';

    nixPath = nixPathInputs ++ [
      "nixpkgs-overlays=${config.dotfiles.dir}/../overlays"
      "dotfiles=${config.dotfiles.dir}"
    ];
    registry = registryInputs // { dotfiles.flake = inputs.self; };


  } // (if !isDarwin then { settings.auto-optimise-store = true; } else { });
  system.configurationRevision = with inputs; mkIf (self ? rev) self.rev;

  # Just the bear necessities...
  environment.systemPackages = with pkgs; [
    bind
    coreutils-prefixed
    git
    vim
    fzf
    wget
    gnumake
    unzip
    ripgrep
    ranger
    nodejs
    gcc
    htop
  ];
} // (if isDarwin then {
  system.stateVersion = 4;
} else {
  system.stateVersion = mkDefault "21.05";
  ## Some reasonable, global defaults
  # This is here to appease 'nix flake check' for generic hosts with no
  # hardware-configuration.nix or fileSystem config.
  fileSystems."/".device = mkDefault "/dev/disk/by-label/nixos";

  boot = {
    kernelPackages = mkDefault pkgs.linuxPackages_5_15;
    tmpOnTmpfs = mkDefault true;
    loader = {
      efi.canTouchEfiVariables = mkDefault true;
      systemd-boot.configurationLimit = 10;
      systemd-boot.enable = mkDefault true;
    };
  };
  security.doas.enable = true;

  # DNS servers
  networking.nameservers = mkDefault [ "192.168.0.250" "1.1.1.1" ];
  networking.enableIPv6 = true;
})
