# Nanobot Status Summary (2026-04-23)

## 1. 문서 목적

오늘 반영된 `/model`, `/usage`, streaming footer 동작, Telegram command 처리, 운영 재시작/health 검증 상태를 현재 기준으로 정리한다.

## 2. 현재 상태 요약

- branch: `feature/nanobot-fork-runtime`
- `/model` 기반 named target 선택 흐름이 runtime/plugin 구조와 연결됨
- `/usage off|tokens|full` 가 세션 메타(`response_footer_mode`)와 연결됨
- streaming 채널에서도 footer가 응답 마지막에 붙도록 반영됨
- `/usage tokens` footer는 가독성을 위해 이모지 색상 태그(예: `🔵`, `🟢`)를 사용함
- live Telegram config는 `streaming: true` 상태 유지

## 3. 이번 반영 주요 작업

- model target 계층 추가
  - `nanobot/model_targets.py` 추가
  - config schema에 `agents.defaults.modelSelection` 추가
  - runtime plugin target catalog(`build_model_targets`) 경로 추가
- slash command 확장
  - `/model`, `/usage` built-in command 추가
  - Telegram/Discord command surface 확장
  - Telegram `/cmd@botname` 계열 normalize 반영
- response status/footer 확장
  - `nanobot/response_status.py` 추가
  - non-streaming footer + streaming footer 모두 지원
  - API 응답은 본문 footer 대신 `usage` JSON 유지
- 운영 안정성 보강
  - gateway health port conflict handling 강화
  - Telegram stop 시 `not running` runtime error 완화

## 4. 이번 검증 결과

- focused tests
  - `tests/cli/test_restart_command.py` (usage/footer 관련 선택 실행) 통과
  - `tests/command/test_builtin_usage.py` 통과
- live runtime
  - `stop-nanobot-services.sh` -> `start-nanobot-services.sh` -> health 재확인 수행
  - 재시작 직후 `down`이 잠깐 보일 수 있으나, 대기 후 `gateway/api ok` 확인
  - `http://127.0.0.1:18790/health` = `{"status": "ok"}`
  - `http://127.0.0.1:8900/health` = `{"status": "ok"}`

## 5. 운영 포인트

- streaming 채널 footer는 최종 `stream_end` 직전에 footer delta를 주입하는 방식으로 동작한다.
- Telegram에서 `streaming: true`를 유지해도 `/usage tokens|full` footer가 노출된다.
- 재시작 직후 health check 실패(exit code 7)는 초기 기동 구간에서 재현 가능하며, 짧은 대기 후 재확인이 필요하다.

## 6. 현재 남은 항목

- TODO 기준: 실제 외부 inbound 채널에서 `/model smart-router` end-to-end 재검증 1회 남음

## 7. 결론

현 상태는 "streaming=true 유지 + `/usage` footer 노출" 요구를 만족한다.
코드/테스트/운영 확인이 같은 방향으로 정렬된 상태이며, 다음 작업은 외부 채널 E2E 재검증이다.