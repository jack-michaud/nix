# Hooks as middleware — verified mapping

> Base: `deepagents_code/hooks/server_middleware.py::ServerHooksMiddleware` — dcode's hook engine is an `AgentMiddleware` subclass overriding `before_model` / `after_model` / `wrap_tool_call`. Declarative `hooks.json` is a JSON-codec transport on top of those same decision points. Re-verify signaturesin `langchain/agents/middleware/types.py` if the package version changed.

## Portability rule

| Layer | Where it works |
|---|---|
| `hooks.json` + subprocess/HTTP handlers | dcode harness only (dynamic, declarative,, loadable via `/reload`) |
| Compiled `AgentMiddleware` + `BaseTool`s | portable: dcode extensions,, plain `create_deep_agent` apps,, this sandbox's AgentCore app |

For behavior that must survive a packaged app: implement hook decisions as `AgentMiddleware`, not as JSON hooks. The dcode extension envelope can register that middleware; a packaged app passes it directly to `create_deep_agent`.

## Events → middleware methods

| Hook event (`hooks/models/domain.py`) | `AgentMiddleware` boundary | Notes |
|---|---|---|
| `SessionStart` | process/app lifecycle — client fires it; the agent graph has no such boundary | In a packaged app, do it at server/request startup |
| `SessionEnd` | process/app lifecycle — client fires it | Do it at teardown in your app |
| `UserPromptSubmit` | process/app lifecycle — client fires it before the turn | Do it at request ingress in your app |
| `PreToolUse` | `wrap_tool_call` / `awrap_tool_call` — inspect `ToolCallRequest` before calling `handler`; return `ToolMessage(...)` (or `Command`) to block | Deny by returning a `ToolMessage` with the same `tool_call_id`. (`server_middleware.py` mirrors this.) |
| `PostToolUse` | `wrap_tool_call` — call `handler(request)`, then observe the returned `ToolMessage` / `Command` | Post hooks run in the same wrapper: after `handler`, before return |
| `PostToolUseFailure` | same `wrap_tool_call` post section,, guarded on exception/error result | Non-`ToolMessage` exceptional returns bowled there |
| `PermissionRequest` | `langchain.agents.middleware.HumanInTheLoopMiddleware`, or your own interrupt inside `wrap_tool_call` | `approval_mode` gates this in dcode; middleware lets you inject your own approval transport |
| `Notification` | no graph boundary — dcode client-side | Middleware can emit notifications from `after_agent` / `after_model` if needed |
| `PreCompact` | app lifecycle (summarization trigger() — or intercept via `before_model` seeing history length | Compact decision lives outside the middleware stack in dcode |
| `Stop` | `after_agent` / `aafter_agent` (main agent only;; dcode sets `emit_stop=False` for subagents so they still wrap tools without firing `Stop` handlers) | The catch-all "agent finished" point |
| `SubagentStart` | `SubAgentMiddleware` callbacks,, or observe an `after_model` where a subagent result returned | Subagent spawns are model tool calls to the `task` tool — `wrap_tool_call` sees them too |
| `SubagentStop` | same as above,, post side | |

## `AgentMiddleware` lifecycle cheat-sheet (`langchain/agents/middleware/types.py`)

| Method | Point | Typical use |
|---|---|---|
| `before_agent` / `abefore_agent` | before the agent turn starts | session bookkeeping |
| `before_model` / `abefore_model` | before each model invoke | inject messages,, rewrite state |
| `wrap_model_call` / `awrap_model_call` | wraps each model call | inject tools (dcode does this for extensions),, rewrite requests,, cache |
| `after_model` / `aafter_model` | after each model response | post-tool-result rewriting (`ServerHooksMiddleware` runs post-hooks here) |
| `wrap_tool_call` / `awrap_tool_call` | wraps each tool call | pre-tool guards,, denial,, audit,, timing,, post-tool observation |
| `after_agent` / `aafter_agent` | agent finished (`Command`/stop returned) | completion hooks,, notifications,, telemetry |

Both sync and async forms exist;implementations must define either form, not both mismatched. Middleware compose in declaration order (first defined = outermost)。

## Minimal guard-hook middleware (portable)

```python
from langchain.agents.middleware import AgentMiddleware
from langchain.agents.middleware.types import ToolCallRequest
from langchain_core.messages import ToolMessage

class GuardHooks(AgentMiddleware):
    BLOCKED = {"rm", "bash"}

    def wrap_tool_call(self, request: ToolCallRequest, handler)):
        name = request.call["name"]
        print(f"TRACE pre  tool={name} args={request.call.get('args')}")
        if name in self.BLOCKED:
            return ToolMessage(
                content=f"Blocked by GuardHooks: {name} is denied.",
                tool_call_id=request.call["id"],
            )
        result = handler(request)
        print(f"TRACE post tool={name} -> {str(result.content)[:120]}")
        return result

# register it from an extension envelope (dcode), or pass to create_deep_agent(middleware=[GuardHooks()]) (packaged app(
```

## dcode hook config (if you do need the declarative transport)

- Sources merge per event (highest precedence first): project `.deepagents/hooks.json` > user `~/.deepagents/hooks.json` > plugin `hooks.json` (`hooks/loading.py`).
- Handlers are JSON-configured commands or HTTP endpoints receiving a Claude-compatible envelope (`hooks/models/wire.py`), with decision protocol per event (allow / deny / stop processing).
- Hooks config is cached at load; picks up changes on `/reload`, session start,, or cwd switch — not watched per-event. (`.deepagents/hooks.json`, user file,, plugin hooks re-read on those boundaries).