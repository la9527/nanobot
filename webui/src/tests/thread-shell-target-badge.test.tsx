import { render, screen } from "@testing-library/react";
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
      activeTarget="smart-router-mini"
    >
      {children}
    </ClientProvider>
  );
}

function session(chatId: string) {
  return {
    key: `websocket:${chatId}`,
    channel: "websocket" as const,
    chatId,
    createdAt: null,
    updatedAt: null,
    preview: "",
  };
}

describe("ThreadShell target badge i18n", () => {
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

  it("renders the smart-router target badge with a localized Korean label", async () => {
    render(
      wrap(
        <ThreadShell
          session={session("chat-target")}
          sessions={[]}
          title="Chat chat-target"
          onToggleSidebar={() => {}}
          onGoHome={() => {}}
          onNewChat={vi.fn().mockResolvedValue("chat-target")}
        />,
      ),
    );

    expect(await screen.findByText("타깃 미니")).toBeInTheDocument();
  });

  it("prefers the smart-router alias over the resolved model leaf when available", async () => {
    render(
      <ClientProvider
        client={makeClient() as unknown as import("@/lib/nanobot-client").NanobotClient}
        token="tok"
        activeTarget="smart-router-mini"
        modelName="openai/gpt-5.4-mini-2026-03-17"
      >
        <ThreadShell
          session={session("chat-target-model")}
          sessions={[]}
          title="Chat chat-target-model"
          onToggleSidebar={() => {}}
          onGoHome={() => {}}
          onNewChat={vi.fn().mockResolvedValue("chat-target-model")}
        />
      </ClientProvider>,
    );

    expect(await screen.findByText("타깃 미니")).toBeInTheDocument();
    expect(screen.queryByText("타깃 gpt-5.4-mini-2026-03-17")).not.toBeInTheDocument();
  });
});