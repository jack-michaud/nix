{ config, options, lib, pkgs, ... }:

with lib;
with lib.my;
let
  cfg = config.modules.dev.prime-agent;

  # Where the agent lands. `npm install -g` writes to <prefix>/{bin,lib}, and
  # the nix-provided node has its prefix inside the read-only store, so the
  # installer is pointed at a writable directory under $HOME instead.
  prefix = cfg.prefix;

  # Prime Agent is not distributed as a package: it is not on the public npm
  # registry, and the vendor ships a shell installer that downloads a release
  # tarball from their bucket and runs `npm install -g` on it. Building it from
  # source (github.com/PrimeIntellect-ai/prime-agent) was considered and
  # rejected — the release tarball pins its three @earendil-works/pi-* deps by
  # bucket URL, so there is no lockfile to hand `buildNpmPackage`, and the tree
  # carries prebuilt native addons (zeromq, koffi) that would need patching.
  # For a personal config that is more machinery than the payoff justifies, so
  # this module runs the vendor installer at activation time. The honest cost:
  # activation touches the network and the result is NOT reproducible from the
  # flake alone. Everything below is about making that impurity well-behaved —
  # pinned, idempotent, non-interactive, and never fatal.
  installer = pkgs.writeShellScript "install-prime-agent" ''
    set -u

    # Activation runs with a minimal environment, so every tool is referenced
    # by store path. node/npm on PATH is also what keeps the installer's
    # interactive "Install Node.js and npm? [Y/n]" branch from ever being
    # reached — activation has no terminal to answer it.
    export PATH=${makeBinPath [ pkgs.nodejs pkgs.curl pkgs.coreutils pkgs.gnutar pkgs.gzip pkgs.gnused pkgs.gnugrep pkgs.which ]}:$PATH

    version=${escapeShellArg cfg.version}
    prefix=${escapeShellArg prefix}
    bin="$prefix/bin"

    warn() {
      echo "prime-agent: $*" >&2
    }

    # `prime-agent --version` prints to STDERR (not stdout) and pads the
    # number with blank lines, so read both streams and pick the version out.
    installed_version() {
      "$bin/${cfg.command}" --version 2>&1 </dev/null \
        | grep -Eo '[0-9]+\.[0-9]+\.[0-9]+' | head -1
    }

    # Idempotency: a switch on an already-current machine must not re-download
    # anything, so compare the installed binary's version against the pin.
    if [ -x "$bin/${cfg.command}" ]; then
      installed=$(installed_version)
      if [ "$installed" = "$version" ]; then
        echo "prime-agent: $version already installed at $bin, skipping."
        exit 0
      fi
      echo "prime-agent: installed version '$installed' != pinned '$version', reinstalling."
    fi

    tmp=$(mktemp -d) || { warn "could not create a temp dir; skipping install."; exit 0; }
    trap 'rm -rf "$tmp"' EXIT

    # Pin the release, suppress the full-screen TTY UI (activation has no
    # terminal), and send the installer's PATH-export line to a throwaway file:
    # it appends to ~/.zshrc or ~/.bashrc by default, which home-manager owns.
    # The bin dir reaches PATH through `home.sessionPath` instead.
    export PRIME_AGENT_VERSION="$version"
    export PRIME_AGENT_INSTALLER_PLAIN=1
    export PRIME_AGENT_SHELL_PROFILE="$tmp/unused-profile"
    export PRIME_AGENT_BOOTSTRAP_KERNEL_ON_INSTALL=${if cfg.bootstrapKernel then "1" else "0"}
    export npm_config_prefix="$prefix"
    export npm_config_fund=false
    export npm_config_audit=false
    mkdir -p "$prefix"

    # A machine that is offline (or a bucket that is down) must not break a
    # switch: warn and leave whatever is already installed in place.
    if ! curl -fsSL --max-time 120 ${escapeShellArg cfg.installerUrl} -o "$tmp/install.sh"; then
      warn "could not download the installer (offline?); leaving the current install alone."
      exit 0
    fi

    if ! sh "$tmp/install.sh"; then
      warn "installer failed; leaving the current install alone."
      exit 0
    fi

    if [ -x "$bin/${cfg.command}" ]; then
      echo "prime-agent: installed $(installed_version) at $bin."
    else
      warn "installer reported success but $bin/${cfg.command} is missing."
    fi
  '';
in {
  options.modules.dev.prime-agent = {
    enable = mkBoolOpt false;
    # Bumping the agent is a one-line change here. The installer verifies the
    # release it downloads, so this is the only knob that decides what runs.
    version = mkOpt types.str "0.7.0";
    installerUrl =
      mkOpt types.str "https://app.primeintellect.ai/prime-agent/install.sh";
    # npm global prefix; must be writable, so it lives under $HOME.
    prefix = mkOpt types.str "${config.user.home}/.local/share/prime-agent";
    command = mkOpt types.str "prime-agent";
    # The installer can also provision uv/Python/ipykernel for the agent's
    # IPython tool. Off by default so a switch stays a small download: `uv`
    # comes from nixpkgs below, and the agent builds the kernel venv itself on
    # first use. Turning this on only moves that one-time venv build earlier.
    bootstrapKernel = mkBoolOpt false;
  };

  # Everything here goes through `home-manager.users.<user>` rather than a
  # bare `home.*`: nix-darwin has no system-level `home.packages` /
  # `home.sessionPath`, and DARKFOREST's standalone-home-manager bridge folds
  # this namespace back into its native `home.*`.
  config = mkIf cfg.enable {
    home-manager.users.${config.user.name} = { lib, ... }: {
      # The installed CLI is a `#!/usr/bin/env node` script, so it needs a
      # node at *runtime*, not just at install time. Ship the same nodejs the
      # installer runs against rather than depending on a distro package.
      # `uv` is NOT optional, despite bootstrapKernel defaulting to false. The
      # agent's IPython tool calls ensureUv() (dist/core/kernel/bootstrap.js),
      # which looks for uv on PATH, then at ~/.local/bin/uv, and otherwise
      # either PROMPTS to install it or throws:
      #
      #   "uv is required to set up the Python kernel. Install uv yourself ...
      #    or set PRIME_AGENT_INSTALL_UV=1 to let prime-agent run that installer."
      #
      # A prompt is not an option for an agent running unattended, so shipping
      # uv declaratively satisfies that first branch. It also keeps a second
      # `curl | sh` (astral.sh's uv installer) out of the picture entirely -
      # one impure vendor installer in this module is enough.
      home.packages = [ pkgs.nodejs pkgs.uv ];

      # `npm install -g` puts the CLI in <prefix>/bin, which nothing else adds
      # to PATH (the installer's own profile edit is deliberately neutralised).
      home.sessionPath = [ "${prefix}/bin" ];

      home.activation = {
        # `run` honours $DRY_RUN_CMD, so `home-manager build` / dry-activate
        # prints the script instead of installing anything.
        primeAgent = lib.hm.dag.entryAfter [ "writeBoundary" ] ''
          run ${installer}
        '';
      };
    };
  };
}
