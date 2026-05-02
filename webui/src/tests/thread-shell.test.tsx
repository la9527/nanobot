import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { useState } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ThreadShell } from "@/components/thread/ThreadShell";
import { ClientProvider } from "@/providers/ClientProvider";

function makeClient() {
  const errorHandlers = new Set<(err: { kind: string }) => void>();
  const chatHandlers = new Map<string, Set<(ev: import("@/lib/types").InboundEvent) => void>>();
  return {
    status: "open" as const,
    defaultChatId: null as string | null,
    onStatus: () => () => {},
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
    _emitError(err: { kind: string }) {
      for (const h of errorHandlers) h(err);
    },
    _emitChat(chatId: string, ev: import("@/lib/types").InboundEvent) {
      for (const h of chatHandlers.get(chatId) ?? []) h(ev);
    },
    sendMessage: vi.fn(),
    sendSessionMessage: vi.fn(),
    newChat: vi.fn(),
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

describe("ThreadShell", () => {
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

  it("restores in-memory messages when switching away and back to a session", async () => {
    const client = makeClient();
    const onNewChat = vi.fn().mockResolvedValue("chat-a");

    const { rerender } = render(
      wrap(
        client,
        <ThreadShell
          session={session("chat-a")}
          title="Chat chat-a"
          onToggleSidebar={() => {}}
          onGoHome={() => {}}
          onNewChat={onNewChat}
        />,
      ),
    );

    fireEvent.change(screen.getByLabelText("Message input"), {
      target: { value: "persist me across tabs" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Send message" }));

    await waitFor(() =>
      expect(client.sendMessage).toHaveBeenCalledWith(
        "chat-a",
        "persist me across tabs",
        undefined,
      ),
    );
    expect(screen.getByText("persist me across tabs")).toBeInTheDocument();

    await act(async () => {
      rerender(
        wrap(
          client,
          <ThreadShell
            session={session("chat-b")}
            title="Chat chat-b"
            onToggleSidebar={() => {}}
            onGoHome={() => {}}
            onNewChat={onNewChat}
          />,
        ),
      );
    });

    await act(async () => {
      rerender(
        wrap(
          client,
          <ThreadShell
            session={session("chat-a")}
            title="Chat chat-a"
            onToggleSidebar={() => {}}
            onGoHome={() => {}}
            onNewChat={onNewChat}
          />,
        ),
      );
    });

    expect(screen.getByText("persist me across tabs")).toBeInTheDocument();
  });

  it("clears the old thread when the active session is removed", async () => {
    const client = makeClient();
    const onNewChat = vi.fn().mockResolvedValue("chat-a");

    const { rerender } = render(
      wrap(
        client,
        <ThreadShell
          session={session("chat-a")}
          title="Chat chat-a"
          onToggleSidebar={() => {}}
          onGoHome={() => {}}
          onNewChat={onNewChat}
        />,
      ),
    );

    fireEvent.change(screen.getByLabelText("Message input"), {
      target: { value: "delete me cleanly" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Send message" }));

    await waitFor(() =>
      expect(client.sendMessage).toHaveBeenCalledWith(
        "chat-a",
        "delete me cleanly",
        undefined,
      ),
    );
    expect(screen.getByText("delete me cleanly")).toBeInTheDocument();

    await act(async () => {
      rerender(
        wrap(
          client,
          <ThreadShell
            session={null}
            title="nanobot"
            onToggleSidebar={() => {}}
            onGoHome={() => {}}
            onNewChat={onNewChat}
          />,
        ),
      );
    });

    expect(screen.queryByText("delete me cleanly")).not.toBeInTheDocument();
    expect(screen.getByText("Assistant dashboard")).toBeInTheDocument();
    expect(screen.queryByText("Latest assistant update is ready")).not.toBeInTheDocument();

    await waitFor(() => {
      expect(screen.queryByText("delete me cleanly")).not.toBeInTheDocument();
    });
    expect(screen.queryByRole("textbox", { name: "메시지 입력" })).not.toBeInTheDocument();
  });

  it("does not use the thread title as dashboard navigation anymore", async () => {
    const client = makeClient();
    const onGoHome = vi.fn();

    render(
      wrap(
        client,
        <ThreadShell
          session={session("chat-a")}
          title="Chat chat-a"
          onToggleSidebar={() => {}}
          onGoHome={onGoHome}
          onNewChat={vi.fn().mockResolvedValue("chat-a")}
        />,
      ),
    );

    const title = await screen.findByText("Chat chat-a");
    await userEvent.click(title);

    expect(onGoHome).not.toHaveBeenCalled();
  });

  it("does not leak the previous thread when opening a brand-new chat", async () => {
    const client = makeClient();
    const onNewChat = vi.fn().mockResolvedValue("chat-new");
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL) => {
        const url = String(input);
        if (url.includes("websocket%3Achat-a/messages")) {
          return httpJson({
            key: "websocket:chat-a",
            created_at: null,
            updated_at: null,
            messages: [
              { role: "user", content: "old question" },
              { role: "assistant", content: "old answer" },
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

    const { rerender } = render(
      wrap(
        client,
        <ThreadShell
          session={session("chat-a")}
          title="Chat chat-a"
          onToggleSidebar={() => {}}
          onGoHome={() => {}}
          onNewChat={onNewChat}
        />,
      ),
    );

    await waitFor(() => expect(screen.getAllByText("old answer").length).toBeGreaterThan(0));

    await act(async () => {
      rerender(
        wrap(
          client,
          <ThreadShell
            session={session("chat-new")}
            title="Chat chat-new"
            onToggleSidebar={() => {}}
            onGoHome={() => {}}
            onNewChat={onNewChat}
          />,
        ),
      );
    });

    expect(screen.queryAllByText("old answer")).toHaveLength(0);
    await waitFor(() =>
      expect(screen.getByPlaceholderText("What's on your mind?")).toBeInTheDocument(),
    );
    const input = screen.getByPlaceholderText("What's on your mind?");
    expect(input.className).toContain("min-h-[96px]");
    expect(screen.queryAllByText("old answer")).toHaveLength(0);
  });

  it("loads and changes the active model target for the current session", async () => {
    const user = userEvent.setup();
    const client = makeClient();
    const onNewChat = vi.fn().mockResolvedValue("chat-a");
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes("/api/sessions/websocket%3Achat-a/model-target/default/select")) {
        return httpJson({
          key: "websocket:chat-a",
          active_target: "default",
          target: { name: "default", kind: "provider_model", model: "openai/gpt-5.4" },
        });
      }
      if (url.includes("/api/sessions/websocket%3Achat-a/model-target")) {
        return httpJson({
          key: "websocket:chat-a",
          active_target: "smart-router",
          target: { name: "smart-router", kind: "smart_router" },
        });
      }
      return {
        ok: false,
        status: 404,
        json: async () => ({}),
      };
    });
    vi.stubGlobal("fetch", fetchMock);

    render(
      <ClientProvider
        client={client as unknown as import("@/lib/nanobot-client").NanobotClient}
        token="tok"
        modelName="openai/gpt-5.4"
        activeTarget="default"
        modelTargets={[
          { name: "default", kind: "provider_model", model: "openai/gpt-5.4" },
          { name: "smart-router", kind: "smart_router" },
        ]}
      >
        <ThreadShell
          session={session("chat-a")}
          title="Chat chat-a"
          onToggleSidebar={() => {}}
          onGoHome={() => {}}
          onNewChat={onNewChat}
        />
      </ClientProvider>,
    );

    await waitFor(() => {
      expect(screen.getByText("Auto")).toBeInTheDocument();
    });

    await user.click(screen.getByRole("button", { name: "Choose model target" }));
    await user.click(screen.getByRole("menuitemradio", { name: /default/i }));

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        expect.stringContaining("/api/sessions/websocket%3Achat-a/model-target/default/select"),
        expect.any(Object),
      );
    });

    await waitFor(() => {
      expect(screen.getByText("gpt-5.4")).toBeInTheDocument();
    });
  });

  it("surfaces a dismissible banner when the stream reports message_too_big", async () => {
    const client = makeClient();
    const onNewChat = vi.fn().mockResolvedValue("chat-a");

    render(
      wrap(
        client,
        <ThreadShell
          session={session("chat-a")}
          title="Chat chat-a"
          onToggleSidebar={() => {}}
          onGoHome={() => {}}
          onNewChat={onNewChat}
        />,
      ),
    );

    // No banner yet: only appears once the client emits a matching error.
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();

    await act(async () => {
      client._emitError({ kind: "message_too_big" });
    });

    const banner = await screen.findByRole("alert");
    expect(banner).toHaveTextContent("Message rejected");

    fireEvent.click(screen.getByRole("button", { name: "Dismiss" }));

    await waitFor(() => {
      expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    });
  });

  it("clears the stream error banner when the user switches to another chat", async () => {
    const client = makeClient();
    const onNewChat = vi.fn().mockResolvedValue("chat-a");

    const { rerender } = render(
      wrap(
        client,
        <ThreadShell
          session={session("chat-a")}
          title="Chat chat-a"
          onToggleSidebar={() => {}}
          onGoHome={() => {}}
          onNewChat={onNewChat}
        />,
      ),
    );

    await act(async () => {
      client._emitError({ kind: "message_too_big" });
    });
    expect(await screen.findByRole("alert")).toBeInTheDocument();

    // Switch to a different chat. The banner was about the *previous* send
    // in chat-a; it must not leak into chat-b's view.
    await act(async () => {
      rerender(
        wrap(
          client,
          <ThreadShell
            session={session("chat-b")}
            title="Chat chat-b"
            onToggleSidebar={() => {}}
            onGoHome={() => {}}
            onNewChat={onNewChat}
          />,
        ),
      );
    });

    await waitFor(() => {
      expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    });
  });

  it("clears the previous thread immediately while the next session loads", async () => {
    const client = makeClient();
    const onNewChat = vi.fn().mockResolvedValue("chat-b");
    let resolveChatB:
      | ((value: { ok: boolean; status: number; json: () => Promise<unknown> }) => void)
      | null = null;
    vi.stubGlobal(
      "fetch",
      vi.fn((input: RequestInfo | URL) => {
        const url = String(input);
        if (url.includes("websocket%3Achat-a/messages")) {
          return Promise.resolve(
            httpJson({
              key: "websocket:chat-a",
              created_at: null,
              updated_at: null,
              messages: [{ role: "assistant", content: "from chat a" }],
            }),
          );
        }
        if (url.includes("websocket%3Achat-b/messages")) {
          return new Promise((resolve) => {
            resolveChatB = resolve;
          });
        }
        return Promise.resolve({
          ok: false,
          status: 404,
          json: async () => ({}),
        });
      }),
    );

    const { rerender } = render(
      wrap(
        client,
        <ThreadShell
          session={session("chat-a")}
          title="Chat chat-a"
          onToggleSidebar={() => {}}
          onGoHome={() => {}}
          onNewChat={onNewChat}
        />,
      ),
    );

    await waitFor(() => expect(screen.getAllByText("from chat a").length).toBeGreaterThan(0));

    await act(async () => {
      rerender(
        wrap(
          client,
          <ThreadShell
            session={session("chat-b")}
            title="Chat chat-b"
            onToggleSidebar={() => {}}
            onGoHome={() => {}}
            onNewChat={onNewChat}
          />,
        ),
      );
    });

    expect(screen.queryAllByText("from chat a")).toHaveLength(0);
    expect(screen.getByText("Loading conversation…")).toBeInTheDocument();

    await act(async () => {
      resolveChatB?.(
        httpJson({
          key: "websocket:chat-b",
          created_at: null,
          updated_at: null,
          messages: [{ role: "assistant", content: "from chat b" }],
        }),
      );
    });

    await waitFor(() => expect(screen.getAllByText("from chat b").length).toBeGreaterThan(0));
    expect(screen.queryAllByText("from chat a")).toHaveLength(0);
  });

  it("bridges telegram session replies through the websocket transport and refreshes history", async () => {
    const user = userEvent.setup();
    const client = makeClient();
    const onNewChat = vi.fn().mockResolvedValue("chat-a");
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
          onNewChat={onNewChat}
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
      expect(screen.getAllByText("telegram assistant answer").length).toBeGreaterThan(0);
    });
  });

  it("renders remote telegram user turns immediately through websocket mirror events", async () => {
    const client = makeClient();
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
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

    act(() => {
      client._emitChat("telegram:12345", {
        event: "message",
        chat_id: "telegram:12345",
        text: "fresh telegram push",
        kind: "remote_user",
      });
    });

    expect(screen.getByText("fresh telegram push")).toBeInTheDocument();
  });

  it("shows a continuity placeholder for linked external sessions", async () => {
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
            messages: [],
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

    await userEvent.setup().click(await screen.findByRole("button", { name: "Assistant details" }));
    expect(screen.getByText("Linked external session")).toBeInTheDocument();
    expect(screen.getByText(/attached to the current Telegram conversation/i)).toBeInTheDocument();
    expect(screen.getByText("Linked session")).toBeInTheDocument();
  });

  it("keeps the continuity placeholder visible alongside completed status for linked sessions", async () => {
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
            messages: [{ role: "assistant", content: "telegram assistant answer" }],
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

    expect(await screen.findByText("Latest assistant update is ready")).toBeInTheDocument();
    await userEvent.setup().click(screen.getByRole("button", { name: "Assistant details" }));
    expect(screen.getByText("Linked external session")).toBeInTheDocument();
  });

  it("renders linked continuity metadata in the external session summary", async () => {
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
            metadata: {
              continuity: {
                canonical_owner_id: "primary-user",
                channel_kind: "telegram",
                external_identity: "12345",
                trust_level: "linked",
                last_confirmed_at: "2026-04-30T10:00:00",
              },
            },
            messages: [],
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
          session={telegramSession("12345", "telegram:12345", {
            continuity: {
              canonical_owner_id: "primary-user",
              channel_kind: "telegram",
              external_identity: "12345",
              trust_level: "linked",
              last_confirmed_at: "2026-04-30T10:00:00",
            },
          })}
          title="Telegram 12345"
          onToggleSidebar={() => {}}
          onGoHome={() => {}}
          onNewChat={vi.fn().mockResolvedValue("chat-a")}
        />,
      ),
    );

    await userEvent.setup().click(await screen.findByRole("button", { name: "Assistant details" }));
    expect(screen.getByText("Linked external session")).toBeInTheDocument();
    expect(screen.getByText(/owner primary-user/i)).toBeInTheDocument();
    expect(screen.getByText(/Linked identity: 12345\./i)).toBeInTheDocument();
    expect(screen.getByText(/Trust: linked\./i)).toBeInTheDocument();
  });

  it("renders an owner-aware summary block from linked sessions and pending approvals", async () => {
    const client = makeClient();
    const user = userEvent.setup();

    render(
      wrap(
        client,
        <ThreadShell
          session={{
            ...session("chat-a"),
            metadata: {
              continuity: {
                canonical_owner_id: "primary-user",
                channel_kind: "websocket",
                external_identity: "local-webui",
                trust_level: "trusted",
              },
              owner_profile: {
                canonical_owner_id: "primary-user",
                preferred_language: "ko-KR",
                timezone: "Asia/Seoul",
                response_tone: "direct",
                response_length: "balanced",
              },
              memory_correction: {
                actions: [
                  {
                    code: "remember",
                    phrase: "기억해",
                    target: "owner_profile_or_project_memory",
                    store: "USER.md or memory/MEMORY.md",
                  },
                  {
                    code: "forget",
                    phrase: "잊어",
                    target: "owner_profile_or_project_memory",
                    store: "USER.md or memory/MEMORY.md",
                  },
                ],
              },
              task_summary: {
                task_id: "session:websocket:chat-a",
                canonical_owner_id: "primary-user",
                title: "Review the local thread summary",
                status: "completed",
                origin_channel: "websocket",
                origin_session_key: "websocket:chat-a",
                updated_at: "2026-04-30T10:06:00Z",
                next_step_hint: "Review the latest completed update if follow-up is needed.",
              },
            },
          }}
          sessions={[
            {
              ...session("chat-a"),
              metadata: {
                continuity: {
                  canonical_owner_id: "primary-user",
                  channel_kind: "websocket",
                  external_identity: "local-webui",
                  trust_level: "trusted",
                },
                owner_profile: {
                  canonical_owner_id: "primary-user",
                  preferred_language: "ko-KR",
                  timezone: "Asia/Seoul",
                  response_tone: "direct",
                  response_length: "balanced",
                },
                memory_correction: {
                  actions: [
                    {
                      code: "remember",
                      phrase: "기억해",
                      target: "owner_profile_or_project_memory",
                      store: "USER.md or memory/MEMORY.md",
                    },
                    {
                      code: "forget",
                      phrase: "잊어",
                      target: "owner_profile_or_project_memory",
                      store: "USER.md or memory/MEMORY.md",
                    },
                  ],
                },
                task_summary: {
                  task_id: "session:websocket:chat-a",
                  canonical_owner_id: "primary-user",
                  title: "Review the local thread summary",
                  status: "completed",
                  origin_channel: "websocket",
                  origin_session_key: "websocket:chat-a",
                  updated_at: "2026-04-30T10:06:00Z",
                  next_step_hint: "Review the latest completed update if follow-up is needed.",
                },
              },
            },
            {
              ...telegramSession("12345"),
              updatedAt: "2026-04-30T10:05:00Z",
              metadata: {
                continuity: {
                  canonical_owner_id: "primary-user",
                  channel_kind: "telegram",
                  external_identity: "12345",
                  trust_level: "linked",
                },
                approval_summary: {
                  status: "pending",
                  tool_name: "exec",
                  prompt_preview: "Approval required for a high-risk command.",
                },
                task_summary: {
                  task_id: "session:telegram:12345",
                  canonical_owner_id: "primary-user",
                  title: "Approval required for a high-risk command.",
                  status: "waiting-approval",
                  origin_channel: "telegram",
                  origin_session_key: "telegram:12345",
                  updated_at: "2026-04-30T10:05:00Z",
                  next_step_hint: "Review the pending approval request.",
                },
              },
            },
          ]}
          title="Chat chat-a"
          onToggleSidebar={() => {}}
          onGoHome={() => {}}
          onNewChat={vi.fn().mockResolvedValue("chat-a")}
        />,
      ),
    );

    await waitFor(() => {
      expect(screen.getByRole("button", { name: "Assistant details" })).toBeInTheDocument();
    });
    expect(screen.getByText(/Approval pending/i)).toBeInTheDocument();
    expect(screen.getByText(/Linked 1/i)).toBeInTheDocument();
    expect(screen.getAllByText(/Review the pending approval request\./i).length).toBeGreaterThan(0);

    await user.click(screen.getByRole("button", { name: "Assistant details" }));
    expect(screen.getByText("Assistant overview")).toBeInTheDocument();
    expect(screen.getByText("Current task")).toBeInTheDocument();
    expect(screen.getByText("Review the local thread summary")).toBeInTheDocument();
    expect(screen.getByText(/Owner defaults/i)).toBeInTheDocument();
    expect(screen.getByText(/ko-KR · Asia\/Seoul · direct · balanced/i)).toBeInTheDocument();
    expect(screen.getByText("Memory tools")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "기억해" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "잊어" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "기억해" }));
    expect(screen.getByLabelText("Message input")).toHaveValue(
      "기억해\n내용: [기억할 내용]\n현재 task: Review the local thread summary\n저장 위치: memory/MEMORY.md",
    );
  });

  it("renders blocked and recent completion hints in the owner-aware summary", async () => {
    const client = makeClient();

    render(
      wrap(
        client,
        <ThreadShell
          session={session("chat-a")}
          sessions={[
            {
              ...session("chat-a"),
              updatedAt: "2026-04-30T10:07:00Z",
              metadata: {
                continuity: {
                  canonical_owner_id: "primary-user",
                  channel_kind: "websocket",
                  external_identity: "local-webui",
                  trust_level: "trusted",
                },
              },
            },
            {
              ...session("chat-blocked"),
              updatedAt: "2026-04-30T10:06:00Z",
              metadata: {
                continuity: {
                  canonical_owner_id: "primary-user",
                  channel_kind: "websocket",
                  external_identity: "local-webui",
                  trust_level: "trusted",
                },
                pending_user_turn: true,
                runtime_checkpoint: {
                  phase: "awaiting_tools",
                  iteration: 0,
                  model: "smart-router",
                },
                task_summary: {
                  task_id: "session:websocket:chat-blocked",
                  canonical_owner_id: "primary-user",
                  title: "Resume awaiting tools",
                  status: "blocked",
                  origin_channel: "websocket",
                  origin_session_key: "websocket:chat-blocked",
                  updated_at: "2026-04-30T10:06:00Z",
                  next_step_hint: "Reopen the interrupted session and continue the task.",
                },
              },
            },
            {
              ...telegramSession("12345"),
              updatedAt: "2026-04-30T10:05:00Z",
              metadata: {
                continuity: {
                  canonical_owner_id: "primary-user",
                  channel_kind: "telegram",
                  external_identity: "12345",
                  trust_level: "linked",
                },
                task_summary: {
                  task_id: "session:telegram:12345",
                  canonical_owner_id: "primary-user",
                  title: "Telegram session follow-up",
                  status: "completed",
                  origin_channel: "telegram",
                  origin_session_key: "telegram:12345",
                  updated_at: "2026-04-30T10:05:00Z",
                  next_step_hint: "Review the latest completed update if follow-up is needed.",
                },
              },
            },
          ]}
          title="Chat chat-a"
          onToggleSidebar={() => {}}
          onGoHome={() => {}}
          onNewChat={vi.fn().mockResolvedValue("chat-a")}
        />,
      ),
    );

    await waitFor(() => {
      expect(screen.getByText(/^Blocked$/i)).toBeInTheDocument();
    });
    await userEvent.setup().click(screen.getByRole("button", { name: "Assistant details" }));
    expect(screen.getByText(/Recent completion: Telegram updated/i)).toBeInTheDocument();
    expect(
      screen.getByText(/Next step: Reopen the interrupted session and continue the task\./i),
    ).toBeInTheDocument();
  });

  it("renders quiet-hours suppressed proactive state in the owner-aware summary", async () => {
    const client = makeClient();

    render(
      wrap(
        client,
        <ThreadShell
          session={session("chat-a")}
          sessions={[
            {
              ...telegramSession("12345"),
              updatedAt: "2026-05-01T06:00:00Z",
              metadata: {
                continuity: {
                  canonical_owner_id: "primary-user",
                  channel_kind: "telegram",
                  external_identity: "12345",
                  trust_level: "linked",
                },
                proactive_summary: {
                  status: "suppressed",
                  category: "briefing",
                  title: "Morning briefing ready",
                  summary: "오늘 일정 1개와 승인 대기 1개가 있습니다.",
                  target_channel: "telegram",
                  suppressed_reason: "quiet_hours",
                  updated_at: "2026-05-01T06:00:00Z",
                },
              },
            },
          ]}
          title="Chat chat-a"
          onToggleSidebar={() => {}}
          onGoHome={() => {}}
          onNewChat={vi.fn().mockResolvedValue("chat-a")}
        />,
      ),
    );

    await waitFor(() => {
      expect(screen.getByText(/Held 1/i)).toBeInTheDocument();
    });
    await userEvent.setup().click(screen.getByRole("button", { name: "Assistant details" }));
    expect(screen.getByText(/Quiet hours held Morning briefing ready for Telegram/i)).toBeInTheDocument();
    expect(screen.getByText(/Next step: open WebUI to review the held proactive update\./i)).toBeInTheDocument();
  });

  it("refreshes owner defaults after a websocket memory correction reply", async () => {
    const client = makeClient();
    const user = userEvent.setup();

    function Harness() {
      const initialSession = {
        ...session("chat-a"),
        metadata: {
          continuity: {
            canonical_owner_id: "primary-user",
          },
          task_summary: {
            task_id: "session:websocket:chat-a",
            canonical_owner_id: "primary-user",
            title: "Review the local thread summary",
            status: "completed",
            origin_channel: "websocket",
            origin_session_key: "websocket:chat-a",
            updated_at: "2026-04-30T10:06:00Z",
            next_step_hint: "Review the latest completed update if follow-up is needed.",
          },
          owner_profile: {
            canonical_owner_id: "primary-user",
            preferred_language: "ko-KR",
            timezone: "Asia/Seoul",
            response_tone: "direct",
            response_length: "balanced",
          },
          memory_correction: {
            actions: [
              {
                code: "not-default",
                phrase: "이건 기본 선호가 아님",
                target: "owner_profile",
                store: "USER.md",
              },
            ],
          },
        },
      };
      const refreshedSession = {
        ...initialSession,
        metadata: {
          ...initialSession.metadata,
          owner_profile: {
            canonical_owner_id: "primary-user",
            preferred_language: "ko-KR",
            timezone: "Asia/Seoul",
            response_tone: "technical",
            response_length: "balanced",
          },
        },
      };
      const [activeSession, setActiveSession] = useState(initialSession);

      return (
        <ThreadShell
          session={activeSession}
          sessions={[activeSession]}
          title="Chat chat-a"
          onToggleSidebar={() => {}}
          onGoHome={() => {}}
          onNewChat={vi.fn().mockResolvedValue("chat-a")}
          onRefreshSessions={async () => {
            setActiveSession(refreshedSession);
          }}
        />
      );
    }

    render(wrap(client, <Harness />));

    await user.click(screen.getByRole("button", { name: "Assistant details" }));
    expect(screen.getByText(/ko-KR · Asia\/Seoul · direct · balanced/i)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "이건 기본 선호가 아님" }));
    await user.click(screen.getByRole("button", { name: "Send message" }));

    await act(async () => {
      client._emitChat("chat-a", {
        event: "message",
        chat_id: "chat-a",
        text: "USER.md 기본 선호 보정 항목에 추가했어요: 답변 길이는 기본적으로 간결하게 유지",
      });
    });

    await user.click(screen.getByRole("button", { name: "Assistant details" }));
    await waitFor(() => {
      expect(screen.getByText(/ko-KR · Asia\/Seoul · technical · balanced/i)).toBeInTheDocument();
    });
  });

  it("renders the latest mail action result from session metadata in the status block", async () => {
    const client = makeClient();

    render(
      wrap(
        client,
        <ThreadShell
          session={{
            ...session("chat-a"),
            metadata: {
              continuity: {
                canonical_owner_id: "primary-user",
                channel_kind: "websocket",
                external_identity: "local-webui",
                trust_level: "trusted",
              },
              action_result: {
                action_id: "mail-draft-1",
                domain: "mail",
                action: "create_draft",
                status: "completed",
                title: "Draft ready",
                summary: "Draft created for alice@example.com.",
                next_step: "Review the draft before requesting send approval.",
                visibility: {
                  badge: "Draft ready",
                  inline_status: "Mail draft created",
                },
                details: {
                  draft_id: "draft-1",
                  preview: {
                    subject: "Budget follow-up",
                    body_preview: "Sharing the revised budget.",
                    to_recipients: ["alice@example.com"],
                  },
                },
              },
              task_summary: {
                task_id: "session:websocket:chat-a",
                canonical_owner_id: "primary-user",
                title: "Draft ready",
                status: "completed",
                origin_channel: "websocket",
                origin_session_key: "websocket:chat-a",
                updated_at: "2026-05-01T11:00:00Z",
                next_step_hint: "Review the draft before requesting send approval.",
              },
            },
          }}
          sessions={[]}
          title="Chat chat-a"
          onToggleSidebar={() => {}}
          onGoHome={() => {}}
          onNewChat={vi.fn().mockResolvedValue("chat-a")}
        />,
      ),
    );

    await waitFor(() => {
      expect(screen.getByText(/Draft ready/)).toBeInTheDocument();
    });
    expect(screen.getByText(/Draft created for alice@example.com./)).toBeInTheDocument();
    expect(screen.getByText("Mail result")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Details" }));
    expect(screen.getByText(/To:/i)).toBeInTheDocument();
    expect(screen.getByText(/Subject:/i)).toBeInTheDocument();
  });

  it("renders a compact mail thread summary card from action_result details", async () => {
    const client = makeClient();

    render(
      wrap(
        client,
        <ThreadShell
          session={{
            ...session("chat-a"),
            metadata: {
              continuity: {
                canonical_owner_id: "primary-user",
                channel_kind: "websocket",
                external_identity: "local-webui",
                trust_level: "trusted",
              },
              action_result: {
                action_id: "mail-thread-1",
                domain: "mail",
                action: "summarize_threads",
                status: "completed",
                title: "Thread summaries ready",
                summary: "Summaries were generated for 1 threads.",
                details: {
                  threads: [
                    {
                      thread_id: "thread-1",
                      subject: "Budget follow-up",
                      summary: "Alice is waiting for approval before noon.",
                    },
                  ],
                },
              },
              task_summary: {
                task_id: "session:websocket:chat-a",
                canonical_owner_id: "primary-user",
                title: "Thread summaries ready",
                status: "completed",
                origin_channel: "websocket",
                origin_session_key: "websocket:chat-a",
                updated_at: "2026-05-01T11:00:00Z",
                next_step_hint: "Create a reply draft for the thread that needs follow-up.",
              },
            },
          }}
          sessions={[]}
          title="Chat chat-a"
          onToggleSidebar={() => {}}
          onGoHome={() => {}}
          onNewChat={vi.fn().mockResolvedValue("chat-a")}
        />,
      ),
    );

    await waitFor(() => {
      expect(screen.getByText("Mail result")).toBeInTheDocument();
    });
    expect(screen.getByText("Thread summary")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Details" }));
    expect(screen.getByText("Budget follow-up")).toBeInTheDocument();
    expect(screen.getByText("Alice is waiting for approval before noon.")).toBeInTheDocument();
  });

  it("renders approval pending badge for a mail send action result", async () => {
    const client = makeClient();

    render(
      wrap(
        client,
        <ThreadShell
          session={{
            ...session("chat-a"),
            metadata: {
              continuity: {
                canonical_owner_id: "primary-user",
                channel_kind: "websocket",
                external_identity: "local-webui",
                trust_level: "trusted",
              },
              approval_summary: {
                status: "pending",
                tool_name: "mail.send_message",
                prompt_preview: "Approval required before sending this email.",
              },
              action_result: {
                action_id: "mail-send-approval-1",
                domain: "mail",
                action: "send_message",
                status: "waiting_approval",
                title: "Mail send approval required",
                summary: "Approval required before sending 'Budget follow-up' to alice@example.com.",
                next_step: "Approve or deny the pending mail send request.",
                details: {
                  draft_id: "draft-123",
                  preview: {
                    subject: "Budget follow-up",
                    body_preview: "Sharing revised notes",
                    to_recipients: ["alice@example.com"],
                  },
                },
              },
              task_summary: {
                task_id: "session:websocket:chat-a",
                canonical_owner_id: "primary-user",
                title: "Mail send approval required",
                status: "waiting-approval",
                origin_channel: "websocket",
                origin_session_key: "websocket:chat-a",
                updated_at: "2026-05-01T11:00:00Z",
                next_step_hint: "Approve or deny the pending mail send request.",
              },
            },
          }}
          sessions={[]}
          title="Chat chat-a"
          onToggleSidebar={() => {}}
          onGoHome={() => {}}
          onNewChat={vi.fn().mockResolvedValue("chat-a")}
        />,
      ),
    );

    await waitFor(() => {
      expect(screen.getByText("Mail result")).toBeInTheDocument();
    });
    expect(screen.getAllByText("Approval pending").length).toBeGreaterThan(0);
    expect(screen.getByText(/Mail send approval required/)).toBeInTheDocument();
  });

  it("renders dashboard home when no session is active and opens priority items", async () => {
    const client = makeClient();
    const openSession = vi.fn();

    render(
      wrap(
        client,
        <ThreadShell
          session={null}
          sessions={[
            {
              ...telegramSession("12345"),
              updatedAt: "2026-05-01T11:00:00Z",
              metadata: {
                approval_summary: {
                  status: "pending",
                  tool_name: "mail.send_message",
                  prompt_preview: "Approval required before sending this email.",
                },
                task_summary: {
                  task_id: "session:telegram:12345",
                  canonical_owner_id: "primary-user",
                  title: "Mail send approval required",
                  status: "waiting-approval",
                  origin_channel: "telegram",
                  origin_session_key: "telegram:12345",
                  updated_at: "2026-05-01T11:00:00Z",
                  next_step_hint: "Review the pending approval request.",
                },
              },
            },
          ]}
          title="nanobot"
          onToggleSidebar={() => {}}
          onGoHome={() => {}}
          onOpenSession={openSession}
          onNewChat={vi.fn().mockResolvedValue("chat-a")}
        />,
      ),
    );

    expect(await screen.findByText("Assistant dashboard")).toBeInTheDocument();
    expect(screen.getByText(/오늘 바로 처리할 항목/i)).toBeInTheDocument();
    expect(screen.getByText("Priority queue")).toBeInTheDocument();
    expect(screen.queryByRole("textbox", { name: "메시지 입력" })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "승인 열기" }));
    expect(openSession).toHaveBeenCalledWith("telegram:12345");
  });

  it("renders a calendar event preview card from action_result details", async () => {
    const client = makeClient();

    render(
      wrap(
        client,
        <ThreadShell
          session={{
            ...session("chat-a"),
            metadata: {
              continuity: {
                canonical_owner_id: "primary-user",
                channel_kind: "websocket",
                external_identity: "local-webui",
                trust_level: "trusted",
              },
              action_result: {
                action_id: "calendar-create-1",
                domain: "calendar",
                action: "create_event",
                status: "completed",
                title: "Calendar event created",
                summary: "5.2. 15:00부터 5.2. 16:00까지 치과 일정을 생성했습니다.",
                details: {
                  event_id: "event-123",
                  preview: {
                    title: "치과",
                    start_at: "2026-05-02T15:00:00+09:00",
                    end_at: "2026-05-02T16:00:00+09:00",
                    location: "Seoul",
                    description: "정기 검진",
                  },
                },
              },
              task_summary: {
                task_id: "session:websocket:chat-a",
                canonical_owner_id: "primary-user",
                title: "Calendar event created",
                status: "completed",
                origin_channel: "websocket",
                origin_session_key: "websocket:chat-a",
                updated_at: "2026-05-01T11:00:00Z",
                next_step_hint: "Review the latest completed update if follow-up is needed.",
              },
            },
          }}
          sessions={[]}
          title="Chat chat-a"
          onToggleSidebar={() => {}}
          onGoHome={() => {}}
          onNewChat={vi.fn().mockResolvedValue("chat-a")}
        />,
      ),
    );

    await waitFor(() => {
      expect(screen.getByText("Calendar result")).toBeInTheDocument();
    });
    fireEvent.click(screen.getByRole("button", { name: "Details" }));
    expect(screen.getByText(/Title:/i)).toBeInTheDocument();
    expect(screen.getByText(/When:/i)).toBeInTheDocument();
    expect(screen.getByText(/Location:/i)).toBeInTheDocument();
  });

  it("renders conflicting calendar events in the inline result card", async () => {
    const client = makeClient();

    render(
      wrap(
        client,
        <ThreadShell
          session={{
            ...session("chat-a"),
            metadata: {
              action_result: {
                action_id: "calendar-conflicts-1",
                domain: "calendar",
                action: "find_conflicts",
                status: "blocked",
                title: "Conflicts found",
                summary: "The requested slot overlaps with 프로젝트 리뷰.",
                details: {
                  requested_start_at: "2026-05-02T15:00:00+09:00",
                  requested_end_at: "2026-05-02T16:00:00+09:00",
                  reason: "overlap_detected",
                  conflicting_events: [
                    {
                      event_id: "event-1",
                      title: "프로젝트 리뷰",
                      start_at: "2026-05-02T15:00:00+09:00",
                      end_at: "2026-05-02T15:30:00+09:00",
                      location: "회의실 A",
                    },
                  ],
                },
              },
            },
          }}
          sessions={[]}
          title="Chat chat-a"
          onToggleSidebar={() => {}}
          onGoHome={() => {}}
          onNewChat={vi.fn().mockResolvedValue("chat-a")}
        />,
      ),
    );

    await waitFor(() => {
      expect(screen.getByText(/Conflicts found/)).toBeInTheDocument();
    });
    expect(screen.queryByText("회의실 A")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Details" }));
    expect(screen.getByText("프로젝트 리뷰")).toBeInTheDocument();
    expect(screen.getByText("회의실 A")).toBeInTheDocument();
  });

  it("renders calendar pending interaction prompts from session metadata", async () => {
    const client = makeClient();

    render(
      wrap(
        client,
        <ThreadShell
          session={{
            ...session("chat-a"),
            metadata: {
              calendar_pending_interaction: {
                id: "calendar-interaction-1",
                kind: "conflict_review",
                status: "pending",
                question: "Choose how to continue before approval.",
                buttons: [["그래도 생성 승인 요청", "새 시간 다시 입력"], ["취소"]],
              },
            },
          }}
          sessions={[]}
          title="Chat chat-a"
          onToggleSidebar={() => {}}
          onGoHome={() => {}}
          onNewChat={vi.fn().mockResolvedValue("chat-a")}
        />,
      ),
    );

    expect(await screen.findByRole("group", { name: "Question" })).toHaveTextContent(
      "Choose how to continue before approval.",
    );
    fireEvent.click(screen.getByRole("button", { name: "새 시간 다시 입력" }));
    expect(client.sendMessage).toHaveBeenCalledWith("chat-a", "새 시간 다시 입력", undefined);
  });

  it("does not duplicate a failed status block when an action result card is already shown", async () => {
    const client = makeClient();

    render(
      wrap(
        client,
        <ThreadShell
          session={{
            ...session("chat-a"),
            metadata: {
              action_result: {
                action_id: "calendar-conflicts-1",
                domain: "calendar",
                action: "find_conflicts",
                status: "blocked",
                title: "Conflicts found",
                summary: "The requested slot overlaps with 프로젝트 리뷰.",
                details: {
                  requested_start_at: "2026-05-02T15:00:00+09:00",
                  requested_end_at: "2026-05-02T16:00:00+09:00",
                  reason: "overlap_detected",
                },
              },
            },
          }}
          sessions={[]}
          title="Chat chat-a"
          onToggleSidebar={() => {}}
          onGoHome={() => {}}
          onNewChat={vi.fn().mockResolvedValue("chat-a")}
        />,
      ),
    );

    await waitFor(() => {
      expect(screen.getByText("Calendar result")).toBeInTheDocument();
    });
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("renders ask_user options above the composer and sends selected answers", async () => {
    const client = makeClient();
    const onNewChat = vi.fn().mockResolvedValue("chat-a");

    render(
      wrap(
        client,
        <ThreadShell
          session={session("chat-a")}
          title="Chat chat-a"
          onToggleSidebar={() => {}}
          onGoHome={() => {}}
          onNewChat={onNewChat}
        />,
      ),
    );

    await act(async () => {
      client._emitChat("chat-a", {
        event: "message",
        chat_id: "chat-a",
        text: "How should I continue?",
        buttons: [["Short answer", "Detailed answer"]],
      });
    });

    expect(screen.getByRole("group", { name: "Question" })).toHaveTextContent(
      "How should I continue?",
    );

    fireEvent.click(screen.getByRole("button", { name: "Short answer" }));

    expect(client.sendMessage).toHaveBeenCalledWith(
      "chat-a",
      "Short answer",
      undefined,
    );
    await waitFor(() => {
      expect(screen.queryByRole("group", { name: "Question" })).not.toBeInTheDocument();
    });
  });

  it("sends ask_user answers through session_message for linked telegram sessions", async () => {
    const client = makeClient();

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

    await act(async () => {
      await Promise.resolve();
    });

    await act(async () => {
      client._emitChat("telegram:12345", {
        event: "message",
        chat_id: "telegram:12345",
        text: "Choose how to continue before approval.",
        buttons: [["그래도 생성 승인 요청", "새 시간 다시 입력"], ["취소"]],
      });
    });

    await waitFor(() => {
      expect(screen.getByRole("group", { name: "Question" })).toHaveTextContent(
        "Choose how to continue before approval.",
      );
    });

    fireEvent.click(screen.getByRole("button", { name: "그래도 생성 승인 요청" }));

    expect(client.sendSessionMessage).toHaveBeenCalledWith(
      "telegram:12345",
      "그래도 생성 승인 요청",
      undefined,
    );
    expect(client.sendMessage).not.toHaveBeenCalled();
  });

  it("shows waiting approval status for approval messages and header badges", async () => {
    const client = makeClient();

    render(
      wrap(
        client,
        <ThreadShell
          session={session("chat-a")}
          title="Chat chat-a"
          onToggleSidebar={() => {}}
          onGoHome={() => {}}
          onNewChat={vi.fn().mockResolvedValue("chat-a")}
        />,
      ),
    );

    await act(async () => {
      client._emitChat("chat-a", {
        event: "message",
        chat_id: "chat-a",
        text: "Approve sending the report email to finance?",
        kind: "tool_approval",
      });
    });

    expect(screen.getAllByText("Approval pending").length).toBeGreaterThan(0);
    const status = screen.getByRole("status");
    expect(status).toHaveTextContent("Assistant is waiting for confirmation");
    expect(status).toHaveTextContent("Approve sending the report email to finance?");
  });

  it("shows running, completed, and failed assistant status blocks", async () => {
    const client = makeClient();

    render(
      wrap(
        client,
        <ThreadShell
          session={session("chat-a")}
          title="Chat chat-a"
          onToggleSidebar={() => {}}
          onGoHome={() => {}}
          onNewChat={vi.fn().mockResolvedValue("chat-a")}
        />,
      ),
    );

    await act(async () => {
      client._emitChat("chat-a", {
        event: "delta",
        chat_id: "chat-a",
        text: "Working",
      });
    });

    const runningStatus = screen.getByRole("status");
    expect(runningStatus).toHaveTextContent("Assistant is working");
    expect(runningStatus).toHaveTextContent("Streaming the current assistant response.");

    await act(async () => {
      client._emitChat("chat-a", {
        event: "stream_end",
        chat_id: "chat-a",
      });
    });

    const completedStatus = screen.getByRole("status");
    expect(completedStatus).toHaveTextContent("Completed");
    expect(completedStatus).toHaveTextContent("Latest assistant update is ready");
    expect(completedStatus).toHaveTextContent("Working");

    await act(async () => {
      client._emitError({ kind: "message_too_big" });
    });

    const failedStatus = screen.getByRole("alert");
    expect(failedStatus).toHaveTextContent("Failed");
    expect(failedStatus).toHaveTextContent("Message rejected");
    expect(failedStatus).toHaveTextContent("exceeded the upload size limit");
  });
});
