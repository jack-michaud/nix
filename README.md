# nix

My NixOS configs. Heavy influence from:

- [Henrik Lissner](https://github.com/hlissner/dotfiles/)
- [Kyle Sferrazza](https://gitlab.com/kylesferrazza/nix/)


## Using on Darwin

Add a new `darwin-system-config` to darwinConfigurations in `flake.nix`:
```
      // darwin-system-config "DAHDEE" "Jack" "x86_64-darwin"
      // darwin-system-config "HOSTNAME" "Jack" "x86_64-darwin"
```
Then, build and switch.
```
nix build ./.\#darwinConfigurations.HOSTNAME.system
./result/sw/bin/darwin-rebuild --flake ./. switch
```
