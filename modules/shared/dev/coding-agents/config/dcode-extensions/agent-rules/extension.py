"""dcode envelope for the framework-clean agent-rules middleware."""

import asyncio
from pathlib import Path

from deepagents_code.extensions.api import ExtensionAPI

from .agent_rules import AgentRulesMiddleware, load_rules


async def extension(api: ExtensionAPI) -> None:
    rules_dir = Path.home() / ".agents" / "rules"
    rules = await asyncio.to_thread(load_rules, rules_dir)
    api.register_middleware(AgentRulesMiddleware(rules_dir, api.cwd, rules=rules))
