"""claude-rlm: an rlm-shaped delegation call backed by the Claude Code CLI.

`rlm.run(prompt)` spawns a Prime Agent sub-agent on this session's own model.
`claude_rlm.run(prompt)` spawns one headless Claude Code turn (`claude -p`)
instead - the inference (and any tool use) bills Jack's Claude subscription
via OAuth, not the session's metered model. It is the kernel-side twin of
agent-harness's ClaudeCodeProvider (src/runtime/providers/claude-code-provider.ts)
and carries that provider's three live-found argv edges with it:

1. The positional prompt goes IMMEDIATELY after `-p`. claude CLI's `--tools`
   is a commander variadic option that greedily swallows any bare positional
   placed after it - a trailing prompt silently becomes another tool name and
   every call fails with "Input must be provided either through stdin or as a
   prompt argument" (claude CLI 2.1.212, live discovery).
2. Tool names are claude's capitalized built-ins. Lowercase pi-style names
   register ZERO tools; the model then narrates "bash(ls ...)" as plain text
   instead of acting. `read/write/edit/bash` map to `Read/Write/Edit/Bash`.
3. A tool-enabled headless call without --dangerously-skip-permissions is
   silently DENIED (no TTY to answer the permission prompt) - the flag rides
   whenever --tools is non-empty, mirroring pi's --no-approve.

Plus the billing invariant: ANTHROPIC_API_KEY is scrubbed from the child's
environment, because a present key silently switches claude from OAuth
subscription billing to per-token API billing.

Workflows (plan -> contract -> build -> critique loops) are YOUR code: compose
`run()` calls however you like. The reference implementations worth studying
are agent-harness's src/workflows/default.ts and src/prompts/*.md.
"""

from __future__ import annotations

import asyncio
import os
import shutil
from typing import Optional

BIN = os.environ.get("CLAUDE_RLM_BIN", "claude")
DEFAULT_MODEL = os.environ.get("CLAUDE_RLM_MODEL", "claude-sonnet-5")
# 30 minutes, mirroring agent-harness's own live-run default - long tool-using
# turns are normal, not hung. There is no inactivity watchdog here (claude
# headless has no session-file stream to watch), so this ceiling is the whole
# hang story.
DEFAULT_TIMEOUT_MS = int(os.environ.get("CLAUDE_RLM_TIMEOUT_MS", "1800000"))

TOOL_NAME_MAP = {"read": "Read", "write": "Write", "edit": "Edit", "bash": "Bash"}


class ClaudeRlmError(RuntimeError):
    """The claude child failed, timed out, or could not be spawned."""


def build_argv(prompt: str, model: str = DEFAULT_MODEL,
               system: Optional[str] = None,
               tools: Optional[list[str]] = None) -> list[str]:
    """Build the claude CLI argv (everything after the binary). Pure.

    See the module docstring for why the prompt MUST sit directly after `-p`
    and why the tool names are capitalized. `system=None` omits
    --system-prompt entirely, leaving claude's own default system prompt -
    usually what you want for a tool-enabled turn.
    """
    argv = ["-p", prompt, "--model", model, "--output-format", "text"]
    if system:
        argv += ["--system-prompt", system]
    # Stateless by design: rlm calls are independent, and claude's
    # --session-id demands UUIDs with no --session-dir to control storage.
    argv.append("--no-session-persistence")
    if tools:
        argv += ["--tools", ",".join(TOOL_NAME_MAP.get(t, t) for t in tools)]
        argv.append("--dangerously-skip-permissions")
    return argv


def scrub_env(env: Optional[dict] = None) -> dict:
    """Copy `env` (default: this process's) minus ANTHROPIC_API_KEY.

    A present key silently overrides OAuth subscription billing into
    per-token API billing - this scrub is the entire reason the skill exists,
    so it is unconditional, not an option.
    """
    clean = dict(os.environ if env is None else env)
    clean.pop("ANTHROPIC_API_KEY", None)
    return clean


async def invoke(prompt: str, model: str = DEFAULT_MODEL,
                 system: Optional[str] = None,
                 tools: Optional[list[str]] = None,
                 cwd: Optional[str] = None, timeout_ms: int = DEFAULT_TIMEOUT_MS,
                 bin: str = BIN) -> dict:
    """Run one headless claude turn. Never raises: returns a result dict with
    `outcome` in {ok, nonzero-exit, timeout, spawn-error}, plus argv, exit
    code, stdout/stderr, and duration. `run()` is the raising convenience
    wrapper most callers want.
    """
    argv = build_argv(prompt, model=model, system=system, tools=tools)
    if shutil.which(bin) is None:
        return {"outcome": "spawn-error", "argv": [bin, *argv], "exit_code": None,
                "stdout": "", "stderr": f"binary not found on PATH: {bin}",
                "duration_ms": 0}
    start = asyncio.get_running_loop().time()
    try:
        proc = await asyncio.create_subprocess_exec(
            bin, *argv, cwd=cwd, env=scrub_env(),
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    except OSError as e:
        return {"outcome": "spawn-error", "argv": [bin, *argv], "exit_code": None,
                "stdout": "", "stderr": str(e), "duration_ms": 0}
    try:
        out, err = await asyncio.wait_for(proc.communicate(), timeout=timeout_ms / 1000)
    except asyncio.TimeoutError:
        proc.kill()  # SIGKILL: a hung claude has no graceful drain worth waiting on
        await proc.wait()
        return {"outcome": "timeout", "argv": [bin, *argv],
                "exit_code": proc.returncode, "stdout": "",
                "stderr": f"timed out after {timeout_ms} ms",
                "duration_ms": int((asyncio.get_running_loop().time() - start) * 1000)}
    dur = int((asyncio.get_running_loop().time() - start) * 1000)
    return {"outcome": "ok" if proc.returncode == 0 else "nonzero-exit",
            "argv": [bin, *argv], "exit_code": proc.returncode,
            "stdout": out.decode("utf-8", "replace"),
            "stderr": err.decode("utf-8", "replace"),
            "duration_ms": dur}


async def run(prompt: str, model: str = DEFAULT_MODEL,
              system: Optional[str] = None,
              tools: Optional[list[str]] = None,
              cwd: Optional[str] = None,
              timeout_ms: int = DEFAULT_TIMEOUT_MS,
              bin: str = BIN) -> str:
    """One rlm-style delegated turn on the Claude Code CLI. Returns the reply text.

    prompt:    the full task/prompt for this turn (self-contained - the call
               is stateless, nothing carries over between calls).
    model:     claude model id (default claude-sonnet-5; CLAUDE_RLM_MODEL).
    system:    optional system prompt. Omit to keep claude Code's own default,
               which is usually right for tool-enabled turns.
    tools:     subset of ["read", "write", "edit", "bash"] (claude's own
               capitalized names also accepted). Omit for a no-tools turn.
               Tool-enabled turns run with --dangerously-skip-permissions -
               point `cwd` at a throwaway checkout when the work is destructive.
    cwd:       working directory - also controls which CLAUDE.md/rules claude
               discovers.
    timeout_ms: hard ceiling (default 30 min; CLAUDE_RLM_TIMEOUT_MS).
    """
    r = await invoke(prompt, model=model, system=system, tools=tools,
                     cwd=cwd, timeout_ms=timeout_ms, bin=bin)
    if r["outcome"] != "ok":
        raise ClaudeRlmError(
            f"claude_rlm turn failed ({r['outcome']}, exit {r['exit_code']}): "
            f"{r['stderr'] or r['stdout'][:500]}")
    return r["stdout"].strip()
