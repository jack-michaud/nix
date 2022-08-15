{
  description = "My xmonad config";

  outputs = { self, nixpkgs }: {

    packages.x86_64-linux.xmonad =
      let pkgs = import nixpkgs { system = "x86_64-linux"; };
      in pkgs.haskellPackages.developPackage {
        name = "xmonad-jack";
        root = ./.;
        modifier = drv:
          pkgs.haskell.lib.addBuildTools drv (with pkgs.haskellPackages; [
            cabal-install
            cabal-fmt
            (ghcWithPackages (p: [ p.xmonad-contrib p.xmonad xmobar ]))
            ghcid
            ormolu
            haskell-language-server
          ]);
      };

    defaultPackage.x86_64-linux = self.packages.x86_64-linux.xmonad;

  };
}
