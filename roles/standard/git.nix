{ username, ... }:
{
  home-manager.users."${username}".programs.git = {
    enable = true;
    userName = "Jack Michaud";
    userEmail = "jack@lomz.me";

    iniContent = {
      init = {
        defaultBranch = "main";
      };
    };
  };
}
