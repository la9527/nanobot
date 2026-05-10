import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ThreadShell } from "@/components/thread/ThreadShell";
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

describe("ThreadShell action result placement", () => {
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

  it("renders the latest action result above the scrollable thread viewport", async () => {
    const client = makeClient();

    const { container } = render(
      wrap(
        client,
        <ThreadShell
          session={{
            ...session("chat-a"),
            updatedAt: "2026-05-01T11:00:00Z",
            metadata: {
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
                  },
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

    const actionContext = await screen.findByTestId("thread-action-context");
    const scrollArea = container.querySelector(".overflow-y-auto");

    expect(actionContext).toHaveTextContent("Completed");
    expect(actionContext).toHaveTextContent("Calendar event created. 5.2. 15:00부터 5.2. 16:00까지 치과 일정을 생성했습니다.");
    expect(scrollArea).toBeTruthy();
    expect(scrollArea).not.toContainElement(actionContext);
    expect(screen.queryByRole("button", { name: "Details" })).not.toBeInTheDocument();

    await waitFor(() => {
      expect(screen.getByText(/Calendar event created/)).toBeInTheDocument();
    });
  });

  it("dismisses the pinned action result and clears persisted metadata", async () => {
    const client = makeClient();
    const onRefreshSessions = vi.fn().mockResolvedValue(undefined);

    vi.stubGlobal(
      "fetch",
      vi.fn().mockImplementation(async (input: RequestInfo | URL) => {
        const url = String(input);
        if (url.includes("/action-result/clear")) {
          return {
            ok: true,
            status: 200,
            json: async () => ({ cleared: true }),
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
          session={{
            ...session("chat-dismiss"),
            updatedAt: "2026-05-01T11:00:00Z",
            metadata: {
              action_result: {
                action_id: "calendar-create-denied-1",
                domain: "calendar",
                action: "create_event",
                status: "rejected",
                title: "Calendar create cancelled",
                summary: "The pending calendar create request was cancelled.",
                details: {
                  preview: {
                    title: "치과",
                    start_at: "2026-05-02T15:00:00+09:00",
                    end_at: "2026-05-02T16:00:00+09:00",
                  },
                },
              },
            },
          }}
          sessions={[]}
          title="Chat chat-dismiss"
          onToggleSidebar={() => {}}
          onGoHome={() => {}}
          onNewChat={vi.fn().mockResolvedValue("chat-dismiss")}
          onRefreshSessions={onRefreshSessions}
        />,
      ),
    );

    expect(await screen.findByTestId("thread-action-context")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Dismiss" }));

    await waitFor(() => {
      expect(screen.queryByTestId("thread-action-context")).not.toBeInTheDocument();
    });

    expect(onRefreshSessions).toHaveBeenCalledTimes(1);
    expect(fetch).toHaveBeenCalledWith(
      expect.stringContaining("/api/sessions/websocket%3Achat-dismiss/action-result/clear"),
      expect.objectContaining({
        credentials: "same-origin",
        headers: expect.objectContaining({ Authorization: "Bearer tok" }),
      }),
    );
  });
});