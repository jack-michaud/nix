"""Framework-clean rule middleware for Deep Agents applications.

Seam: ``wrap_tool_call`` records matching file touches and ``wrap_model_call``
adds the resulting rule bodies to the system message before the next model call.
Guarantees: rules are read from the configured directory, path globs match the
Claude/pi contract, and each rule is emitted once per thread key. Non-guarantee:
this does not persist state across a process restart; dcode's thread/checkpoint
identity is used when available.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

from langchain.agents.middleware import AgentMiddleware
from langchain.agents.middleware.types import ModelRequest, ModelResponse, ToolCallRequest
from langchain_core.messages import SystemMessage


TOOL_NAMES = frozenset({
    "Read", "Edit", "Write", "NotebookEdit", "Glob", "Grep",
    "read_file", "edit_file", "write_file", "glob", "grep",
})


# Keep these deliberately aligned with global-rule-files.py and pi-extensions/agent-rules.ts.
def parse_paths_list(frontmatter: str) -> list[str]:
    inline = re.search(r"^paths:\s*\[([^\]]*)\]", frontmatter, re.MULTILINE)
    if inline:
        entries = [entry.strip().strip("\"'") for entry in inline.group(1).split(",")]
        return [entry for entry in entries if entry]
    block = re.search(r"^paths:\s*\r?\n((?:\s+-\s+.*\r?\n?)+)", frontmatter, re.MULTILINE)
    if not block:
        return []
    entries = [
        re.sub(r"^\s+-\s+", "", line).strip().strip("\"'")
        for line in block.group(1).splitlines()
    ]
    return [entry for entry in entries if entry]


def parse_rule(name: str, raw: str) -> dict[str, Any]:
    match = re.match(r"^---\r?\n([\s\S]*?)\r?\n---\r?\n?", raw)
    if not match:
        return {"name": name, "paths": [], "body": raw.strip()}
    return {
        "name": name,
        "paths": parse_paths_list(match.group(1)),
        "body": raw[match.end():].strip(),
    }


def glob_to_regexp(glob: str) -> re.Pattern[str]:
    expanded = os.path.join(os.path.expanduser("~"), glob[2:]) if glob.startswith("~/") else glob
    source = re.sub(r"[.+^${}()|\[\]\\]", lambda match: "\\" + match.group(0), expanded)
    source = source.replace("**", "\x00")
    source = source.replace("*", "[^/]*")
    source = source.replace("?", "[^/]")
    source = source.replace("\x00", ".*")
    return re.compile("^" + source + "$")


def matches(rule: dict[str, Any], absolute_path: str) -> bool:
    return any(glob_to_regexp(pattern).match(absolute_path) for pattern in rule["paths"])


def rule_reminder(rule: dict[str, Any], source: str = "~/.agents/rules") -> str:
    return f'<agent-rule source="{source}/{rule["name"]}">\n{rule["body"]}\n</agent-rule>'


def load_rules(rules_dir: Path) -> list[dict[str, Any]]:
    try:
        names = sorted(path.name for path in rules_dir.iterdir())
    except OSError:
        return []
    rules = []
    for name in names:
        if not name.endswith(".md"):
            continue
        try:
            rules.append(parse_rule(name, (rules_dir / name).read_text(encoding="utf-8")))
        except OSError:
            continue
    return rules


def _tool_path(args: object) -> str | None:
    if not isinstance(args, dict):
        return None
    for key in ("file_path", "path", "filePath", "notebook_path"):
        value = args.get(key)
        if isinstance(value, str) and value:
            return value
    return None


def _thread_key(runtime: object) -> str:
    info = getattr(runtime, "execution_info", None)
    thread_id = getattr(info, "thread_id", None)
    if thread_id:
        return str(thread_id)
    config = getattr(runtime, "config", None) or {}
    configurable = config.get("configurable", {}) if isinstance(config, dict) else {}
    if configurable.get("thread_id"):
        return str(configurable["thread_id"])
    return "middleware-instance"


class AgentRulesMiddleware(AgentMiddleware):
    def __init__(self, rules_dir: Path, cwd: Path, rules: list[dict[str, Any]] | None = None) -> None:
        # Rules are normally preloaded by the async envelope via asyncio.to_thread
        # so the constructor does no blocking IO (LangGraph flags blocking calls
        # in async contexts). The sync default keeps plain packaged apps portable.
        self.rules = load_rules(rules_dir) if rules is None else rules
        self.always_on = [rule for rule in self.rules if not rule["paths"]]
        self.path_scoped = [rule for rule in self.rules if rule["paths"]]
        self.cwd = cwd
        self.injected: dict[str, set[str]] = {}
        self.touched: dict[str, set[str]] = {}

    def _pending(self, thread: str) -> list[dict[str, Any]]:
        injected = self.injected.setdefault(thread, set())
        touched = self.touched.setdefault(thread, set())
        return [
            rule for rule in self.always_on + self.path_scoped
            if rule["name"] not in injected
            and (not rule["paths"] or rule["name"] in touched)
        ]

    def _thread(self, runtime: object) -> str:
        return _thread_key(runtime)

    def _mark_injected(self, thread: str, rules: list[dict[str, Any]]) -> None:
        self.injected.setdefault(thread, set()).update(rule["name"] for rule in rules)
        self.touched.setdefault(thread, set()).update(rule["name"] for rule in rules)

    def _system_update(self, request: ModelRequest, thread: str) -> ModelRequest:
        due = self._pending(thread)
        if not due:
            return request
        self._mark_injected(thread, due)
        text = "\n\n".join(rule_reminder(rule) for rule in due)
        prior = request.system_message.text if request.system_message else ""
        content = f"{prior}\n\n{text}" if prior else text
        return request.override(system_message=SystemMessage(content=content))

    def wrap_model_call(self, request: ModelRequest, handler: Any) -> ModelResponse:
        return handler(self._system_update(request, _thread_key(request.runtime)))

    async def awrap_model_call(self, request: ModelRequest, handler: Any) -> ModelResponse:
        return await handler(self._system_update(request, _thread_key(request.runtime)))

    def _observe_tool(self, request: ToolCallRequest) -> None:
        call = request.tool_call
        if call.get("name") not in TOOL_NAMES:
            return
        raw_path = _tool_path(call.get("args"))
        if not raw_path:
            return
        absolute = Path(raw_path) if os.path.isabs(raw_path) else self.cwd / raw_path
        absolute_path = os.path.normpath(str(absolute))
        due = [rule for rule in self.path_scoped if matches(rule, absolute_path)]
        self.touched.setdefault(_thread_key(request.runtime), set()).update(
            rule["name"] for rule in due
        )

    def wrap_tool_call(self, request: ToolCallRequest, handler: Any) -> Any:
        result = handler(request)
        self._observe_tool(request)
        return result

    async def awrap_tool_call(self, request: ToolCallRequest, handler: Any) -> Any:
        result = await handler(request)
        self._observe_tool(request)
        return result
