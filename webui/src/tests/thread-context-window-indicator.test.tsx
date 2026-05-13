import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ThreadShell } from "@/components/thread/ThreadShell";
import { setAppLanguage } from "@/i18n";
import { ClientProvider } from "@/providers/ClientProvider";

function makeClient() {
  return {
    status: "open" as const,
    defaultChatId: null as string | null,
    onStatus: () => () => {},
    onChat: () => () => {},
    onError: () => () => {},
    sendMessage: vi.fn(),
    sendSessionMessage: vi.fn(),
    newChat: vi.fn(),
    attach: vi.fn(),
    connect: vi.fn(),
    close: vi.fn(),
    updateUrl: vi.fn(),
  };
}

function wrap(children: ReactNode) {
  return (
    <ClientProvider
      client={makeClient() as unknown as import("@/lib/nanobot-client").NanobotClient}
      token="tok"
      activeTarget="smart-router"
    >
      {children}
    </ClientProvider>
  );
}

describe("ThreadShell context window indicator", () => {
  beforeEach(async () => {
    await setAppLanguage("ko");
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: false,
        status: 404,
        json: async () => ({}),
      }),
    );
  });

  it("renders the context indicator and opens detailed context data", async () => {
    render(
      wrap(
        <ThreadShell
          session={{
            key: "websocket:chat-context",
            channel: "websocket",
            chatId: "chat-context",
            createdAt: "2026-05-13T11:00:00Z",
            updatedAt: "2026-05-13T11:01:00Z",
            preview: "",
            metadata: {
              context_window: {
                max_tokens: 400000,
                used_input_tokens: 69300,
                reserved_output_tokens: 16000,
                available_tokens: 314700,
                usage_ratio: 0.21325,
                status: "healthy",
                source: "estimated",
                active_target: "smart-router",
                resolved_model: "gpt-5.4-mini-2026-03-17",
                updated_at: "2026-05-13T11:01:00Z",
              },
            },
          }}
          title="Chat chat-context"
          onToggleSidebar={() => {}}
          onGoHome={() => {}}
          onNewChat={vi.fn().mockResolvedValue("chat-context")}
        />,
      ),
    );

    expect(await screen.findByRole("button", { name: "컨텍스트 윈도우 세부 정보 열기" })).toBeInTheDocument();
    expect(screen.queryByText("컨텍스트 사용량")).not.toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "컨텍스트 윈도우 세부 정보 열기" }));

    await waitFor(() => expect(screen.getByRole("dialog", { name: "컨텍스트 윈도우" })).toBeInTheDocument());
    const dialog = screen.getByRole("dialog", { name: "컨텍스트 윈도우" });
    expect(within(dialog).getByText("컨텍스트 사용량")).toBeInTheDocument();
    expect(within(dialog).getByText("여유 있음")).toBeInTheDocument();
    expect(within(dialog).getByText("69.3k / 400k")).toBeInTheDocument();
    expect(within(dialog).getByText("응답 예약")).toBeInTheDocument();
    expect(within(dialog).getByText("smart-router")).toBeInTheDocument();
    expect(within(dialog).getByText("gpt-5.4-mini-2026-03-17")).toBeInTheDocument();
    expect(within(dialog).getByText(/\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}/)).toBeInTheDocument();
    expect(within(dialog).queryByText("이 대화에서 현재 컨텍스트가 얼마나 차 있는지와 다음 응답을 위해 남겨 둔 예약분을 함께 보여줍니다.")).not.toBeInTheDocument();
    expect(within(dialog).queryByText("다음 응답을 처리할 여유가 아직 충분합니다. 작업이 급격히 커지지 않는다면 현재 채팅을 계속 사용해도 됩니다.")).not.toBeInTheDocument();
  });

  it("shows an unavailable context indicator when no snapshot exists", async () => {
    render(
      wrap(
        <ThreadShell
          session={{
            key: "websocket:chat-empty-context",
            channel: "websocket",
            chatId: "chat-empty-context",
            createdAt: "2026-05-13T11:00:00Z",
            updatedAt: "2026-05-13T11:01:00Z",
            preview: "",
            metadata: {},
          }}
          title="Chat chat-empty-context"
          onToggleSidebar={() => {}}
          onGoHome={() => {}}
          onNewChat={vi.fn().mockResolvedValue("chat-empty-context")}
        />,
      ),
    );

    expect(await screen.findByRole("button", { name: "컨텍스트 윈도우 세부 정보 열기" })).toBeInTheDocument();
    expect(screen.queryByText("컨텍스트 사용량")).not.toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "컨텍스트 윈도우 세부 정보 열기" }));

    await waitFor(() => expect(screen.getByRole("dialog", { name: "컨텍스트 윈도우" })).toBeInTheDocument());
    const dialog = screen.getByRole("dialog", { name: "컨텍스트 윈도우" });
    expect(within(dialog).getByText("이 채팅에는 아직 저장된 컨텍스트 스냅샷이 없습니다. 대화를 열거나 한 턴을 더 보내면 최신 추정치를 채울 수 있습니다.")).toBeInTheDocument();
  });
});