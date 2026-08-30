# dcode ExtensionAPI — verified reference

> Base: `deepagents_code` v0.1.64.. Re-verify with grep if the package version changed..

> Authoring rule: keep payloads framework-clean (`langchain_core.tools`, `langchain.agents.middleware`, `deepagents.backends`) — only the thin `extension(api)` envelope may import `deepagents_code`. That way the payload drops unchanged into a plain `create_deep_agent` app (see this sandbox `deepagents/app.py`).

## Discovery sources & scopes

| Source | Path | Scope |
|---|---|---|
| User extensions dir | `~/.deepagents/extensions/` (`DEFAULT_CONFIG_PATH.parent/extensions`) | `user` |
| Project extensions dir | `<project-root>/.deepagents/extensions/` | `project` |
| CLI `--extension` paths (one-off) | explicit file or dir | `temporary` |
| Plugins' `pythonExtensions` | bundled paths recorded by plugin discovery | plugin |

Entry shapes (`extensions/discovery.py`):

- any top-level `*.py` file, or
- a directory containing `__init__.py` or `extension.py` (loaded as a package).

The module must define a callable `extension`;the loader requires an async factory (`inspect.iscoroutinefunction`) — verify in `extensions/loader.py`.

## Gates

1. **Env flag**: `DEEPAGENTS_CODE_EXPERIMENTAL=1` (`_env_vars.py`). Extension discovery is skipped entirely unless truthy at startup..
2. **Config**: `[extensions] enabled = true` in user config (default true) — `extensions/settings.py`.
3. **Trust** (project dirs only): `TrustPolicy` ∈ `ask` (default)/ `always` / `never`, configured via `[extensions] trust`; `ask` may show a trust prompt persisted in `~/.deepagents/state/extension_trust.json` (`extensions/trust.py`). `never` always skips project extensions; `always` skips the prompt. CLI flag grants once.

## Factory signature & `ExtensionAPI` surface

`extensions/api.py` — every extension gets its own `ExtensionAPI` instance bound to its source provenance:

| Method / property | Purpose |
|---|---|
| `api.register_tool(tool)` | Expose an LLM-callable `BaseTool` or plain callable (converted via `langchain_core.tools.tool`). Uniquely named — later duplicates (same name, regardless of source) are ignored with a warning (`extensions/registry.py`). |
| `api.register_middleware(mw)` | Install `AgentMiddleware` (class instantiated no-args, or instance). Uniquely named by `name` attr or class name.. |
| `api.register_backend_route(prefix, backend)` | Mount a `BackendProtocol` under a virtual filesystem `prefix` — lowercase, leading+trailing slash (e.g. `/memories/`). Shell execution stays on the default backend and cannot see routed content.. |
| `api.on_shutdown(hook)` | Register a deterministic (sync or async, zero-arg) teardown callback.. |
| `api.cwd` | Working directory for the session (`Path`).. |
| `api.mode` | `ExtensionMode.INTERACTIVE` or `HEADLESS`; `api.has_ui` shorthand.. |
| `api.path` | Entry file for this extension (`Path`).. |

Registration names are `RegisteredUnit.name`; tools by `tool.name`, middleware by `name` attribute or class `__name__`.

## Where registrations go

`agent.py` (interactive graph construction):

1. Extension tools replace same-named built-in tools (extension wins by name).
2. Extension middleware replaces same-named agent middleware (extension wins).
3. `ExtensionRuntimeMiddleware` (`extensions/hosting.py`) is appended last — it dynamically injects the latest extension-tool snapshot into every model call via `wrap_model_call`/`awrap_model_call` (so late registrations constitute without rebuilding the graph).

Extensions load in the server process path (`server_graph.py`);the server runtime factory is cached once-per-process (`server_graph.py`).

## Load & reload semantics

- **No file watcher.** Editing a `.py` mid-session does nothing until the server process rebuilds..
- `/reload` (or `/restart`) re-discovers plugins/skills/hooks/config,, clears model-config caches,, and restarts the owned server subprocess — that reload re-imports extensions fresh (`app.py::_run_reload`, `server_graph.py::load_extensions`).
- Hooks config re-reads on `/reload`, on session start,, and on cwd switch (`hooks/manager.py::reload`; `app.py::_reload_hooks`).
- Extensions are not part of plugin discovery by default — plugin `pythonExtensions` paths feed into the same discovery but plugins re-discover on `/reload` too..

## Minimal factory template

```python
"""~/.deepagents/extensions/demo.py"""
from deepagents_code.extensions.api import ExtensionAPI  # envelope only

async def extension(api: ExtensionAPI) -> None:
    api.register_tool(my_tool)           # framework-clean payload module
    api.register_middleware(MyMiddleware()  # framework-clean payload module
    # api.register_backend_route("/memories/", MyBackend())
    # api.on_shutdown(cleanup)
```

Packaged-app equivalent of the payload (no dcode):

```python
from deepagents import create_deep_agent

agent = create_deep_agent(
    model=model,
    tools=[my_tool],
    middleware=[MyMiddleware()],
    backend=composite_backend,
)
```