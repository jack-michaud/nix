# nix

My NixOS configs for cross-platform (`aarch64-darwin`, `aarch64-linux`, `x86_64-linux`, and `x86_64-darwin` configs). 

Uses `deploy-rs` for deploying remote machines.

Heavy influence from:
- [Henrik Lissner](https://github.com/hlissner/dotfiles/)
- [Kyle Sferrazza](https://gitlab.com/kylesferrazza/nix/)

## Home Manager shortcuts

```
home.programs    ->  home-manager.users.{user}.programs
home.services    ->  home-manager.users.{user}.services
home.file        ->  home-manager.users.{user}.home.file
home.configFile  ->  home-manager.users.{user}.home.xdg.configFile
home.dataFile    ->  home-manager.users.{user}.home.xdg.dataFile
home.xsession     ->  home-manager.users.{user}.xsession
```

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

## Secrets with vault 

```nix
{
  config = {
    vault-secrets = {
      # Namespace of kv to look in.
      namespace = "hosts";
      secrets = {
        familypi = {
	  # Key to specify looking in Vault;
          secretsKey = "aws-creds";
	  # file that populates `VAULT_ADDR`, `VAULT_ROLE_ID` and `VAULT_SECRET_ID` in the env
	  # e.g. VAULT_ADDR=http://127.0.0.1:8200
          environmentFile = "/tmp/secrets.sh";
        };
      };
    };
  };
}
```

With namespace, the secret name, and secretsKey, this block will
pull from `kv/hosts/familypi/aws-creds` and populate the directory
`/run/secrets/familypi/<key>` as long as the familypi-secrets.service is 
required or started.

For a systemd compatible EnvironmentFile, you can
use the `environmentKey` key to populate a file with all key value pairs in `kv/<namespace>/<secret-name>/<environmentKey>` into `/run/secrets/<secret-name>/environment`. For example, the following config populates `/run/secrets/familypi/environment` with the secrets in `kv/hosts/familypi/production`:

```nix
{
  config = {
    vault-secrets = {
      namespace = "hosts";
      secrets = {
        familypi = {
          environmentKey = "production";
          environmentFile = "/tmp/secrets.sh";
        };
      };
    };
  };
}
```
```
      secrets = {
        familypi = {
	  # Key to specify looking in Vault;
          secretsKey = "aws-creds";
	  # file that populates `VAULT_ADDR`, `VAULT_ROLE_ID` and `VAULT_SECRET_ID` in the env
	  # e.g. VAULT_ADDR=http://127.0.0.1:8200
          environmentFile = "/tmp/secrets.sh";
        };
      };
