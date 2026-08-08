---
name: claude-rlm
description: Delegate a prompt to the Claude Code CLI (claude -p) as an rlm-shaped sub-call, so the inference bills Jack's Claude subscription via OAuth instead of the session's model. Use when a task needs a delegated coding/reasoning turn - with or without tools - and you want it on the subscription, or when building planner/generator/evaluator-style workflow loops in the kernel.
compatibility: Requires the `claude` binary on PATH, authenticated via Claude subscription OAuth. Runs inside the agent kernel. Each call is a stateless subprocess turn.
---

# claude-rlm

`rlm.run(prompt)` spawns a Prime Agent sub-agent on this session's model.
`claude_rlm.run(prompt)` spawns one headless Claude Code turn instead - same
"delegate a unit of work, get text back" shape, but the inference (and any
tool use) rides Jack's Claude subscription via OAuth. It is the kernel-side
twin of agent-harness's `ClaudeCodeProvider`.

```python
reply = await claude_rlm.run("Explain the watcher pattern in pr-watch")

code = await claude_rlm.run(
    "Write a fizzbuzz.py in this directory, then run it and paste the output",
    tools=["write", "bash"], cwd="/tmp/scratch")

review = await claude_rlm.run(
    DIFF_TEXT, model="claude-opus-4-8",
    system="You are a strict reviewer. Reply with findings only.")
```

Shell form (same call, reply on stdout):

```bash
claude_rlm "Summarize this repo" --cwd /path/to/repo
claude_rlm "Add a --verbose flag to main.py" --tools write edit bash --cwd /path
```

## Model

- **One call = one stateless turn.** Nothing carries over between `run()` calls
  (`--no-session-persistence` always). A multi-round loop (contract
  negotiation, build-critique) is YOUR code: keep the state in Python and put
  the previous round's text into the next prompt, the way
  agent-harness's `src/workflows/default.ts` does. Its prompt templates
  (`src/prompts/*.md` in the agent-harness repo) are the reference for
  planner/generator/evaluator role prompts.
- **Billing is the point.** The child env is scrubbed of `ANTHROPIC_API_KEY`,
  because a present key silently switches claude from OAuth subscription
  billing to per-token API billing. The scrub is unconditional.
- **`tools=`** accepts pi-style lowercase names (`read`, `write`, `edit`,
  `bash`) or claude's own capitalized names; the module maps them. Omit
  `tools` for a no-tools turn. Tool-enabled turns pass
  `--dangerously-skip-permissions` (headless has no TTY to answer permission
  prompts - without it every tool call is silently denied), so point `cwd=`
  at a throwaway checkout when the work is destructive.
- **`cwd=`** controls both the working directory and which `CLAUDE.md`/rules
  claude discovers - project conventions apply to tool-enabled turns for free.
- **`system=None` keeps claude's own default system prompt** - usually right
  for tool-enabled turns. Pass `system=` to pin a role (planner, reviewer...)
  for text-only turns.
- **Timeout** is a hard ceiling (default 30 min, `CLAUDE_RLM_TIMEOUT_MS`,
  per-call `timeout_ms=`). There is no inactivity watchdog - this ceiling is
  the whole hang story.
- **Concurrency** is ordinary asyncio: `asyncio.create_task(claude_rlm.run(...))`
  or `asyncio.gather(...)` for fan-out. The skill adds nothing of its own.
- **Failures raise `ClaudeRlmError`** naming the outcome (nonzero-exit /
  timeout / spawn-error) and stderr. `invoke()` is the never-raising variant
  returning the full result dict (`outcome`, `exit_code`, `stdout`, `stderr`,
  `duration_ms`, `argv`) for loops that handle failures themselves.
- Overrides: `CLAUDE_RLM_BIN`, `CLAUDE_RLM_MODEL`, `CLAUDE_RLM_TIMEOUT_MS`.
