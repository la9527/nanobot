# Runtime Plugin Guide

Build non-channel Nanobot extensions without patching core files every time.

This guide covers the new runtime plugin path used for provider wrappers, routing layers, and future hook-based extensions. If you want to build a chat channel, see [Channel Plugin Guide](./CHANNEL_PLUGIN_GUIDE.md) instead.

## What a Runtime Plugin Is

Nanobot now has two different extension surfaces:

1. **Channel plugins** for Telegram-like integrations that send and receive messages.
2. **Runtime plugins** for internal agent/runtime behavior such as provider wrappers, routing, hooks, and future tool registration.

Runtime plugins are discovered from:

1. `custom-plugins/` inside the source checkout.
2. Python entry points registered under `nanobot.plugins`.

The current in-repo reference plugin is `custom-plugins/smartrouter/`.

## Current Status

The runtime plugin system is still intentionally small, but it is no longer provider-only.

Today a runtime plugin can contribute:

- A provider builder (`build_provider`)
- Agent loop hooks (`build_hooks`)
- Runtime tools (`build_tools`)
- Loop initialization (`initialize`)
- CLI/runtime status rows (`describe_status`)
- A custom enablement check (`is_enabled`)

This is enough to support provider wrappers such as `smartrouter`, runtime-only helper tools, and operational visibility without reopening core integration points every time.

## Directory Layout

Current in-repo layout:

```text
nanobot/
├── custom-plugins/
│   └── smartrouter/
│       ├── __init__.py
│       ├── config.py
│       ├── policy.py
│       └── smart_router_provider.py
├── nanobot/
│   └── plugins/
│       ├── __init__.py
│       ├── registry.py
│       └── types.py
└── tests/
    └── plugins/
        └── test_runtime_plugins.py
```

The `nanobot.plugins` package contains discovery and registry code. Each plugin package exposes a `register_plugin()` function.

## Minimal Plugin Contract

Runtime plugins return a `RuntimePlugin` object.

```python
from nanobot.plugins import RuntimePlugin, RuntimePluginContext


def register_plugin() -> RuntimePlugin:
    return RuntimePlugin(
        name="myplugin",
        description="Example runtime plugin",
        source="custom",
    )
```

Available fields today:

| Field | Meaning |
|------|---------|
| `name` | Stable plugin identifier |
| `description` | Human-readable description for CLI and docs |
| `source` | Where the plugin came from (`custom`, `entry-point`, etc.) |
| `module_name` | Import module name, filled automatically when omitted |
| `build_provider` | Optional factory for a custom provider or provider wrapper |
| `build_hooks` | Optional factory returning `AgentHook` instances |
| `build_tools` | Optional factory returning `Tool` instances to register on the loop |
| `initialize` | Optional runtime callback invoked after the loop and tools are ready |
| `describe_status` | Optional callback returning CLI-visible plugin status |
| `is_enabled` | Optional callback to decide enablement from config |

For provider and hook builders, Nanobot passes `RuntimePluginContext(config, make_base_provider)`.

For tool and init builders, Nanobot passes `RuntimePluginRuntimeContext(config, make_base_provider, loop)`.

## Provider Plugins

Provider-style runtime plugins are the first supported use case.

`build_provider(context)` receives a `RuntimePluginContext`:

```python
from nanobot.plugins import RuntimePlugin, RuntimePluginContext


def _build_provider(context: RuntimePluginContext):
    base = context.make_base_provider(
        context.config,
        model="openai/gpt-5.4-mini",
        provider_name="openrouter",
    )
    return base


def register_plugin() -> RuntimePlugin:
    return RuntimePlugin(
        name="myproviderplugin",
        description="Provider wrapper example",
        build_provider=_build_provider,
    )
```

Use this pattern when your plugin:

- Wraps an existing provider
- Adds routing or fallback behavior
- Switches between multiple providers
- Changes request policy before the actual model call

## Hook Plugins

Hook-style runtime plugins can attach behavior to the `AgentLoop` without changing the loop itself.

```python
from nanobot.agent import AgentHook, AgentHookContext
from nanobot.plugins import RuntimePlugin, RuntimePluginContext


class AuditHook(AgentHook):
    async def before_execute_tools(self, ctx: AgentHookContext) -> None:
        for call in ctx.tool_calls:
            print(f"[audit] {call.name}")


def _build_hooks(context: RuntimePluginContext):
    return [AuditHook()]


def register_plugin() -> RuntimePlugin:
    return RuntimePlugin(
        name="audit-plugin",
        description="Example hook plugin",
        build_hooks=_build_hooks,
    )
```

Hook plugins are a good fit for:

- Audit logging
- Metrics
- Response post-processing
- Turn-level policy checks

## Tool and Init Plugins

Runtime plugins can now register tools directly onto `AgentLoop.tools` and run one-time initialization logic after the loop is constructed.

```python
from nanobot.agent.tools.base import Tool
from nanobot.plugins import RuntimePlugin, RuntimePluginRuntimeContext


class EchoTool(Tool):
    @property
    def name(self) -> str:
        return "echo_runtime"

    @property
    def description(self) -> str:
        return "Echo text for runtime plugin validation"

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {"text": {"type": "string"}},
            "required": ["text"],
        }

    async def execute(self, text: str):
        return text


def _build_tools(context: RuntimePluginRuntimeContext):
    return [EchoTool()]


def _initialize(context: RuntimePluginRuntimeContext) -> None:
    context.loop._runtime_vars["echo_runtime_loaded"] = True


def register_plugin() -> RuntimePlugin:
    return RuntimePlugin(
        name="echo-runtime",
        description="Example runtime tool plugin",
        build_tools=_build_tools,
        initialize=_initialize,
    )
```

Use `build_tools` when the extension is really a runtime concern rather than a channel concern or MCP server.

Use `initialize` for lightweight runtime wiring only. Do not hide expensive network bootstrap or long-running background jobs there.

## Configuration

Nanobot now exposes a generic `plugins` section in the root config:

```json
{
  "plugins": {
    "sample": {
      "enabled": true,
      "mode": "test"
    }
  }
}
```

This section is intentionally permissive. Plugin-specific keys are stored as raw dict values so each runtime plugin can evolve its own settings shape.

`smartrouter` now uses `plugins.smartrouter` as the primary config path. Nanobot still accepts legacy root `smartRouter` / `smart_router` input for compatibility, but it is mirrored into `plugins.smartrouter` and saved back under `plugins`.

Recommended shape:

```json
{
    "plugins": {
        "smartrouter": {
            "enabled": true,
            "local": {
                "provider": "vllm",
                "model": "LiquidAI/LFM2-24B-A2B-GGUF:Q4_0"
            },
            "mini": {
                "provider": "openrouter",
                "model": "openai/gpt-5.4-mini"
            },
            "full": {
                "provider": "openrouter",
                "model": "openai/gpt-5.4"
            }
        }
    }
}
```

## Discovery and CLI

List both channel plugins and runtime plugins with:

```bash
nanobot plugins list
nanobot plugins list --config ~/.nanobot/config.api.json
nanobot plugins status --config ~/.nanobot/config.api.json
```

The command now shows:

- plugin name
- kind (`channel` or `runtime`)
- source (`builtin`, `plugin`, `custom`, `entry-point`)
- config path used for that plugin
- whether the plugin is currently enabled
- a short runtime status detail string

`plugins status` focuses on runtime plugins and is more useful when you are validating a specific instance config.

## Recommended Implementation Plan

If you want to add a new runtime plugin, follow this order:

1. Create a folder under `custom-plugins/<plugin-name>/`.
2. Add a small `register_plugin()` entry point in `__init__.py`.
3. Keep business logic in separate modules rather than inside `__init__.py`.
4. Add focused tests under `tests/plugins/` and feature-specific tests under the relevant area.
5. Validate with `python -m pytest` rather than relying on a stale editable launcher.

## Current Limitations

The runtime plugin system is working, but it is still early-stage.

Known limitations:

- No formal plugin packaging template for `nanobot.plugins` entry points yet.
- No automatic plugin config schema merge into root config docs or onboarding UI.
- No plugin install/uninstall CLI for runtime plugins yet.
- Status reporting is diagnostic only; it does not attempt health probing by itself.
- Existing plugins may still accept legacy dedicated config sections for compatibility.

## Suggested Next Steps

The next useful improvements are:

1. Add a formal entry-point-based packaging example for runtime plugins.
2. Expose runtime plugin settings in onboarding and status views.
3. Add a stable tool-contribution API for runtime plugins.
4. Move more runtime customizations from ad hoc source patches into plugins.