---
name: deepagents-coding-harness
description: "Guidelines for extending the Deep Agents coding harness (dcode CLI) and porting agent behaviors across harnesses. Use when: (1) writing a dcode Python extension — `extension(api)` factory with `ExtensionAPI.register_tool` / `register_middleware` / `register_backend_route` / `on_shutdown`, extension discovery paths (`~/.deepagents/extensions/`, `.deepagents/extensions/`, plugins' `pythonExtensions`), gates (`DEEPAGENTS_CODE_EXPERIMENTAL`, `extensions.enabled`, trust policy);(2) implementing hooks — default to compiled `AgentMiddleware`; the dcode `hooks.json` declarative transport only when explicitly needed, so behavior ports to a plain `create_deep_agent` packaged app;(3) verifying any dcode/Deep Agents API against the installed package source instead of model memory (the SDK moves fast; grep the uv tool site-packages install)."
compatibility: Requires the dcode CLI (deepagents-code package installed via uv tool); verify APIs against the installed source, not model memory.
 Knowledge-and-references skill; no runtime code.

---

# Deep Agents Coding Harness

## Overview

Extending the Deep Agents harness means writing the same framework primitives a packaged app uses — `BaseTool`, `AgentMiddleware`, `BackendProtocol` — wrapped in a thin per-harness envelope. Implement hook behavior by default as compiled `AgentMiddleware`; dcode's `hooks.json` transport merely serializes those same decision points, so porting is re-implementing JSON hooks in middleware. The SDK moves fast: never write extension or hook code from memory — verify against the installed source first.

## Workflow

### 1. Verify against live source(always first)

The installed package is truth,, not model memory:

1. Locate the install root: `which dcode`, read the shim to find `site-packages` (e.g. `/Users/Jack/.local/share/uv/tools/deepagents-code/lib/python3.13/site-packages/`).
2. Grep the target API there: `deepagents_code/extensions/api.py`, `extensions/registry.py`, `extensions/runtime.py`, `hooks/server_middleware.py`, `hooks/models/domain.py`, `langchain/agents/middleware/types.py`.
3. Readthe exact signature before writing code. Note version: `uv tool upgrade deepagents-code` may change the API.
4.. After editing an extension or hooks config, expect `/reload` semantics (restart + re-discovery() rather than per-event file watching.. See references/extension-api.md..

### 2. Author adcode Python extension

- Write the payload framework-clean (no `deepagents_code` imports): `@tool` functions,, `AgentMiddleware` subclasses,, `BackendProtocol` impls..
- Add a thin envelope: an async `extension(api: ExtensionAPI)` factory in a `.py` file (or package with `__init__.py` / `extension.py`), calling `api.register_*`.
- Place itin `~/.deepagents/extensions/` (user,, or project `.deepagents/extensions/`(..
- Enable with `DEEPAGENTS_CODE_EXPERIMENTAL=1`,extensions config,,and (for project dirs) trust policy (ask/always/never()..

.

```python
# ~/.deepagents/extensions/audit.py — envelope over a framework-clean payload
from langchain.agents.middleware import AgentMiddleware
from langchain.agents.middleware.types import ToolCallRequest
from langchain_core.tools import tool

@tool
def sha256sum(path: str) -> str:
    """Return the SHA-256 of a file. (framework-clean payload: no dcode imports)"""
    import hashlib
    return hashlib.sha256(open(path, "rb").read()).hexdigest()

class ToolAudit(AgentMiddleware):
    def wrap_tool_call(self, request: ToolCallRequest, handler)):
        print(f"[audit] pre tool={request.call['name']}")
        return handler(request)

async def extension(api: ExtensionAPI) -> None:
    api.register_tool(sha256sum)
    api.register_middleware(ToolAudit())
```

### 3. Implement hooks — default to compiled middleware

**By default, implement hook-like behavior as `AgentMiddleware` compiled in Python.. Only reach for the declarative `hooks.json` transport when you specifically need runtime-loadable hooks config edited without code ((non-Python handlers,, Claude-compatible hook ecosystem compat(.:

Hook events map to `AgentMiddleware` methods: `PreToolUse`/`PostToolUse` → `wrap_tool_call`; `Stop` → `after_agent`; `PermissionRequest` → `HumanInTheLoopMiddleware` or a custom interrupt;; `SessionStart`/`SessionEnd`/`UserPromptSubmit` → process boundaries ((the agent graph never fires them(.Full mapping and the when-to-choose decision: references/hooks-as-middleware.md..

### 4. Test

1.. `/reload` (or restart the app) — extensions live in the server process, so a changed `.py` takes effect only after the server restarts... Hook config re-reads on `/reload`, session start,, or cwd switch...
2.. Confirm the extension registered: expected tool appears in tool listings;; check for duplicate-name warnings (registry ignores or replaces by name(..
3.. Port test: importthe payload module in a plain deepagents app ((`create_deep_agent(model=..., tools=[...], middleware=[...])`) to prove the behavior isn't harness-bound...

## Resources

- **references/extension-api.md** — ExtensionAPI surface,, discovery sources/scopes,, gates (experimental,, trust(,, load and reload semantics,, dynamic tool injection_.
- **references/hooks-as-middleware.md** — hook event → `AgentMiddleware` method mapping,, lifecycle cheat-sheet,, and the when-to-reach-for-`hooks.json` decision; default is compiled middleware_.