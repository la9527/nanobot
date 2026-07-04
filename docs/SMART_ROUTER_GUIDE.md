# Smart Router Guide

`smartrouter` is the first real runtime plugin built on top of Nanobot's new runtime plugin registry.

It routes a request across three tiers:

- `local`
- `mini`
- `full`

The goal is to keep simple requests on a local model while still allowing safe fallback and higher-capability models for more complex requests.

## Current Role in the Architecture

The smart router is not a channel plugin. It is a runtime plugin that contributes a provider wrapper.

Current flow:

1. `Config.plugins.smartrouter.enabled` turns the feature on.
2. `nanobot.nanobot._make_provider()` loads the `smartrouter` runtime plugin.
3. The plugin builds a `SmartRouterProvider`.
4. The router chooses `local`, `mini`, or `full` per request.
5. If needed, it falls back to another tier using health-aware retry rules.

Legacy root `smartRouter` / `smart_router` config is still accepted, but Nanobot now treats `plugins.smartrouter` as the primary path.

Implementation lives in:

- `custom-plugins/smartrouter/`
- `nanobot/plugins/`
- `nanobot/nanobot.py`

## Directory Layout

```text
custom-plugins/smartrouter/
├── __init__.py                # runtime plugin registration
├── config.py                  # config conversion into router dataclasses
├── fallback.py                # fallback ordering
├── health.py                  # failure tracking and cooldown
├── logging.py                 # JSONL routing logs
├── policy.py                  # rule-based routing policy
├── smart_router_provider.py   # provider wrapper
└── types.py                   # shared router types
```

## Routing Model

The current router is intentionally simple.

It uses rule-based scoring rather than an LLM classifier or semantic router.

Current inputs include:

- prompt length
- code-like keywords
- reasoning keywords
- tool-like keywords
- attachments and message history signals

Current outputs include:

- requested tier
- fallback attempts
- optional JSONL log entries

This is a deliberate first version. The priority is deterministic behavior and easy debugging, not maximum routing sophistication.

## Example Configuration

```json
{
  "agents": {
    "defaults": {
      "provider": "vllm",
      "model": "LiquidAI/LFM2-24B-A2B-GGUF:Q4_0"
    }
  },
  "providers": {
    "vllm": {
      "apiBase": "http://127.0.0.1:1242/v1"
    },
    "openrouter": {
      "apiKey": "sk-or-..."
    }
  },
  "plugins": {
    "smartrouter": {
      "enabled": true,
      "allowLocalTools": false,
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
      },
      "logging": {
        "enabled": true,
        "path": "~/.nanobot/logs/smart-router.jsonl"
      }
    }
  }
}
```

## Important Behavior

### 1. API Runtime Context Is Ignored for Scoring

Nanobot's API channel injects runtime metadata into the synthetic user message stream.

The smart router explicitly strips the `[Runtime Context ...]` metadata block before scoring so that request routing is based on the user prompt rather than internal transport metadata.

This avoids false promotion to `mini` or `full` for simple API requests.

### 2. Local Tool History Is Flattened for Local OpenAI-Compatible Providers

The router depends on the local provider compatibility fixes in `nanobot/providers/openai_compat_provider.py`.

Completed tool-call history is flattened for local-compatible providers so llama.cpp-style backends do not choke on replayed structured tool-call history.

### 3. Fallback Is Health-Aware

Tier failures are not treated equally forever.

The router tracks failures and cooldown windows so obviously unhealthy paths stop being retried immediately on every turn.

## Logging

When enabled, the router writes JSONL decision logs.

These logs are meant for:

- route debugging
- policy tuning
- fallback analysis
- comparing local vs remote behavior over time

The current JSONL payload includes:

- `requestModel`
- `requestedTier`
- `finalTier`
- `score`
- `reasonCodes`
- `features`
- `attempts`

Each `attempts` entry captures the tier, model, provider, status, and error text if a fallback happened.

## Operational Validation Workflow

Use this sequence when validating a source checkout against a real Nanobot instance config.

### 1. Confirm the plugin is visible

```bash
PYTHONPATH=/path/to/nanobot/source \
  /path/to/nanobot/source/.venv/bin/python -m nanobot.cli.commands \
  plugins list --config ~/.nanobot/config.api.json

PYTHONPATH=/path/to/nanobot/source \
  /path/to/nanobot/source/.venv/bin/python -m nanobot.cli.commands \
  plugins status --config ~/.nanobot/config.api.json
```

You should see `smartrouter` reported as a `runtime` plugin with config path `plugins.smartrouter`.

### 2. Start the API server from the source tree

If you run the source venv from outside the source checkout, set `PYTHONPATH` explicitly so the CLI imports the edited source tree and not another installation.

```bash
set -a && source ~/.nanobot/nanobot.env && set +a
PYTHONPATH=/path/to/nanobot/source \
  /path/to/nanobot/source/.venv/bin/python -m nanobot.cli.commands serve \
  --config ~/.nanobot/config.api.json \
  --host 127.0.0.1 \
  --port 8911
```

### 3. Check health and a real completion

```bash
curl -s http://127.0.0.1:8911/health

curl -s http://127.0.0.1:8911/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{
    "model": "LiquidAI/LFM2-24B-A2B-GGUF:Q4_0",
    "messages": [
      {"role": "user", "content": "Reply with exactly SMART_ROUTER_PLUGIN_OK"}
    ]
  }'
```

### 4. Inspect the JSONL log

```bash
tail -n 5 ~/.nanobot/logs/smart-router.jsonl
```

Example fields to confirm:

- `requestedTier`
- `finalTier`
- `reasonCodes`
- `attempts[].status`

In the validated source-tree run used during implementation, the router emitted a JSONL row with both `requestedTier` and `finalTier` populated and the API completion returned the exact expected string.

## Validation Checklist

Recommended validation flow:

```bash
python -m pytest tests/providers/test_smart_router_provider.py \
  tests/test_nanobot_facade.py \
  tests/config/test_smart_router_config.py \
  tests/providers/test_litellm_kwargs.py
```

For runtime path validation, use the installed `nanobot` path and not only a source-local venv shortcut.

If you are invoking the source venv from outside the source directory, prefer an explicit `PYTHONPATH=/path/to/source` prefix.

## Current Limitations

The smart router is working, but several constraints are still deliberate:

- Routing policy is rule-based only.
- No UI/editor flow exists yet for tuning smart-router thresholds.
- No packaging example exists yet for shipping it as an external `nanobot.plugins` package.
- Full `local -> mini -> full` operational validation still depends on remote credentials being available in the target instance.

## Recommended Next Steps

1. Add richer observability around route decisions and fallback reasons.
2. Add a packaging example for external runtime plugins.
3. Add long-session and real-traffic regression coverage for route stability.
4. Add a dedicated fallback validation runbook for environments with real remote credentials.