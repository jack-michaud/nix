"""nix-config-change: delegate a change to Jack's nix config to a sub-agent that ships it.

One call spawns a sub-agent that edits the flake, evaluates it for real, then
commits/pushes/opens a PR with the `jj-ship` skill and reports back. Jack asks
for nix-config changes often; this keeps the house conventions in one place
instead of re-deriving them every session.
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any, Optional

NIX_REPO = os.environ.get("NIX_CONFIG_REPO",
                          str(Path.home() / "Code/github.com/jack-michaud/nix"))
DEFAULT_HOST = os.environ.get("NIX_CONFIG_HOST", "DARKFOREST")

# The house conventions a sub-agent would otherwise have to rediscover by
# reading the whole tree. Keep this in sync with the repo's own README.
CONVENTIONS = """\
Repo layout and conventions (verify against the tree, do not assume):
- `modules/shared/**` holds cross-platform modules, `modules/linux/**` and
  `modules/darwin/**` the platform-specific ones; `hosts/<system>/<HOST>/`
  enables them per machine. A shared module is written as a NixOS/darwin
  SYSTEM module even when a host consumes it through standalone home-manager
  (DARKFOREST bridges the option namespaces itself - read its home.nix before
  adding an option a standalone evaluation would not have).
- Options use this repo's `lib.my` helpers (`mkBoolOpt`, `mkOpt`) under
  `modules.<area>.<name>`, default off, and are enabled from the host file.
- Config FILES belonging to a module live beside it in `config/` and are
  deployed as live symlinks into the checkout (the `pkgs.runCommandLocal ...
  ln -s` pattern), so edits apply without a rebuild. Copy that pattern rather
  than inlining file contents into nix strings, unless the file needs
  build-time `@var@` substitution (then use `substitute`, as AGENTS.md does).
- Prefer deriving a set from the filesystem (`builtins.readDir`) over a
  hand-maintained list, so adding a file needs no nix edit.
- Comments explain WHY a non-obvious thing is done, in full sentences.\
"""

VERIFY = """\
Verification (required, do not skip, do not claim it without output):
- `nix flake check --no-build` in the repo root, and
- a real evaluation of the affected host, e.g.
  `nix build --no-link .#homeConfigurations."jack@{host}".activationPackage`
  (or the matching `darwinConfigurations.<HOST>.system` for a darwin host).
- If the change deploys files, show the built symlink/target so the reviewer
  can see it points where the comment says it does.
- Do NOT run `home-manager switch` / `darwin-rebuild switch`: activating the
  change is Jack's call, not yours.\
"""


def build_prompt(change: str, repo: str = NIX_REPO, host: str = DEFAULT_HOST,
                 bookmark: str = "", ship: bool = True,
                 extra: str = "", lease_id: str = "") -> str:
    """Render the sub-agent task prompt (pure - useful for review before spawning)."""
    lease_block = f"""
YOUR WORKSPACE. You are working in {repo!r}, an isolated jj workspace leased for
this change - not a shared checkout. Work only there.
RELEASE IT AS YOUR LAST STEP, after the PR is open, whether or not the change
succeeded:

    subprocess.run(["treehouse", "return", {repo!r}, "--if-lease-id", {lease_id!r}, "--force"])

`--if-lease-id` means you can only release your own lease, never someone else's.
A leased workspace that is never returned pins a pool slot indefinitely.
""" if lease_id else ""
    ship_block = f"""
Ship it with the `jj-ship` skill (already installed in your kernel as `jj_ship`;
read its SKILL.md if you need the API):

    await jj_ship.commit("<imperative summary>", repo={repo!r}, bookmark={bookmark or "<short-kebab-branch>"!r})
    await jj_ship.push(repo={repo!r})
    await jj_ship.open_pr("<title>", body=BODY, repo={repo!r})
    await jj_ship.watch(repo={repo!r})   # CI + review comments

The PR body must lead with one bold sentence saying what changed, then Context,
then what changed, then an Evidence section quoting the REAL command output from
the verification step. Do not merge the PR - report and stop.
""" if ship else """
Do NOT commit, push, or open a PR. Leave the change in the working copy and
report exactly what you edited.
"""

    return f"""Make a change to Jack's nix config at {repo}.

REQUESTED CHANGE
{change}

{CONVENTIONS}

{VERIFY.format(host=host)}
{lease_block}{ship_block}
{extra}
Reply to your parent with `await agent_message.send(<report>, receiver_role='parent')`:
the files you touched, the verification commands you ran WITH their real output,
the PR URL and CI state if you shipped, and anything you deliberately did not do.
"""



def acquire_workspace(repo: str = NIX_REPO, holder: str = "nix-config-change") -> dict:
    """Lease an isolated jj workspace for this change, so concurrent changes cannot collide.

    treehouse manages the workspaces; this only drives it. `TREEHOUSE_VCS` is passed
    explicitly rather than inherited: hm-session-vars.sh guards on __HM_SESS_VARS_SOURCED,
    which agent kernels inherit already set, so the variable never reaches us.
    """
    out = subprocess.run(
        ["treehouse", "get", "--lease", "--json", "--lease-holder", holder],
        cwd=repo, capture_output=True, text=True,
        env={**os.environ, "TREEHOUSE_VCS": "jj", "TREEHOUSE_NO_UPDATE_CHECK": "1"})
    if out.returncode != 0:
        raise RuntimeError(f"treehouse could not lease a workspace: {out.stderr.strip() or out.stdout.strip()}")
    lease = json.loads(out.stdout)
    path = lease.get("path") or lease.get("worktree") or ""
    # A git-flavored slot is silently wrong: jj commands fail later, deep in the ship step.
    if not path or not Path(path, ".jj").exists():
        release_workspace(path, lease.get("lease_id", ""))
        raise RuntimeError(f"leased {path!r} is not a jj workspace (pool slot is git-flavored); "
                           f"run `treehouse destroy` on it to migrate")
    return {"path": path, "lease_id": lease.get("lease_id", "")}


def release_workspace(path: str, lease_id: str = "") -> None:
    """Return the workspace. `--if-lease-id` means we can only ever release our own."""
    if not path:
        return
    argv = ["treehouse", "return", path, "--force"]
    if lease_id:
        argv[3:3] = ["--if-lease-id", lease_id]
    subprocess.run(argv, capture_output=True, text=True,
                   env={**os.environ, "TREEHOUSE_NO_UPDATE_CHECK": "1"})


async def run(change: str, repo: str = NIX_REPO, host: str = DEFAULT_HOST,
              bookmark: str = "", ship: bool = True, extra: str = "",
              name: str = "nix-config-change", dry_run: bool = False,
              workspace: bool = True) -> str:
    """Spawn a sub-agent to make (and by default ship) a change to the nix config.

    change:   what to change, in plain language - the more concrete the better.
    repo:     path to the nix config checkout.
    host:     host whose configuration must evaluate as proof.
    bookmark: jj bookmark / branch name for the PR (the agent picks one if empty).
    ship:     commit + push + open PR + watch CI via the jj-ship skill.
    dry_run:  render and return the prompt without spawning anything.
    workspace: lease an isolated treehouse workspace instead of using `repo`'s
              working copy, so two changes in flight cannot collide.
    """
    if dry_run:
        return build_prompt(change, repo=repo, host=host, bookmark=bookmark,
                            ship=ship, extra=extra)
    lease = acquire_workspace(repo, holder=f"{name}/{bookmark or 'change'}") if workspace else None
    work_in = lease["path"] if lease else repo
    prompt = build_prompt(change, repo=work_in, host=host, bookmark=bookmark,
                          ship=ship, extra=extra,
                          lease_id=(lease or {}).get("lease_id", ""))
    import rlm  # provided by the agent runtime, only available inside the kernel

    try:
        handle = await rlm.run(prompt, name=name)
    except BaseException:
        if lease:
            release_workspace(lease["path"], lease["lease_id"])
        raise
    info: dict[str, Any] = {
        "spawned": getattr(handle, "name", name),
        "rlm_child_id": getattr(handle, "rlm_child_id", None),
        "model": getattr(handle, "model", None),
        "repo": work_in,
        "lease": lease,
        "ship": ship,
        "note": "The sub-agent replies with agent_message when it is done; "
                "do not poll it.",
    }
    return json.dumps(info, indent=2, default=str)
