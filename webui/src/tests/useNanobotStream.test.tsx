import { act, renderHook } from "@testing-library/react";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";

import { useNanobotStream } from "@/hooks/useNanobotStream";
import type { InboundEvent } from "@/lib/types";
import { ClientProvider } from "@/providers/ClientProvider";

const EMPTY_MESSAGES: import("@/lib/types").UIMessage[] = [];

function fakeClient() {
  const handlers = new Map<string, Set<(ev: InboundEvent) => void>>();
  return {
    client: {
      status: "open" as const,
      defaultChatId: null as string | null,
      onStatus: () => () => {},
      onError: () => () => {},
      onChat(chatId: string, h: (ev: InboundEvent) => void) {
        let set = handlers.get(chatId);
        if (!set) {
          set = new Set();
          handlers.set(chatId, set);
        }
        set.add(h);
        return () => set!.delete(h);
      },
      sendMessage: vi.fn(),
      newChat: vi.fn(),
      attach: vi.fn(),
      connect: vi.fn(),
      close: vi.fn(),
      updateUrl: vi.fn(),
    },
    emit(chatId: string, ev: InboundEvent) {
      const set = handlers.get(chatId);
      set?.forEach((h) => h(ev));
    },
  };
}

function wrap(client: ReturnType<typeof fakeClient>["client"]) {
  return function Wrapper({ children }: { children: ReactNode }) {
    return (
      <ClientProvider
        client={client as unknown as import("@/lib/nanobot-client").NanobotClient}
        token="tok"
      >
        {children}
      </ClientProvider>
    );
  };
}

describe("useNanobotStream", () => {
  it("starts in streaming mode when history shows pending tool calls", () => {
    const fake = fakeClient();
    const initialMessages = [{
      id: "m1",
      role: "assistant" as const,
      content: "Using tools",
      createdAt: Date.now(),
    }];
    const { result } = renderHook(
      () => useNanobotStream("chat-p", initialMessages, true),
      {
        wrapper: wrap(fake.client),
      },
    );

    expect(result.current.isStreaming).toBe(true);
  });

  it("collapses consecutive tool_hint frames into one trace row", () => {
    const fake = fakeClient();
    const { result } = renderHook(() => useNanobotStream("chat-t", EMPTY_MESSAGES), {
      wrapper: wrap(fake.client),
    });

    act(() => {
      fake.emit("chat-t", {
        event: "message",
        chat_id: "chat-t",
        text: 'weather("get")',
        kind: "tool_hint",
      });
      fake.emit("chat-t", {
        event: "message",
        chat_id: "chat-t",
        text: 'search "hk weather"',
        kind: "tool_hint",
      });
    });

    expect(result.current.messages).toHaveLength(1);
    expect(result.current.messages[0].kind).toBe("trace");
    expect(result.current.messages[0].role).toBe("tool");
    expect(result.current.messages[0].isStreaming).toBe(true);
    expect(result.current.messages[0].traces).toEqual([
      'weather("get")',
      'search "hk weather"',
    ]);

    act(() => {
      fake.emit("chat-t", {
        event: "message",
        chat_id: "chat-t",
        text: "## Summary",
      });
    });

    expect(result.current.messages).toHaveLength(2);
    expect(result.current.messages[1].role).toBe("assistant");
    expect(result.current.messages[1].kind).toBeUndefined();
  });

  it("keeps tool hints ahead of a streaming assistant reply", () => {
    const fake = fakeClient();
    const { result } = renderHook(() => useNanobotStream("chat-order", EMPTY_MESSAGES), {
      wrapper: wrap(fake.client),
    });

    act(() => {
      fake.emit("chat-order", {
        event: "delta",
        chat_id: "chat-order",
        text: "Thinking...",
      });
      fake.emit("chat-order", {
        event: "message",
        chat_id: "chat-order",
        text: "searching workspace",
        kind: "tool_hint",
      });
    });

    expect(result.current.messages).toHaveLength(2);
    expect(result.current.messages[0]).toMatchObject({
      kind: "trace",
      content: "searching workspace",
    });
    expect(result.current.messages[1]).toMatchObject({
      role: "assistant",
      content: "Thinking...",
    });
  });

  it("marks trace rows complete on turn_end", () => {
    const fake = fakeClient();
    const { result } = renderHook(() => useNanobotStream("chat-turn", EMPTY_MESSAGES), {
      wrapper: wrap(fake.client),
    });

    act(() => {
      fake.emit("chat-turn", {
        event: "message",
        chat_id: "chat-turn",
        text: 'calendar lookup',
        kind: "progress",
      });
    });

    expect(result.current.messages[0]).toMatchObject({
      kind: "trace",
      isStreaming: true,
    });

    act(() => {
      fake.emit("chat-turn", {
        event: "turn_end",
        chat_id: "chat-turn",
      });
    });

    expect(result.current.messages[0]).toMatchObject({
      kind: "trace",
      isStreaming: false,
    });
  });

  it("maps tool_approval frames into approval messages", () => {
    const fake = fakeClient();
    const { result } = renderHook(() => useNanobotStream("chat-a", []), {
      wrapper: wrap(fake.client),
    });

    act(() => {
      fake.emit("chat-a", {
        event: "message",
        chat_id: "chat-a",
        text: "Approval required for a high-risk command.",
        kind: "tool_approval",
      });
    });

    expect(result.current.messages).toHaveLength(1);
    expect(result.current.messages[0]).toMatchObject({
      role: "assistant",
      kind: "approval",
      content: "Approval required for a high-risk command.",
    });
  });

  it("attaches assistant media_urls to complete messages", () => {
    const fake = fakeClient();
    const { result } = renderHook(() => useNanobotStream("chat-m", EMPTY_MESSAGES), {
      wrapper: wrap(fake.client),
    });

    act(() => {
      fake.emit("chat-m", {
        event: "message",
        chat_id: "chat-m",
        text: "video ready",
        media_urls: [{ url: "/api/media/sig/payload", name: "demo.mp4" }],
      });
    });

    expect(result.current.messages).toHaveLength(1);
    expect(result.current.messages[0].media).toEqual([
      { kind: "video", url: "/api/media/sig/payload", name: "demo.mp4" },
    ]);
  });

  it("preserves render_as=text on live assistant messages", () => {
    const fake = fakeClient();
    const { result } = renderHook(() => useNanobotStream("chat-help", EMPTY_MESSAGES), {
      wrapper: wrap(fake.client),
    });

    act(() => {
      fake.emit("chat-help", {
        event: "message",
        chat_id: "chat-help",
        text: "## Help\n/status — Show status\n/help — Show help",
        render_as: "text",
      });
    });

    expect(result.current.messages[0]).toMatchObject({
      role: "assistant",
      renderAs: "text",
      content: "## Help\n/status — Show status\n/help — Show help",
    });
  });

  it("accepts remote_user frames for session-key subscriptions", () => {
    const fake = fakeClient();
    const { result } = renderHook(
      () => useNanobotStream("telegram:12345", [], false),
      { wrapper: wrap(fake.client) },
    );

    act(() => {
      fake.emit("telegram:12345", {
        event: "message",
        chat_id: "telegram:12345",
        text: "hello from telegram",
        kind: "remote_user",
      });
    });

    expect(result.current.messages).toHaveLength(1);
    expect(result.current.messages[0]).toMatchObject({
      role: "user",
      content: "hello from telegram",
    });
  });

  it("suppresses redundant stream confirmation after assistant media", () => {
    const fake = fakeClient();
    const { result } = renderHook(() => useNanobotStream("chat-img-result", EMPTY_MESSAGES), {
      wrapper: wrap(fake.client),
    });

    act(() => {
      fake.emit("chat-img-result", {
        event: "message",
        chat_id: "chat-img-result",
        text: "image ready",
        media_urls: [{ url: "/api/media/sig/image", name: "generated.png" }],
      });
      fake.emit("chat-img-result", {
        event: "message",
        chat_id: "chat-img-result",
        text: "message()",
        kind: "tool_hint",
      });
      fake.emit("chat-img-result", {
        event: "delta",
        chat_id: "chat-img-result",
        text: "发送成功",
      });
      fake.emit("chat-img-result", {
        event: "stream_end",
        chat_id: "chat-img-result",
      });
      fake.emit("chat-img-result", {
        event: "turn_end",
        chat_id: "chat-img-result",
      });
    });

    expect(result.current.messages).toHaveLength(1);
    expect(result.current.messages[0].content).toBe("image ready");
    expect(result.current.messages[0].media).toHaveLength(1);
  });

  it("passes image generation options to the websocket client", () => {
    const fake = fakeClient();
    const { result } = renderHook(() => useNanobotStream("chat-img", EMPTY_MESSAGES), {
      wrapper: wrap(fake.client),
    });

    act(() => {
      result.current.send(
        "draw a square icon",
        undefined,
        { imageGeneration: { enabled: true, aspect_ratio: "1:1" } },
      );
    });

    expect(fake.client.sendMessage).toHaveBeenCalledWith(
      "chat-img",
      "draw a square icon",
      undefined,
      { imageGeneration: { enabled: true, aspect_ratio: "1:1" } },
    );

  });

  it("stops the active turn without adding a user slash command bubble", () => {
    const fake = fakeClient();
    const { result } = renderHook(() => useNanobotStream("chat-stop", EMPTY_MESSAGES), {
      wrapper: wrap(fake.client),
    });

    act(() => {
      result.current.send("long task");
    });
    expect(result.current.messages).toHaveLength(1);
    expect(result.current.isStreaming).toBe(true);

    act(() => {
      result.current.stop();
    });

    expect(fake.client.sendMessage).toHaveBeenLastCalledWith("chat-stop", "/stop");
    expect(result.current.isStreaming).toBe(false);
    expect(result.current.messages).toHaveLength(1);
    expect(result.current.messages[0].content).toBe("long task");
  });

  it("keeps assistant buttons on complete messages", () => {
    const fake = fakeClient();
    const { result } = renderHook(() => useNanobotStream("chat-q", EMPTY_MESSAGES), {
      wrapper: wrap(fake.client),
    });

    act(() => {
      fake.emit("chat-q", {
        event: "message",
        chat_id: "chat-q",
        button_prompt: "How should I continue?",
        text: "How should I continue?",
        buttons: [["Short answer", "Detailed answer"]],
      });
    });

    expect(result.current.messages.at(-1)).toMatchObject({
      role: "assistant",
      content: "How should I continue?",
      buttons: [["Short answer", "Detailed answer"]],
    });
  });

  it("does not append a duplicate complete assistant message when the same text already exists in history", () => {
    const fake = fakeClient();
    const initialMessages = [{
      id: "hist-assistant",
      role: "assistant" as const,
      content: "현재 사용 중인 모델은 `mlx-community/Qwen3.6-35B-A3B-4bit` 입니다.",
      createdAt: Date.now() - 60_000,
    }];
    const { result } = renderHook(
      () => useNanobotStream("telegram:12345", initialMessages, false),
      {
        wrapper: wrap(fake.client),
      },
    );

    act(() => {
      fake.emit("telegram:12345", {
        event: "message",
        chat_id: "telegram:12345",
        text: "현재 사용 중인 모델은 `mlx-community/Qwen3.6-35B-A3B-4bit` 입니다.",
      });
    });

    expect(
      result.current.messages.filter((message) => message.content === "현재 사용 중인 모델은 `mlx-community/Qwen3.6-35B-A3B-4bit` 입니다.").length,
    ).toBe(1);
  });

  it("does not append a second assistant reply when only a streamed status footer differs", () => {
    const fake = fakeClient();
    const initialMessages = [{
      id: "hist-assistant",
      role: "assistant" as const,
      content: "현재 사용 중인 모델은 `mlx-community/Qwen3.6-35B-A3B-4bit` 입니다.",
      createdAt: Date.now() - 60_000,
    }];
    const { result } = renderHook(
      () => useNanobotStream("telegram:12345", initialMessages, false),
      {
        wrapper: wrap(fake.client),
      },
    );

    act(() => {
      fake.emit("telegram:12345", {
        event: "message",
        chat_id: "telegram:12345",
        text: "현재 사용 중인 모델은 `mlx-community/Qwen3.6-35B-A3B-4bit` 입니다.\n\nStatus: model=smart-router-local | tokens=🔵55431 in/🟢47 out",
      });
    });

    expect(result.current.messages).toHaveLength(1);
    expect(result.current.messages[0]?.content).toContain("현재 사용 중인 모델은 `mlx-community/Qwen3.6-35B-A3B-4bit` 입니다.");
    expect(result.current.messages[0]?.content).toContain("Status: model=smart-router-local | tokens=🔵55431 in/🟢47 out");
  });

  it("replaces a historical assistant row when a websocket frame has the same turn_id", () => {
    const fake = fakeClient();
    const initialMessages = [{
      id: "turn-shared-123",
      role: "assistant" as const,
      content: "older persisted answer",
      createdAt: Date.now() - 60_000,
    }];
    const { result } = renderHook(
      () => useNanobotStream("telegram:12345", initialMessages, false),
      {
        wrapper: wrap(fake.client),
      },
    );

    act(() => {
      fake.emit("telegram:12345", {
        event: "message",
        chat_id: "telegram:12345",
        turn_id: "turn-shared-123",
        text: "final live answer\n\nStatus: model=smart-router-local | tokens=🔵12 in/🟢4 out",
      } as InboundEvent);
    });

    expect(result.current.messages).toHaveLength(1);
    expect(result.current.messages[0]).toMatchObject({
      id: "turn-shared-123",
      role: "assistant",
      content: "final live answer\n\nStatus: model=smart-router-local | tokens=🔵12 in/🟢4 out",
    });
  });

  it("keeps streaming state until turn_end", () => {
    const fake = fakeClient();
    const onTurnEnd = vi.fn();
    const { result } = renderHook(() => useNanobotStream("chat-s", EMPTY_MESSAGES, false, onTurnEnd), {
      wrapper: wrap(fake.client),
    });

    act(() => {
      fake.emit("chat-s", {
        event: "delta",
        chat_id: "chat-s",
        text: "Hello world",
      });
    });

    expect(result.current.isStreaming).toBe(true);
    expect(result.current.messages.at(-1)).toMatchObject({
      role: "assistant",
      content: "Hello world",
    });

    act(() => {
      fake.emit("chat-s", {
        event: "turn_end",
        chat_id: "chat-s",
      });
    });

    expect(result.current.isStreaming).toBe(false);
    expect(result.current.messages.every((message) => !message.isStreaming)).toBe(true);
    expect(onTurnEnd).toHaveBeenCalledTimes(1);
  });

  it("does not keep both the streamed placeholder and final assistant message", () => {
    const fake = fakeClient();
    const { result } = renderHook(() => useNanobotStream("chat-final", EMPTY_MESSAGES), {
      wrapper: wrap(fake.client),
    });

    act(() => {
      fake.emit("chat-final", {
        event: "delta",
        chat_id: "chat-final",
        text: "Final reply",
      });
      fake.emit("chat-final", {
        event: "stream_end",
        chat_id: "chat-final",
      });
      fake.emit("chat-final", {
        event: "message",
        chat_id: "chat-final",
        text: "Final reply",
      });
      fake.emit("chat-final", {
        event: "turn_end",
        chat_id: "chat-final",
      });
    });

    expect(result.current.messages).toHaveLength(1);
    expect(result.current.messages[0]).toMatchObject({
      role: "assistant",
      content: "Final reply",
    });
  });

  it("refreshes session metadata when the server reports a session update", () => {
    const fake = fakeClient();
    const onTurnEnd = vi.fn();
    renderHook(() => useNanobotStream("chat-title", EMPTY_MESSAGES, false, onTurnEnd), {
      wrapper: wrap(fake.client),
    });

    act(() => {
      fake.emit("chat-title", {
        event: "session_updated",
        chat_id: "chat-title",
      });
    });

    expect(onTurnEnd).toHaveBeenCalledTimes(1);
  });
});
