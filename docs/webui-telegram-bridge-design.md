# WebUI Telegram Bridge Design

## 문서 목적

이 문서는 현재 Nanobot 구조를 기준으로, WebUI 에서 Telegram 세션을 조회하고 같은 화면에서 답장을 보내며 실제 Telegram 채널에도 반영되는 양방향 브리지 설계안을 정리한다.

이 문서의 목표는 바로 구현에 들어갈 수 있는 최소 변경 구조를 정리하는 것이다.

## 목표

- WebUI 에서 `telegram:*` 세션을 목록으로 보고 선택할 수 있어야 한다.
- 선택한 Telegram 세션의 히스토리를 WebUI 에서 읽을 수 있어야 한다.
- WebUI 에서 입력한 답장을 같은 Telegram 세션으로 보낼 수 있어야 한다.
- 답장은 실제 Telegram 채널로도 나가고, WebUI 에서도 같은 턴 진행을 볼 수 있어야 한다.
- 기존 `websocket:*` WebUI 채팅 UX 는 깨지지 않아야 한다.

## 비목표

- 모든 채널을 한 번에 WebUI 에 노출하는 범용 멀티채널 콘솔 구현
- Telegram 외 Discord, Slack, Lark 까지 동시에 같은 설계로 완성하는 작업
- 최초 단계에서 완전한 실시간 다중 브라우저 동기화 보장

## 현재 구조 요약

현재 코드 기준 동작은 아래와 같다.

- WebUI transport 는 `nanobot/channels/websocket.py` 의 websocket channel 전용이다.
- WebUI 세션 목록 API 는 `websocket:` prefix 세션만 노출한다.
- WebUI history read API 도 `websocket:` 세션만 허용한다.
- 프런트는 `webui/src/hooks/useSessions.ts` 와 `webui/src/components/thread/ThreadShell.tsx` 에서 `websocket:${chatId}` 를 전제로 동작한다.
- 브라우저 입력은 `webui/src/lib/nanobot-client.ts` 가 websocket frame `type=message` 로 전송한다.
- agent loop 와 channel manager 자체는 `InboundMessage.channel`, `chat_id`, `session_key_override` 기반으로 채널 중립적으로 동작한다.
- Telegram 쪽은 topic 이 있는 경우 `telegram:{chat_id}:topic:{message_thread_id}` 형태 session key 를 이미 사용한다.

즉, core loop 와 session manager 는 멀티채널 세션을 다룰 수 있지만, WebUI surface 만 의도적으로 websocket 전용으로 막혀 있다.

## 핵심 설계 판단

양방향 Telegram 브리지는 websocket channel 자체를 Telegram transport 로 바꾸는 방식보다, WebUI 를 Telegram session observer + reply surface 로 확장하는 방식이 더 안전하다.

핵심 이유는 아래와 같다.

- Telegram message delivery 는 이미 channel manager 와 Telegram channel 이 담당하고 있다.
- WebUI 가 해야 할 일은 Telegram session 을 읽고, 같은 session key 로 inbound turn 을 넣고, 진행 상황을 브라우저에 mirror 하는 것이다.
- 기존 websocket 채널은 WebUI transport 로만 남기고, Telegram routing 은 Telegram channel 쪽에 그대로 두는 편이 채널 경계를 덜 깨뜨린다.

## 제안 아키텍처

구조는 아래 3개 층으로 나눈다.

1. session browsing
2. reply injection
3. browser-side mirror streaming

### 1. Session Browsing

WebUI 가 Telegram 세션을 목록과 히스토리에서 볼 수 있게 만든다.

필요 변경:

- `GET /api/sessions` 에 channel filter 또는 scope filter 를 추가한다.
- 기본값은 현재와 동일하게 `websocket` only 로 유지한다.
- WebUI 에서 Telegram inbox 모드가 켜진 경우 `telegram:` 세션도 함께 받는다.
- `GET /api/sessions/{key}/messages` 는 Telegram 세션도 허용한다.

권장 shape:

```json
{
  "sessions": [
    {
      "key": "telegram:-1001234567890:topic:42",
      "channel": "telegram",
      "chat_id": "-1001234567890",
      "preview": "최근 메시지",
      "updated_at": "2026-04-25T10:00:00Z",
      "bridge_capabilities": {
        "read": true,
        "reply": true,
        "stream_mirror": true
      }
    }
  ]
}
```

주의점:

- 프런트에서 session key 는 opaque string 으로 취급한다.
- `telegram:{chat_id}:topic:{thread_id}` 구조를 프런트가 직접 파싱하지 않게 한다.
- 표시용 `channel`, `chat_id`, `thread_id`, `title` 같은 필드는 서버가 분해해서 내려준다.

### 2. Reply Injection

WebUI reply 는 websocket frame `type=message` 를 재사용하지 않고 별도 HTTP API 로 넣는 편이 안전하다.

권장 endpoint:

```text
POST /api/sessions/{key}/reply
```

request body 예시:

```json
{
  "content": "이 답장을 Telegram 으로 보냅니다.",
  "media": []
}
```

server 동작:

1. `key` 를 decode 한다.
2. 허용된 bridged channel 인지 확인한다. 초기 단계는 `telegram` 만 허용한다.
3. session key 로부터 실제 target 을 resolve 한다.
4. `InboundMessage` 를 만든다.
5. `session_key_override=key` 를 그대로 넣는다.
6. `channel="telegram"`, `chat_id=<resolved telegram chat id>` 로 publish 한다.
7. metadata 에 bridge marker 를 넣는다.

권장 metadata:

```json
{
  "_webui_bridge": true,
  "_webui_bridge_client_id": "browser-session-id",
  "message_thread_id": 42,
  "reply_to_message_id": 1234
}
```

이 방식의 장점은 아래와 같다.

- Telegram outbound 는 기존 channel manager 경로를 그대로 사용한다.
- loop 입장에서는 정상 Telegram inbound turn 으로 처리된다.
- session continuity 는 `session_key_override` 로 보장된다.

### 3. Browser-Side Mirror Streaming

reply injection 만 구현하면 Telegram 으로는 답장이 나가지만, WebUI 에서는 새 assistant turn 을 실시간으로 보지 못한다.

이를 위해 WebUI transport 에 observer 개념을 추가한다.

핵심 아이디어:

- 브라우저 websocket connection 은 여전히 `websocket` channel transport 를 사용한다.
- 하지만 chat subscription 대상을 단순 `chat_id` 가 아니라 `session_key` observer 로 확장한다.
- Telegram reply 를 WebUI 에서 시작한 경우, 해당 browser connection 은 `telegram:*` session key observer 로 등록된다.
- agent loop 의 진행 상태와 최종 reply 를 이 observer 에도 mirror 한다.

여기서 필요한 seam 은 아래 둘 중 하나다.

#### 옵션 A. `OutboundMessage` 에 `session_key` 필드 추가

가장 명시적인 방법이다.

```python
@dataclass
class OutboundMessage:
    channel: str
    chat_id: str
    content: str
    session_key: str | None = None
```

장점:

- browser observer 가 정확히 어느 session 을 보는지 알 수 있다.
- Telegram topic 처럼 `chat_id` 만으로는 구분이 안 되는 케이스를 정확히 다룰 수 있다.

단점:

- core event contract 가 바뀐다.

#### 옵션 B. `metadata["session_key"]` 사용

초기 구현은 더 작게 갈 수 있다.

장점:

- event contract 변경 범위가 작다.

단점:

- 장기적으로 metadata freeform 의존이 커진다.

권장 판단:

- 1차 구현은 `metadata["session_key"]` 로 시작 가능
- 구조가 안정되면 `OutboundMessage.session_key` 를 first-class field 로 승격

## WebUI 변경안

프런트는 기존 websocket 전용 가정들을 channel-aware 하게 바꿔야 한다.

### 세션 목록

- `useSessions.ts` 에 session scope 개념 추가
- 예: `scope = "websocket" | "telegram" | "all"`
- Telegram scope 선택 시 `/api/sessions?scope=telegram` 또는 `/api/sessions?channels=websocket,telegram` 호출

### 세션 표시

- sidebar 에 channel badge 추가
- Telegram session 은 `telegram` badge 와 thread badge 를 같이 표시
- `activeTarget` 과 별개로 `channel` 을 명확히 보여준다

### thread shell

- `historyKey` 를 opaque string 으로 유지
- `websocket:${chatId}` 같은 직접 조합 코드를 줄인다
- 새 채팅 생성은 websocket 전용에서만 사용하고, Telegram session 은 기존 row 선택으로만 진입한다

### send path

- 현재 `send()` 는 websocket transport send 로 직결된다
- Telegram session 선택 시 `POST /api/sessions/{key}/reply` 를 사용하도록 분기한다
- optimistic user bubble 은 그대로 가능하다
- assistant turn 은 mirror stream 또는 history refresh 로 반영한다

## 백엔드 변경안

### websocket channel HTTP API

- `/api/sessions` 에 scope/channel filter 추가
- `/api/sessions/{key}/messages` 의 websocket-only 제한 완화
- `/api/sessions/{key}/reply` 추가

### bridge authorization

WebUI 가 Telegram session 을 읽고 쓰는 권한은 명시 opt-in 이어야 한다.

권장 config 예시:

```json
{
  "channels": {
    "websocket": {
      "webuiBridge": {
        "allowRemoteSessions": true,
        "allowedChannels": ["telegram"],
        "readOnly": false
      }
    }
  }
}
```

초기 기본값은 아래처럼 둔다.

- `allowRemoteSessions=false`
- `allowedChannels=[]`
- 즉, 현재 동작이 기본값으로 유지됨

### reply target resolution

session key 를 그대로 parse 해서 Telegram target 을 복원한다.

예:

- `telegram:12345`
- `telegram:-1001234567890:topic:42`

서버는 이 key 로부터 아래를 추출한다.

- channel=`telegram`
- chat_id=`12345` 또는 `-1001234567890`
- optional `message_thread_id=42`

이 값들은 `InboundMessage.metadata` 로 같이 넘긴다.

## 권한 및 보안 고려사항

이 기능은 단순 UX 기능이 아니라 원격 채널 조작 기능이다. 따라서 아래 제약이 필요하다.

1. 기본 비활성

- 기존 WebUI token 만 있다고 Telegram session 을 자동 조회/답장할 수 있으면 안 된다.

2. channel allowlist

- 초기 구현은 `telegram` 만 허용한다.
- 다른 channel 은 별도 opt-in 없이 열지 않는다.

3. read / reply 분리

- 운영자는 먼저 read-only 로 켠 뒤 안정성을 보고 reply 까지 열 수 있어야 한다.

4. audit marker

- WebUI 에서 들어온 Telegram reply 는 metadata 에 `_webui_bridge=true` 를 남겨 로그에서 구분 가능해야 한다.

5. session exposure control

- sidebar 에 모든 Telegram 세션을 무제한으로 노출하지 않고 최근 N개 또는 allowlisted sender/chat 만 보여주는 옵션이 필요할 수 있다.

## 구현 단계 제안

### Phase 1. Read-Only Telegram Inbox

- WebUI session list 에 Telegram rows 노출
- Telegram session history read 허용
- write 는 막음

검증 목표:

- WebUI 에서 Telegram 세션을 선택할 수 있다
- 히스토리가 정상 표시된다

### Phase 2. Non-Streaming Reply Bridge

- `/api/sessions/{key}/reply` 추가
- WebUI 에서 Telegram session reply 가능
- optimistic user bubble + history refresh 기반 assistant 반영

검증 목표:

- WebUI reply 가 실제 Telegram 으로 전송된다
- 세션 파일에 같은 turn 이 정상 기록된다

### Phase 3. Streaming Mirror

- browser observer registry 추가
- Telegram reply 진행 상황을 WebUI 에 stream mirror
- final reply 와 tool traces 를 브라우저에서도 본다

검증 목표:

- WebUI 에서 Telegram reply 진행 상태를 실시간으로 본다
- 실제 Telegram outbound 와 WebUI mirror 가 같은 session 으로 정렬된다

## 권장 최소 구현 범위

가장 현실적인 첫 구현 범위는 Phase 2 까지다.

이유는 아래와 같다.

- 사용자는 실제로 WebUI 에서 Telegram 답장을 보낼 수 있다.
- core routing 변경이 비교적 작다.
- streaming mirror 는 후속 단계로 분리 가능하다.

즉, 첫 배치는 아래 조합을 권장한다.

- Telegram session list/read 허용
- Telegram reply endpoint 추가
- optimistic UI + history revalidation
- streaming mirror 는 다음 단계

## 구현 시 직접 건드릴 가능성이 높은 파일

- `nanobot/channels/websocket.py`
- `nanobot/bus/events.py`
- `nanobot/agent/loop.py`
- `nanobot/channels/telegram.py`
- `webui/src/hooks/useSessions.ts`
- `webui/src/components/thread/ThreadShell.tsx`
- `webui/src/lib/api.ts`
- `webui/src/lib/types.ts`
- `webui/src/components/ChatList.tsx`

## 오픈 질문

구현 전 아래는 확정이 필요하다.

1. WebUI 에서 Telegram 세션은 모두 볼 수 있어야 하는가, 아니면 allowlisted subset 만 볼 수 있어야 하는가?
2. WebUI reply 는 read-only 모드와 별도로 enable flag 를 둬야 하는가?
3. Telegram topic session 을 WebUI 에서 기본 노출할 것인가, 아니면 topic 없는 direct/group chat 만 우선 노출할 것인가?
4. assistant streaming 을 초기 배치에 넣을 것인가, 아니면 polling/history refresh 로 충분한가?

## 결론

현재 Nanobot 구조에서는 WebUI 에서 Telegram 채팅을 직접 실행하는 기능은 구현 가능하다. 다만 지금 WebUI 는 websocket 전용 surface 이므로, 그대로는 지원되지 않는다.

가장 안전한 설계는 아래다.

- WebUI 를 Telegram session browser + reply surface 로 확장
- Telegram outbound 경로는 기존 channel manager 를 그대로 사용
- WebUI 는 별도 reply endpoint 와 observer/mirror seam 으로 붙임

권장 구현 순서는 `Read-Only Inbox -> Reply Bridge -> Streaming Mirror` 이다.