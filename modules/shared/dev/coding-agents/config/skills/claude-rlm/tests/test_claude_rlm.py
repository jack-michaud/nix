"""Unit tests for claude_rlm: argv construction (the three live-found claude
CLI edges), the ANTHROPIC_API_KEY env scrub, and invoke()'s outcome mapping
against a fake `claude` binary.

Runs with plain `python3 -m unittest` - no pytest, no real `claude` binary
(the fake scripts stand in; the real-binary path is covered by the live smoke
described in the skill's PR).
"""

from __future__ import annotations

import asyncio
import os
import stat
import sys
import tempfile
import unittest
import unittest.mock
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import claude_rlm  # noqa: E402


def _run(coro):
    return asyncio.run(coro)


class TestBuildArgv(unittest.TestCase):
    def test_prompt_immediately_after_dash_p(self):
        # Regression: claude's variadic --tools swallows a trailing positional
        # prompt. The prompt must sit directly after -p no matter what follows.
        argv = claude_rlm.build_argv("do the thing", tools=["read", "bash"])
        self.assertEqual(argv[argv.index("-p") + 1], "do the thing")

    def test_tool_names_mapped_and_skip_permissions(self):
        argv = claude_rlm.build_argv("p", tools=["read", "write", "edit", "bash"])
        self.assertIn("Read,Write,Edit,Bash", argv)
        self.assertIn("--dangerously-skip-permissions", argv)

    def test_no_tools_omits_flags_entirely(self):
        argv = claude_rlm.build_argv("p")
        self.assertNotIn("--tools", argv)
        self.assertNotIn("--dangerously-skip-permissions", argv)

    def test_stateless_and_text_output_always(self):
        argv = claude_rlm.build_argv("p", system="you are a planner")
        self.assertIn("--no-session-persistence", argv)
        self.assertEqual(argv[argv.index("--output-format") + 1], "text")
        self.assertEqual(argv[argv.index("--system-prompt") + 1], "you are a planner")

    def test_system_omitted_when_none(self):
        self.assertNotIn("--system-prompt", claude_rlm.build_argv("p"))

    def test_capitalized_tool_names_pass_through(self):
        argv = claude_rlm.build_argv("p", tools=["Read", "WebSearch"])
        self.assertIn("Read,WebSearch", argv)


class TestScrubEnv(unittest.TestCase):
    def test_api_key_removed_rest_kept(self):
        env = {"ANTHROPIC_API_KEY": "sk-secret", "HOME": "/home/x", "PATH": "/bin"}
        clean = claude_rlm.scrub_env(env)
        self.assertNotIn("ANTHROPIC_API_KEY", clean)
        self.assertEqual(clean["HOME"], "/home/x")
        # input dict not mutated
        self.assertEqual(env["ANTHROPIC_API_KEY"], "sk-secret")

    def test_absent_key_is_fine(self):
        self.assertEqual(claude_rlm.scrub_env({"A": "1"}), {"A": "1"})


def _fake_claude(body: str) -> str:
    d = tempfile.mkdtemp()
    path = Path(d) / "fake-claude"
    path.write_text(f"#!/bin/sh\n{body}\n")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)
    return str(path)


class TestInvoke(unittest.TestCase):
    def test_ok_returns_stdout(self):
        bin = _fake_claude("echo hello-reply")
        r = _run(claude_rlm.invoke("p", bin=bin))
        self.assertEqual(r["outcome"], "ok")
        self.assertEqual(r["stdout"].strip(), "hello-reply")
        self.assertEqual(r["exit_code"], 0)

    def test_nonzero_exit(self):
        bin = _fake_claude("echo boom >&2; exit 3")
        r = _run(claude_rlm.invoke("p", bin=bin))
        self.assertEqual(r["outcome"], "nonzero-exit")
        self.assertEqual(r["exit_code"], 3)
        self.assertIn("boom", r["stderr"])

    def test_timeout(self):
        bin = _fake_claude("sleep 10")
        r = _run(claude_rlm.invoke("p", bin=bin, timeout_ms=200))
        self.assertEqual(r["outcome"], "timeout")

    def test_spawn_error_missing_binary(self):
        r = _run(claude_rlm.invoke("p", bin="definitely-not-a-real-binary-xyz"))
        self.assertEqual(r["outcome"], "spawn-error")

    def test_run_raises_with_stderr(self):
        bin = _fake_claude("echo nope >&2; exit 1")
        with self.assertRaises(claude_rlm.ClaudeRlmError) as ctx:
            _run(claude_rlm.run("p", bin=bin))
        self.assertIn("nonzero-exit", str(ctx.exception))
        self.assertIn("nope", str(ctx.exception))

    def test_child_env_is_scrubbed(self):
        # The fake prints whether ANTHROPIC_API_KEY survived into the child.
        bin = _fake_claude('if [ -z "$ANTHROPIC_API_KEY" ]; then echo scrubbed; else echo LEAKED; fi')
        with unittest.mock.patch.dict(os.environ, {"ANTHROPIC_API_KEY": "sk-secret"}):
            r = _run(claude_rlm.invoke("p", bin=bin))
        self.assertEqual(r["stdout"].strip(), "scrubbed")


if __name__ == "__main__":
    unittest.main()
