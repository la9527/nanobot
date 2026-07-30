import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ThreadShell } from "@/components/thread/ThreadShell";
import { ClientProvider } from "@/providers/ClientProvider";

function makeClient() {
  const errorHandlers = new Set<(err: { kind: string }) => void>();
  const chatHandlers = new Map<string, Set<(ev: import("@/lib/types").InboundEvent) => void>>();
  const sessionUpdateHandlers = new Set<(chatId: string, scope?: string) => void>();
  const goalStateByChatId = new Map<string, import("@/lib/types").GoalStateWsPayload>();
  return {
    status: "open" as const,
    defaultChatId: null as string | null,
    onStatus: () => () => {},
    onRuntimeModelUpdate: () => () => {},
    getRunStartedAt: () => null,
    getGoalState: (chatId: string) => goalStateByChatId.get(chatId),
    onChat: (chatId: string, handler: (ev: import("@/lib/types").InboundEvent) => void) => {
      let handlers = chatHandlers.get(chatId);
      if (!handlers) {
        handlers = new Set();
        chatHandlers.set(chatId, handlers);
      }
      handlers.add(handler);
      return () => {
        handlers?.delete(handler);
      };
    },
    onError: (handler: (err: { kind: string }) => void) => {
      errorHandlers.add(handler);
      return () => {
        errorHandlers.delete(handler);
      };
    },
    onSessionUpdate: (handler: (chatId: string, scope?: string) => void) => {
      sessionUpdateHandlers.add(handler);
      return () => {
        sessionUpdateHandlers.delete(handler);
      };
    },
    _emitError(err: { kind: string }) {
      for (const h of errorHandlers) h(err);
    },
    _emitChat(chatId: string, ev: import("@/lib/types").InboundEvent) {
      if (ev.event === "goal_state") {
        goalStateByChatId.set(chatId, ev.goal_state);
      }
      for (const h of chatHandlers.get(chatId) ?? []) h(ev);
    },
    _emitSessionUpdate(chatId: string, scope?: string) {
      for (const h of sessionUpdateHandlers) h(chatId, scope);
    },
    sendMessage: vi.fn(),
    sendSessionMessage: vi.fn(),
    newChat: vi.fn(),
    forkChat: vi.fn(),
    attach: vi.fn(),
    connect: vi.fn(),
    close: vi.fn(),
    updateUrl: vi.fn(),
  };
}

function wrap(client: ReturnType<typeof makeClient>, children: ReactNode) {
  return (
    <ClientProvider
      client={client as unknown as import("@/lib/nanobot-client").NanobotClient}
      token="tok"
    >
      {children}
    </ClientProvider>
  );
}

function telegramSession(
  chatId: string,
  key: string = `telegram:${chatId}`,
  metadata?: import("@/lib/types").ChatSummary["metadata"],
) {
  return {
    key,
    channel: "telegram" as const,
    chatId,
    createdAt: null,
    updatedAt: null,
    preview: "telegram thread",
    metadata,
  };
}

function httpJson(body: unknown) {
  return {
    ok: true,
    status: 200,
    json: async () => body,
  };
}

describe("ThreadShell linked sessions", () => {
  beforeEach(() => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: false,
        status: 404,
        json: async () => ({}),
      }),
    );
  });

  it("bridges telegram session replies through the websocket transport and refreshes history", async () => {
    const user = userEvent.setup();
    const client = makeClient();
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes("telegram%3A12345/messages")) {
        const callCount = fetchMock.mock.calls.filter(([value]) =>
          String(value).includes("telegram%3A12345/messages"),
        ).length;
        if (callCount < 2) {
          return httpJson({
            key: "telegram:12345",
            created_at: null,
            updated_at: null,
            messages: [{ role: "user", content: "older telegram user turn" }],
          });
        }
        return httpJson({
          key: "telegram:12345",
          created_at: null,
          updated_at: null,
          messages: [
            { role: "user", content: "older telegram user turn" },
            { role: "user", content: "reply from webui" },
            { role: "assistant", content: "telegram assistant answer" },
          ],
        });
      }
      if (url.includes("telegram%3A12345/model-target")) {
        return {
          ok: false,
          status: 404,
          json: async () => ({}),
        };
      }
      return {
        ok: false,
        status: 404,
        json: async () => ({}),
      };
    });
    vi.stubGlobal("fetch", fetchMock);

    render(
      wrap(
        client,
        <ThreadShell
          session={telegramSession("12345")}
          title="Telegram 12345"
          onToggleSidebar={() => {}}
          onGoHome={() => {}}
          onNewChat={vi.fn().mockResolvedValue("chat-a")}
        />,
      ),
    );

    await waitFor(() => expect(screen.getByText("older telegram user turn")).toBeInTheDocument());

    await user.type(screen.getByLabelText("Message input"), "reply from webui");
    await user.keyboard("{Enter}");

    await waitFor(() => {
      expect(client.sendSessionMessage).toHaveBeenCalledWith(
        "telegram:12345",
        "reply from webui",
        undefined,
      );
    });
    await waitFor(() => {
      expect(screen.getAllByText("telegram assistant answer")).toHaveLength(1);
    });
  });

  it("clears the linked-session waiting placeholder when a telegram reply arrives live", async () => {
    const user = userEvent.setup();
    const client = makeClient();
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL) => {
        const url = String(input);
        if (url.includes("telegram%3A12345/messages")) {
          return httpJson({
            key: "telegram:12345",
            created_at: null,
            updated_at: null,
            messages: [{ role: "user", content: "older telegram user turn" }],
          });
        }
        if (url.includes("telegram%3A12345/model-target")) {
          return {
            ok: false,
            status: 404,
            json: async () => ({}),
          };
        }
        return {
          ok: false,
          status: 404,
          json: async () => ({}),
        };
      }),
    );

    render(
      wrap(
        client,
        <ThreadShell
          session={telegramSession("12345")}
          title="Telegram 12345"
          onToggleSidebar={() => {}}
          onGoHome={() => {}}
          onNewChat={vi.fn().mockResolvedValue("chat-a")}
        />,
      ),
    );

    await waitFor(() => expect(screen.getByText("older telegram user turn")).toBeInTheDocument());

    await user.type(screen.getByLabelText("Message input"), "/status");
    await user.keyboard("{Enter}");

    await waitFor(() => {
      expect(client.sendSessionMessage).toHaveBeenCalledWith(
        "telegram:12345",
        "/status",
        undefined,
      );
    });

    expect(screen.getByText("Waiting for the linked external session to return a reply.")).toBeInTheDocument();

    act(() => {
      client._emitChat("telegram:12345", {
        event: "message",
        chat_id: "telegram:12345",
        text: "Target: smart-router",
      });
    });

    await waitFor(() => {
      expect(screen.getByText("Target: smart-router")).toBeInTheDocument();
      expect(screen.queryByText("Waiting for the linked external session to return a reply.")).not.toBeInTheDocument();
    });
  });

  it("does not duplicate a telegram assistant reply when the same reply already exists in history", async () => {
    const client = makeClient();
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL) => {
        const url = String(input);
        if (url.includes("telegram%3A12345/messages")) {
          return httpJson({
            key: "telegram:12345",
            created_at: null,
            updated_at: null,
            messages: [
              { role: "user", content: "older telegram user turn" },
              { role: "assistant", content: "telegram assistant answer" },
            ],
          });
        }
        return {
          ok: false,
          status: 404,
          json: async () => ({}),
        };
      }),
    );

    render(
      wrap(
        client,
        <ThreadShell
          session={telegramSession("12345")}
          title="Telegram 12345"
          onToggleSidebar={() => {}}
          onGoHome={() => {}}
          onNewChat={vi.fn().mockResolvedValue("chat-a")}
        />,
      ),
    );

    await waitFor(() => expect(screen.getAllByText("telegram assistant answer")).toHaveLength(1));

    act(() => {
      client._emitChat("telegram:12345", {
        event: "message",
        chat_id: "telegram:12345",
        text: "telegram assistant answer",
      });
    });

    await waitFor(() => {
      expect(screen.getAllByText("telegram assistant answer")).toHaveLength(1);
    });
  });
});
