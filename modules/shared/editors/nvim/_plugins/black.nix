{ pkgs, config, home, ... }:
{
  home.programs.neovim.extraConfig = let
    blackVenv = pkgs.python39.withPackages (pypkgs: [
      pypkgs.black
    ]);
  in ''
    let g:black_virtualenv = "${blackVenv}"
  '';
}
