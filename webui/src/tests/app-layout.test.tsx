import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { ChatSummary } from "@/lib/types";
import { fetchBootstrap } from "@/lib/bootstrap";
import { NanobotClient } from "@/lib/nanobot-client";

const connectSpy = vi.fn();
const refreshSpy = vi.fn();
const createChatSpy = vi.fn().mockResolvedValue("chat-1");
const deleteChatSpy = vi.fn();
const toggleThemeSpy = vi.fn();
let mockSessions: ChatSummary[] = [];
const mockClientInstances: Array<{ onReauth?: () => Promise<string | null> }> = [];

vi.mock("@/hooks/useSessions", async (importOriginal) => {
  const React = await import("react");
  const actual = await importOriginal<typeof import("@/hooks/useSessions")>();
  return {
    ...actual,
    useSessions: () => {
      const [sessions, setSessions] = React.useState(mockSessions);
      return {
        sessions,
        loading: false,
        error: null,
        refresh: refreshSpy,
        createChat: createChatSpy,
        deleteChat: async (key: string) => {
          await deleteChatSpy(key);
          setSessions((prev: ChatSummary[]) => prev.filter((s) => s.key !== key));
        },
      };
    },
  };
});

vi.mock("@/hooks/useTheme", () => ({
  useTheme: () => ({
    theme: "light" as const,
    toggle: toggleThemeSpy,
  }),
}));

vi.mock("@/lib/bootstrap", () => ({
  fetchBootstrap: vi.fn().mockResolvedValue({
    token: "tok",
    ws_path: "/",
    expires_in: 300,
  }),
  deriveWsUrl: vi.fn(() => "ws://test"),
  loadSavedSecret: vi.fn(() => ""),
  saveSecret: vi.fn(),
  clearSavedSecret: vi.fn(),
}));

vi.mock("@/lib/nanobot-client", () => {
  class MockClient {
    status = "idle" as const;
    defaultChatId: string | null = null;
    onReauth?: () => Promise<string | null>;
    connect = connectSpy;
    constructor(options?: { onReauth?: () => Promise<string | null> }) {
      this.onReauth = options?.onReauth;
      mockClientInstances.push(this);
    }
    onStatus = () => () => {};
    onError = () => () => {};
    onChat = () => () => {};
    sendMessage = vi.fn();
    newChat = vi.fn();
    attach = vi.fn();
    close = vi.fn();
    updateUrl = vi.fn();
  }

  return { NanobotClient: MockClient };
});

import App from "@/App";

async function findSidebarButton(name: RegExp) {
  const buttons = await screen.findAllByRole("button", { name });
  expect(buttons.length).toBeGreaterThan(0);
  return buttons[0];
}

function getSidebarButton(name: RegExp) {
  const buttons = screen.getAllByRole("button", { name });
  expect(buttons.length).toBeGreaterThan(0);
  return buttons[0];
}

describe("App layout", () => {
  beforeEach(() => {
    mockSessions = [];
    mockClientInstances.length = 0;
    connectSpy.mockClear();
    refreshSpy.mockReset();
    createChatSpy.mockClear();
    deleteChatSpy.mockReset();
    toggleThemeSpy.mockReset();
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: false,
        status: 404,
      }),
    );
  });

  it("keeps sidebar layout out of the main thread width contract", async () => {
    const { container } = render(<App />);

    await waitFor(() => expect(connectSpy).toHaveBeenCalled());

    const main = container.querySelector("main");
    expect(main).toBeInTheDocument();
    expect(main?.getAttribute("style") ?? "").not.toContain("width:");

    const asideClassNames = Array.from(container.querySelectorAll("aside")).map(
      (el) => el.className,
    );
    expect(asideClassNames.some((cls) => cls.includes("lg:block"))).toBe(true);
  });

  it("provides an accessible title and description for the mobile sidebar sheet", async () => {
    vi.stubGlobal(
      "matchMedia",
      vi.fn().mockImplementation(() => ({
        matches: false,
        media: "(min-width: 1024px)",
        onchange: null,
        addListener: vi.fn(),
        removeListener: vi.fn(),
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
        dispatchEvent: vi.fn(),
      })),
    );

    render(<App />);

    await waitFor(() => expect(connectSpy).toHaveBeenCalled());
    fireEvent.click(screen.getByRole("button", { name: "Toggle sidebar" }));

    expect(await screen.findByText("Navigation sidebar")).toBeInTheDocument();
    expect(
      screen.getByText("Browse recent chats, start a new chat, or open settings."),
    ).toBeInTheDocument();
  });

  it("keeps the mobile sidebar non-modal so thread content stays reachable", async () => {
    mockSessions = [
      {
        key: "websocket:chat-a",
        channel: "websocket",
        chatId: "chat-a",
        createdAt: "2026-04-16T10:00:00Z",
        updatedAt: "2026-04-16T10:00:00Z",
        preview: "First chat",
        activeTarget: null,
      },
    ];

    vi.stubGlobal(
      "matchMedia",
      vi.fn().mockImplementation(() => ({
        matches: false,
        media: "(min-width: 1024px)",
        onchange: null,
        addListener: vi.fn(),
        removeListener: vi.fn(),
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
        dispatchEvent: vi.fn(),
      })),
    );

    render(<App />);

    await waitFor(() => expect(connectSpy).toHaveBeenCalled());
    fireEvent.click(screen.getByRole("button", { name: "Toggle sidebar" }));

    expect(await findSidebarButton(/^Home$/)).toBeInTheDocument();
    expect(getSidebarButton(/^First chat\b/)).toBeInTheDocument();
  });

  it("shows a fixed Home entry in the sidebar and returns to dashboard home", async () => {
    mockSessions = [
      {
        key: "websocket:chat-a",
        channel: "websocket",
        chatId: "chat-a",
        createdAt: "2026-04-16T10:00:00Z",
        updatedAt: "2026-05-01T11:00:00Z",
        preview: "First chat",
        activeTarget: null,
      },
    ];

    render(<App />);

    await waitFor(() => expect(connectSpy).toHaveBeenCalled());
    expect(await findSidebarButton(/^First chat\b/)).toBeInTheDocument();

    fireEvent.click(getSidebarButton(/^Home$/));

    expect(await screen.findByText("Dashboard")).toBeInTheDocument();
    expect(screen.queryByRole("textbox", { name: "메시지 입력" })).not.toBeInTheDocument();
  });

  it("switches to the next session when deleting the active chat", async () => {
    mockSessions = [
      {
        key: "websocket:chat-a",
        channel: "websocket",
        chatId: "chat-a",
        createdAt: "2026-04-16T10:00:00Z",
        updatedAt: "2026-04-16T10:00:00Z",
        preview: "First chat",
        activeTarget: "smart-router",
      },
      {
        key: "websocket:chat-b",
        channel: "websocket",
        chatId: "chat-b",
        createdAt: "2026-04-16T11:00:00Z",
        updatedAt: "2026-04-16T11:00:00Z",
        preview: "Second chat",
        activeTarget: null,
      },
    ];

    render(<App />);

    await waitFor(() => expect(connectSpy).toHaveBeenCalled());
    const sidebar = screen.getByRole("navigation", { name: "Sidebar navigation" });
    await waitFor(() =>
      expect(
        within(sidebar).getAllByRole("button", { name: /First chat/ })[0],
      ).toBeInTheDocument(),
    );
    expect(screen.getByText("smart-router")).toBeInTheDocument();

    fireEvent.pointerDown(screen.getByLabelText("Chat actions for First chat"), {
      button: 0,
    });
    fireEvent.click(await screen.findByRole("menuitem", { name: "Delete" }));

    await waitFor(() =>
      expect(screen.getByText("Delete this chat?")).toBeInTheDocument(),
    );
    fireEvent.click(screen.getByRole("button", { name: "Delete" }));

    await waitFor(() =>
      expect(deleteChatSpy).toHaveBeenCalledWith("websocket:chat-a"),
    );
    await waitFor(() =>
      expect(
        within(sidebar).getAllByRole("button", { name: /Second chat/ })[0],
      ).toBeInTheDocument(),
    );
    expect(screen.queryByText("Delete this chat?")).not.toBeInTheDocument();
    expect(document.body.style.pointerEvents).not.toBe("none");
  }, 15_000);

  it("opens the Cursor-style settings view from the header", async () => {
    mockSessions = [
      {
        key: "websocket:chat-a",
        channel: "websocket",
        chatId: "chat-a",
        createdAt: "2026-04-16T10:00:00Z",
        updatedAt: "2026-04-16T10:00:00Z",
        preview: "Existing chat",
      },
    ];
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL) => {
        if (String(input).includes("/webui/bootstrap")) {
          return {
            ok: true,
            status: 200,
            json: async () => ({
              token: "tok",
              ws_path: "/",
              expires_in: 300,
              model_name: "openai/gpt-5.4",
              active_target: "default",
              model_targets: [
                { name: "default", kind: "provider_model", model: "openai/gpt-5.4" },
              ],
            }),
          };
        }
        if (String(input).includes("/api/settings")) {
          return {
            ok: true,
            status: 200,
            json: async () => ({
              agent: {
                model: "openai/gpt-4o",
                provider: "auto",
                resolved_provider: "openai",
                has_api_key: true,
              },
              providers: [
                { name: "auto", label: "Auto" },
                { name: "openai", label: "OpenAI" },
              ],
              runtime: {
                config_path: "/tmp/config.json",
              },
              requires_restart: false,
            }),
          };
        }
        return { ok: false, status: 404, json: async () => ({}) };
      }),
    );

    render(<App />);

    await waitFor(() => expect(connectSpy).toHaveBeenCalled());
    fireEvent.click(screen.getByRole("button", { name: "Open settings" }));

    expect(await screen.findByRole("heading", { name: "General" })).toBeInTheDocument();
    expect(screen.getByText("Defaults")).toBeInTheDocument();
    expect(screen.getByText("Themes")).toBeInTheDocument();
    expect(screen.getByText("System")).toBeInTheDocument();
    expect(screen.getByText("Account")).toBeInTheDocument();
    expect(screen.getByText("Disconnect this browser from the gateway.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Sign out" })).toBeInTheDocument();
    expect(screen.getByDisplayValue("openai/gpt-4o")).toBeInTheDocument();
    expect(screen.getByText("15")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Increase chat font size" }));
    expect(screen.getByText("17")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Decrease chat font size" }));
    expect(screen.getByText("15")).toBeInTheDocument();
  });

  it("refreshes the REST token when websocket reauth succeeds", async () => {
    vi.mocked(fetchBootstrap)
      .mockResolvedValueOnce({
        token: "tok-1",
        ws_path: "/",
        expires_in: 300,
        model_name: "openai/gpt-5.4",
        active_target: "default",
        model_targets: [],
      })
      .mockResolvedValueOnce({
        token: "tok-2",
        ws_path: "/",
        expires_in: 300,
        model_name: "openai/gpt-5.4",
        active_target: "default",
        model_targets: [],
      });

    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      if (String(input).includes("/api/settings")) {
        return {
          ok: true,
          status: 200,
          json: async () => ({
            agent: {
              model: "openai/gpt-5.4",
              provider: "auto",
              resolved_provider: "openai",
              has_api_key: true,
            },
            providers: [
              { name: "auto", label: "Auto" },
              { name: "openai", label: "OpenAI" },
            ],
            runtime: { config_path: "/tmp/config.json" },
            requires_restart: false,
          }),
          headers: init?.headers,
        };
      }
      return { ok: false, status: 404, json: async () => ({}) };
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<App />);

    await waitFor(() => expect(connectSpy).toHaveBeenCalled());

    const client = mockClientInstances[0];
    expect(client?.onReauth).toBeTypeOf("function");

    await act(async () => {
      await client.onReauth?.();
    });

    fireEvent.click(screen.getByRole("button", { name: "Open settings" }));

    await waitFor(() => expect(screen.getByRole("heading", { name: "General" })).toBeInTheDocument());
    await waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith(
        expect.stringContaining("/api/settings"),
        expect.objectContaining({
          headers: expect.objectContaining({
            Authorization: "Bearer tok-2",
          }),
        }),
      ),
    );
  });

  it("uses bootstrap model_name instead of active_target for the default model label", async () => {
    mockSessions = [
      {
        key: "websocket:chat-a",
        channel: "websocket",
        chatId: "chat-a",
        createdAt: "2026-04-16T10:00:00Z",
        updatedAt: "2026-04-16T10:00:00Z",
        preview: "First chat",
        activeTarget: "default",
      },
    ];

    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL) => {
        if (String(input).includes("/webui/bootstrap")) {
          return {
            ok: true,
            status: 200,
            json: async () => ({
              token: "tok",
              ws_path: "/",
              expires_in: 300,
              model_name: "openai/gpt-5.4",
              active_target: "default",
              model_targets: [
                { name: "default", kind: "provider_model", model: "openai/gpt-5.4" },
              ],
            }),
          };
        }
        if (String(input).includes("/api/sessions/websocket%3Achat-a/model-target")) {
          return {
            ok: true,
            status: 200,
            json: async () => ({
              key: "websocket:chat-a",
              active_target: "default",
              target: { name: "default", kind: "provider_model", model: "openai/gpt-5.4" },
            }),
          };
        }
        return { ok: false, status: 404, json: async () => ({}) };
      }),
    );

    render(<App />);

    await waitFor(() => expect(connectSpy).toHaveBeenCalled());
    await waitFor(() => expect(screen.getByText("gpt-5.4")).toBeInTheDocument());
    expect(screen.queryByText(/^default$/i)).not.toBeInTheDocument();
  });

  it("shows compact assistant status badges in the thread header", async () => {
    mockSessions = [
      {
        key: "telegram:chat-a",
        channel: "telegram",
        chatId: "chat-a",
        createdAt: "2026-04-16T10:00:00Z",
        updatedAt: "2026-04-16T10:00:00Z",
        preview: "Telegram chat",
        activeTarget: "smart-router",
      },
    ];

    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL) => {
        if (String(input).includes("/webui/bootstrap")) {
          return {
            ok: true,
            status: 200,
            json: async () => ({
              token: "tok",
              ws_path: "/",
              expires_in: 300,
              model_name: "openai/gpt-5.4",
              active_target: "smart-router",
              model_targets: [
                { name: "smart-router", kind: "smart_router", model: null },
              ],
            }),
          };
        }
        if (String(input).includes("/api/sessions/telegram%3Achat-a/model-target")) {
          return {
            ok: true,
            status: 200,
            json: async () => ({
              key: "telegram:chat-a",
              active_target: "smart-router",
              target: { name: "smart-router", kind: "smart_router", model: null },
            }),
          };
        }
        return { ok: false, status: 404, json: async () => ({}) };
      }),
    );

    render(<App />);

    await waitFor(() => expect(connectSpy).toHaveBeenCalled());
    await waitFor(() => expect(screen.getByText("Target Auto")).toBeInTheDocument());
    expect(screen.getByText("Channel Telegram")).toBeInTheDocument();
  });

  it("shows env-managed local settings as locked with the resolved model value", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL) => {
        if (String(input).includes("/webui/bootstrap")) {
          return {
            ok: true,
            status: 200,
            json: async () => ({
              token: "tok",
              ws_path: "/",
              expires_in: 300,
              model_name: "LiquidAI/LFM2-24B-A2B-GGUF:Q4_0",
              active_target: "default",
              model_targets: [
                {
                  name: "default",
                  kind: "provider_model",
                  model: "LiquidAI/LFM2-24B-A2B-GGUF:Q4_0",
                },
              ],
            }),
          };
        }
        if (String(input).includes("/api/settings")) {
          return {
            ok: true,
            status: 200,
            json: async () => ({
              agent: {
                model: "LiquidAI/LFM2-24B-A2B-GGUF:Q4_0",
                configured_model: "${LOCAL_LLM_MODEL}",
                provider: "vllm",
                resolved_provider: "vllm",
                has_api_key: false,
                model_locked: true,
                provider_locked: true,
              },
              providers: [
                { name: "auto", label: "Auto" },
                { name: "vllm", label: "vLLM/Local" },
              ],
              runtime: {
                config_path: "/tmp/config.json",
              },
              requires_restart: false,
            }),
          };
        }
        return { ok: false, status: 404, json: async () => ({}) };
      }),
    );

    render(<App />);

    await waitFor(() => expect(connectSpy).toHaveBeenCalled());
    fireEvent.click(screen.getByRole("button", { name: "Open settings" }));

    expect(await screen.findByText("Default settings for model selection, theme, and chat readability.")).toBeInTheDocument();
    expect(screen.getByText("Defaults")).toBeInTheDocument();

    const modelInput = await screen.findByDisplayValue(
      "LiquidAI/LFM2-24B-A2B-GGUF:Q4_0",
    );
    expect(modelInput).toBeDisabled();
    const providerSelect = screen.getAllByRole("combobox")[0] as HTMLSelectElement;
    expect(providerSelect).toBeDisabled();
    expect(providerSelect.value).toBe("vllm");
    expect(screen.getByText("Provider or model is locked by the current runtime configuration.")).toBeInTheDocument();
  });

  it("filters sidebar sessions through the lightweight search row", async () => {
    mockSessions = [
      {
        key: "websocket:chat-alpha",
        channel: "websocket",
        chatId: "chat-alpha",
        createdAt: new Date().toISOString(),
        updatedAt: new Date().toISOString(),
        preview: "Project planning notes",
      },
      {
        key: "websocket:chat-beta",
        channel: "websocket",
        chatId: "chat-beta",
        createdAt: "2026-04-15T10:00:00Z",
        updatedAt: "2026-04-15T10:00:00Z",
        preview: "Travel ideas",
      },
    ];

    render(<App />);

    await waitFor(() => expect(connectSpy).toHaveBeenCalled());
    const sidebar = screen.getByRole("navigation", { name: "Sidebar navigation" });
    expect(within(sidebar).getByText("Project planning notes")).toBeInTheDocument();
    expect(within(sidebar).getByText("Travel ideas")).toBeInTheDocument();

    fireEvent.change(screen.getByRole("textbox", { name: "Search chats" }), {
      target: { value: "travel" },
    });

    expect(within(sidebar).queryByText("Project planning notes")).not.toBeInTheDocument();
    expect(within(sidebar).getByText("Travel ideas")).toBeInTheDocument();
  });

  it("opens a blank start page without creating an empty chat", async () => {
    mockSessions = [
      {
        key: "websocket:chat-a",
        channel: "websocket",
        chatId: "chat-a",
        createdAt: "2026-04-16T10:00:00Z",
        updatedAt: "2026-04-16T10:00:00Z",
        preview: "Existing chat",
      },
    ];

    const matchMedia = vi.fn().mockImplementation((query: string) => ({
      matches: query.includes("1024px"),
      media: query,
      onchange: null,
      addListener: vi.fn(),
      removeListener: vi.fn(),
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      dispatchEvent: vi.fn(),
    }));
    vi.stubGlobal("matchMedia", matchMedia);

    const { container } = render(<App />);

    await waitFor(() => expect(connectSpy).toHaveBeenCalled());

    fireEvent.click(screen.getByRole("button", { name: "Toggle theme from header" }));
    expect(toggleThemeSpy).toHaveBeenCalledTimes(1);

    fireEvent.click(screen.getByRole("button", { name: "Collapse sidebar" }));
    const desktopAside = container.querySelector("aside.lg\\:block") as HTMLElement;
    await waitFor(() => expect(desktopAside.style.width).toBe("0px"));

    expect(screen.queryByRole("button", { name: "Start a new chat" })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Toggle sidebar" }));
    await waitFor(() => expect(desktopAside.style.width).toBe("279px"));

    const sidebar = screen.getByRole("navigation", { name: "Sidebar navigation" });
    fireEvent.click(within(sidebar).getByRole("button", { name: "New chat" }));
    expect(createChatSpy).not.toHaveBeenCalled();
    expect(screen.queryByText("Dashboard")).not.toBeInTheDocument();
    expect(screen.getByLabelText("Message input")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Create a project plan" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Start a new chat" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Toggle theme from header" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Open settings" })).toBeInTheDocument();

    expect(within(sidebar).getByText("Existing chat")).toBeInTheDocument();
  });
});
