{ pkgs, home-manager, ... }:
{
  imports = [
    ./plugins
  ];
  home-manager.users.jack.programs.neovim = {
    enable = true;
    viAlias = true;
    vimAlias = true;
    withNodeJs = true;
    withPython3 = true;
  };
  home-manager.users.jack.home.sessionVariables.EDITOR = "nvim";
  home-manager.users.jack.programs.neovim.extraConfig = ''
    let mapleader = "`"
    map <Space> <leader>
  '';
}
