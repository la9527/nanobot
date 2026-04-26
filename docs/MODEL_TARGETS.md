# Model Targets and `/model`

이 문서는 Nanobot 의 named model target 구조와 `/model` 명령 사용법을 설명한다.

## 목적

Nanobot 는 기본 단일 `provider + model` 설정만 쓰는 대신, 여러 실행 target 을 이름으로 등록하고 세션별로 전환할 수 있다.

현재 target 종류는 아래 두 가지다.

- `provider_model`: 특정 provider/model 조합을 직접 고정하는 target
- `smart_router`: smart-router runtime plugin 을 통해 local/mini/full 라우팅을 맡기는 target

이 구조 덕분에 아래를 같은 표면에서 다룰 수 있다.

- startup default model
- 특정 remote model
- 특정 local model
- smart-router

## 설정 위치

기본 설정 위치는 `~/.nanobot/config.json` 또는 사용 중인 runtime config 파일이다.

named target 은 `agents.defaults.modelSelection` 아래에 둔다.

```json
{
  "agents": {
    "defaults": {
      "model": "LiquidAI/LFM2-24B-A2B-GGUF:Q4_0",
      "provider": "vllm",
      "modelSelection": {
        "activeTarget": "default",
        "targets": {
          "local-fast": {
            "kind": "provider_model",
            "provider": "vllm",
            "model": "LiquidAI/LFM2-24B-A2B-GGUF:Q4_0",
            "description": "기본 local llama.cpp/vLLM target"
          },
          "remote-mini": {
            "kind": "provider_model",
            "provider": "openrouter",
            "model": "openai/gpt-5.4-mini",
            "description": "짧은 원격 작업용"
          }
        }
      }
    }
  }
}
```

`activeTarget` 은 전역 기본 target 이다. 세션 안에서 `/model` 로 바꾸면 그 세션에만 override 가 저장된다.

## smart-router target

smart-router 는 별도 special case 가 아니라 runtime plugin 이 기여하는 named target 묶음으로 노출된다.

즉 아래 설정이 유효하면 `/model` 목록과 WebUI target picker 에 아래 target 이 자동으로 나타난다.

- `smart-router`: Auto
- `smart-router-local`: Local
- `smart-router-mini`: Mini
- `smart-router-full`: Full

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

이때 동작은 아래와 같다.

- `/model smart-router`: smart-router policy 가 turn 별로 tier 를 자동 선택한다.
- `/model smart-router-local`: local tier 를 시작점으로 실행한다.
- `/model smart-router-mini`: mini tier 를 시작점으로 실행한다.
- `/model smart-router-full`: full tier 를 시작점으로 실행한다.

Local, Mini, Full variant 도 smart-router provider 를 그대로 쓰므로 기존 health/fallback 메타는 유지된다.

## `/model` 사용법

`/model` 명령은 채팅 세션 기준으로 현재 active target 을 보여주고 바꾼다.

### 현재 target 보기

```text
/model
```

### 사용 가능한 target 목록 보기

```text
/model list
```

### 특정 target 선택

```text
/model local-fast
/model remote-mini
/model smart-router
/model smart-router-local
/model smart-router-mini
/model smart-router-full
```

### 세션 override 해제

```text
/model clear
```

`/model clear` 이후에는 다시 startup 기본 target 또는 `activeTarget` 값이 사용된다.

## 우선순위

현재 적용 순서는 아래와 같다.

1. 세션 override (`/model <name>` 로 저장된 값)
2. `agents.defaults.modelSelection.activeTarget`
3. built-in `default`

`default` target 은 현재 startup 기본값을 그대로 따른다.

- startup 기본이 일반 provider/model 이면 `provider_model` target 으로 동작
- startup 기본이 smart-router 기준이면 `smart_router` target 으로 동작

## runtime plugin target catalog

runtime plugin 은 named target catalog 를 기여할 수 있다.

현재 contract 는 `RuntimePlugin.build_model_targets(context)` 이다.

plugin 은 이 callback 에서 `{name: ResolvedModelTarget}` 형태의 dict 를 반환하면 된다.

예시 개념:

```python
def register_plugin() -> RuntimePlugin:
    return RuntimePlugin(
        name="sample",
        build_model_targets=lambda context: {
            "sample-remote": ResolvedModelTarget(
                name="sample-remote",
                kind="provider_model",
                provider="openrouter",
                model="openai/gpt-5.4-mini",
                description="Sample plugin target",
            )
        },
    )
```

이 구조는 smart-router 외에도 provider bundle plugin, deployment alias plugin, 환경별 preset plugin 으로 확장할 수 있다.

## 운영 메모

- user-configured `modelSelection.targets` 는 plugin target 과 같은 이름을 쓰면 그 이름을 override 한다.
- `smart-router` target 이 보인다고 해서 remote fallback 검증이 끝났다는 뜻은 아니다. 실제 fallback 체인은 별도 운영 검증이 필요하다.
- `/status` 는 현재 세션의 effective target 기준으로 model 정보를 보여준다.

## 운영 예시: local direct target + smart-router

아래처럼 두 개를 같이 두면 운영자가 세션별로 direct local 과 smart-router 를 오갈 수 있다.

```json
{
  "agents": {
    "defaults": {
      "model": "LiquidAI/LFM2-24B-A2B-GGUF:Q4_0",
      "provider": "vllm",
      "modelSelection": {
        "activeTarget": "local-llm",
        "targets": {
          "local-llm": {
            "kind": "provider_model",
            "provider": "vllm",
            "model": "LiquidAI/LFM2-24B-A2B-GGUF:Q4_0",
            "description": "Direct local baseline"
          }
        }
      }
    }
  },
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

권장 운영 흐름은 아래와 같다.

- startup default 는 `local-llm` 로 둔다.
- 일반 자동 라우팅 실험은 `/model smart-router` 로 세션 override 를 건다.
- 특정 tier 를 고정 비교할 때는 `/model smart-router-local`, `/model smart-router-mini`, `/model smart-router-full` 중 하나를 쓴다.
- fallback 검증 후에도 direct local 비교가 필요하면 `/model local-llm` 으로 바로 되돌린다.
- 세션 상태 확인은 `/status`, 응답 footer 노출 제어는 `/usage off|tokens|full` 로 맞춘다.