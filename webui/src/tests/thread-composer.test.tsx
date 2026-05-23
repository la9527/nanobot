import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { ThreadComposer } from "@/components/thread/ThreadComposer";
import type { SlashCommand } from "@/lib/types";

vi.mock("@/lib/imageEncode", () => ({
  encodeImage: vi.fn(async () => ({
    ok: true,
    dataUrl: "data:image/png;base64,abc123",
    bytes: 6,
    normalized: false,
  })),
}));

const COMMANDS: SlashCommand[] = [
  {
    command: "/stop",
    title: "Stop current task",
    description: "Cancel the active agent turn.",
    icon: "square",
  },
  {
    command: "/history",
    title: "Show conversation history",
    description: "Print the last N persisted messages.",
    icon: "history",
    argHint: "[n]",
  },
];

const COMMANDS_WITH_RECENT_ADDITIONS: SlashCommand[] = [
  { command: "/new", title: "New chat", description: "Start fresh.", icon: "square-pen" },
  { command: "/status", title: "Show status", description: "Check runtime state.", icon: "activity" },
  { command: "/model", title: "Select model target", description: "Choose a target.", icon: "bot", argHint: "[name|list|clear]" },
  { command: "/usage", title: "Set usage details", description: "Adjust token details.", icon: "gauge", argHint: "[off|tokens|full]" },
  { command: "/mail", title: "Manage Gmail", description: "Open mail actions.", icon: "mail", argHint: "[subcommand]" },
  { command: "/calendar", title: "Manage calendar", description: "Open calendar actions.", icon: "calendar-days", argHint: "[subcommand]" },
  { command: "/history", title: "Show conversation history", description: "Inspect persisted messages.", icon: "history", argHint: "[n]" },
  { command: "/dream", title: "Run Dream", description: "Run memory consolidation.", icon: "sparkles" },
  { command: "/dream-log", title: "Show Dream log", description: "Inspect Dream changes.", icon: "book-open" },
  { command: "/dream-restore", title: "Restore memory", description: "Revert memory to a previous Dream snapshot.", icon: "undo-2" },
  { command: "/help", title: "Show help", description: "List commands.", icon: "circle-help" },
];

describe("ThreadComposer", () => {
  it("renders a readonly hero model composer when provided", () => {
    render(
      <ThreadComposer
        onSend={vi.fn()}
        modelLabel="claude-opus-4-5"
        placeholder="Ask anything..."
        variant="hero"
      />,
    );

    expect(screen.getByText("claude-opus-4-5")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Search" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Reason" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Deep research" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Voice input" })).not.toBeInTheDocument();
    const input = screen.getByPlaceholderText("Ask anything...");
    expect(input).toBeInTheDocument();
    expect(input.className).toContain("min-h-[78px]");
    expect(input.parentElement?.className).toContain("max-w-[58rem]");
  });

  it("keeps the thread composer compact while matching the hero style", () => {
    render(
      <ThreadComposer
        onSend={vi.fn()}
        modelLabel="gpt-4o"
        placeholder="Type your message..."
      />,
    );

    expect(screen.getByText("gpt-4o")).toBeInTheDocument();
    const input = screen.getByPlaceholderText("Type your message...");
    expect(input.className).toContain("min-h-[50px]");
    expect(input.parentElement?.className).toContain("max-w-[49.5rem]");
    expect(input.parentElement?.className).toContain("rounded-[22px]");
    expect(input.parentElement?.className).toContain("shadow-[0_12px_30px_rgba(15,23,42,0.07)]");
    expect(screen.getByRole("button", { name: "Attach image" }).className).toContain("bg-card");
    expect(screen.getByRole("button", { name: "Send message" }).className).toContain("bg-foreground");
  });

  it("opens a slash command palette and inserts the selected command", () => {
    const onSend = vi.fn();
    render(
      <ThreadComposer
        onSend={onSend}
        placeholder="Type your message..."
        slashCommands={COMMANDS}
      />,
    );

    const input = screen.getByLabelText("Message input");
    fireEvent.change(input, { target: { value: "/" } });

    expect(screen.getByRole("listbox", { name: "Slash commands" })).toBeInTheDocument();
    expect(screen.getByRole("option", { name: /\/stop/i })).toHaveAttribute(
      "aria-selected",
      "true",
    );

    fireEvent.keyDown(input, { key: "ArrowDown" });
    expect(screen.getByRole("option", { name: /\/history/i })).toHaveAttribute(
      "aria-selected",
      "true",
    );
    fireEvent.keyDown(input, { key: "Enter" });

    expect(input).toHaveValue("/history ");
    expect(onSend).not.toHaveBeenCalled();
    expect(screen.queryByRole("listbox", { name: "Slash commands" })).not.toBeInTheDocument();
  });

  it("shows newly added slash commands when opening the palette", () => {
    render(
      <ThreadComposer
        onSend={vi.fn()}
        placeholder="Type your message..."
        slashCommands={COMMANDS_WITH_RECENT_ADDITIONS}
      />,
    );

    const input = screen.getByLabelText("Message input");
    fireEvent.change(input, { target: { value: "/" } });

    expect(screen.getByRole("option", { name: /\/calendar/i })).toBeInTheDocument();
    expect(screen.getByRole("option", { name: /\/dream-restore/i })).toBeInTheDocument();
    expect(screen.getByRole("option", { name: /\/mail/i })).toBeInTheDocument();
    expect(screen.getByRole("option", { name: /\/model/i })).toBeInTheDocument();
    expect(screen.getByRole("option", { name: /\/usage/i })).toBeInTheDocument();
  });

  it("keeps the slash palette viewport-bounded with an internal scroll area", () => {
    const { container } = render(
      <ThreadComposer
        onSend={vi.fn()}
        placeholder="Type your message..."
        slashCommands={COMMANDS_WITH_RECENT_ADDITIONS}
      />,
    );

    const input = screen.getByLabelText("Message input");
    fireEvent.change(input, { target: { value: "/" } });

    const scrollContainer = container.querySelector('[style*="max-height"]');
    expect(scrollContainer?.className).toContain("overflow-y-auto");
    expect(scrollContainer?.className).toContain("overscroll-contain");
    expect(scrollContainer?.getAttribute("style")).toContain("max-height: min(22rem, 45vh)");
  });

  it("sends image generation mode with automatic aspect ratio", () => {
    const onSend = vi.fn();
    render(
      <ThreadComposer
        onSend={onSend}
        placeholder="Type your message..."
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "Toggle image generation mode" }));
    expect(screen.getByPlaceholderText("Describe or edit an image…")).toBeInTheDocument();

    const input = screen.getByLabelText("Message input");
    fireEvent.change(input, { target: { value: "Draw a friendly robot" } });
    fireEvent.click(screen.getByRole("button", { name: "Send message" }));

    expect(onSend).toHaveBeenCalledWith(
      "Draw a friendly robot",
      undefined,
      { imageGeneration: { enabled: true, aspect_ratio: null } },
    );
  });

  it("shows a stop button while streaming", () => {
    const onStop = vi.fn();
    render(
      <ThreadComposer
        onSend={vi.fn()}
        onStop={onStop}
        isStreaming
        placeholder="Type your message..."
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "Stop response" }));

    expect(onStop).toHaveBeenCalledTimes(1);
    expect(screen.queryByRole("button", { name: "Send message" })).not.toBeInTheDocument();
  });

  it("lets users select a concrete image aspect ratio", () => {
    const onSend = vi.fn();
    render(
      <ThreadComposer
        onSend={onSend}
        placeholder="Type your message..."
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "Toggle image generation mode" }));
    fireEvent.click(screen.getByRole("button", { name: "Image aspect ratio" }));
    expect(screen.getByRole("listbox", { name: "Image aspect ratio" }).className).toContain(
      "bottom-full",
    );
    fireEvent.mouseDown(screen.getByRole("option", { name: "Wide 16:9" }));

    const input = screen.getByLabelText("Message input");
    fireEvent.change(input, { target: { value: "Draw a banner" } });
    fireEvent.click(screen.getByRole("button", { name: "Send message" }));

    expect(onSend).toHaveBeenCalledWith(
      "Draw a banner",
      undefined,
      { imageGeneration: { enabled: true, aspect_ratio: "16:9" } },
    );
  });

  it("opens the hero image aspect menu downward", () => {
    render(
      <ThreadComposer
        onSend={vi.fn()}
        placeholder="Ask anything..."
        variant="hero"
        imageMode
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "Image aspect ratio" }));

    expect(screen.getByRole("listbox", { name: "Image aspect ratio" }).className).toContain(
      "top-full",
    );
  });

  it("dismisses the image aspect menu on outside click, escape, and wheel", () => {
    render(
      <div>
        <button type="button">outside</button>
        <ThreadComposer
          onSend={vi.fn()}
          placeholder="Type your message..."
          imageMode
        />
      </div>,
    );

    const aspectButton = screen.getByRole("button", { name: "Image aspect ratio" });
    fireEvent.click(aspectButton);
    expect(screen.getByRole("listbox", { name: "Image aspect ratio" })).toBeInTheDocument();

    fireEvent.pointerDown(screen.getByRole("button", { name: "outside" }));
    expect(screen.queryByRole("listbox", { name: "Image aspect ratio" })).not.toBeInTheDocument();

    fireEvent.click(aspectButton);
    fireEvent.keyDown(document, { key: "Escape" });
    expect(screen.queryByRole("listbox", { name: "Image aspect ratio" })).not.toBeInTheDocument();

    fireEvent.click(aspectButton);
    fireEvent.wheel(screen.getByRole("listbox", { name: "Image aspect ratio" }), { deltaY: 120 });
    expect(screen.queryByRole("listbox", { name: "Image aspect ratio" })).not.toBeInTheDocument();
  });

  it("opens the model target selector and reports changes", async () => {
    const user = userEvent.setup();
    const onSelectModelTarget = vi.fn();
    const loadLocalLlmStatus = vi.fn().mockResolvedValue({
      default_target: "lfm2",
      default_model: "LiquidAI/LFM2-24B-A2B-GGUF:Q4_0",
      default_api_base: "http://127.0.0.1:1242/v1",
      targets: [
        {
          name: "lfm2",
          label: "LFM2",
          provider: "llama.cpp",
          runtime: "llama.cpp",
          model: "LiquidAI/LFM2-24B-A2B-GGUF:Q4_0",
          api_base: "http://127.0.0.1:1242/v1",
          launchd_label: "com.nanobot.local-model-lfm2",
          running: true,
          endpoint_ok: true,
          supports_vision: false,
          vision_check_ok: false,
          vision_check_message: "endpoint unavailable",
          is_default: true,
        },
      ],
    });

    render(
      <ThreadComposer
        onSend={vi.fn()}
        modelLabel="smart-router"
        activeTarget="smart-router"
        modelTargets={[
          { name: "default", kind: "provider_model", model: "openai/gpt-5.4", description: "Startup default provider/model." },
          { name: "local-llm", kind: "provider_model", provider: "vllm", model: "LiquidAI/LFM2-24B-A2B-GGUF:Q4_0", description: "현재 기본 local runtime (LiquidAI/LFM2-24B-A2B-GGUF:Q4_0)" },
          { name: "smart-router", kind: "smart_router", display_name: "Auto", group: "smart-router", smart_router_mode: "auto", description: "smart-router runtime plugin target." },
          { name: "smart-router-local", kind: "smart_router", provider: "vllm", model: "LiquidAI/LFM2-24B-A2B-GGUF:Q4_0", display_name: "Local", group: "smart-router", smart_router_mode: "local", description: "smart-router forced local tier (LiquidAI/LFM2-24B-A2B-GGUF:Q4_0)" },
          { name: "smart-router-mini", kind: "smart_router", provider: "openrouter", model: "openai/gpt-5.4-mini", display_name: "Mini", group: "smart-router", smart_router_mode: "mini", description: "smart-router forced mini tier." },
          { name: "smart-router-full", kind: "smart_router", provider: "openrouter", model: "openai/gpt-5.4", display_name: "Full", group: "smart-router", smart_router_mode: "full", description: "smart-router forced full tier." },
        ]}
        loadLocalLlmStatus={loadLocalLlmStatus}
        onSelectModelTarget={onSelectModelTarget}
      />,
    );

    await user.click(screen.getByRole("button", { name: "Choose model target" }));
    await waitFor(() => expect(loadLocalLlmStatus).toHaveBeenCalledTimes(1));
    expect(screen.getByText(/^Auto$/i)).toBeInTheDocument();
    expect(screen.getByText(/^Local$/i)).toBeInTheDocument();
    expect(screen.getByText(/^Mini$/i)).toBeInTheDocument();
    expect(screen.getByText(/^Full$/i)).toBeInTheDocument();
    expect(screen.getByText("Automatic model selection")).toBeInTheDocument();
    expect(screen.getByText("llama.cpp -> LiquidAI/LFM2-24B-A2B-GGUF:Q4_0")).toBeInTheDocument();
    expect(screen.getByText("openrouter -> openai/gpt-5.4-mini")).toBeInTheDocument();
    expect(screen.getByText("openrouter -> openai/gpt-5.4")).toBeInTheDocument();
    expect(screen.queryByText("Local LLM")).not.toBeInTheDocument();
    expect(screen.queryByText("Startup default provider/model.")).not.toBeInTheDocument();
    await user.click(screen.getByRole("menuitemradio", { name: /Mini/i }));

    expect(onSelectModelTarget).toHaveBeenCalledWith("smart-router-mini");
  });

  it("disables the local smart-router target when an image is attached and the active local runtime lacks vision", async () => {
    const user = userEvent.setup();
    const onSelectModelTarget = vi.fn();
    const loadLocalLlmStatus = vi.fn().mockResolvedValue({
      default_target: "qwen36",
      default_model: "mlx-community/Qwen3.6-35B-A3B-4bit",
      default_api_base: "http://127.0.0.1:1246/v1",
      targets: [
        {
          name: "qwen36",
          label: "Qwen3.6",
          provider: "vllm",
          runtime: "mlx_lm.server",
          model: "mlx-community/Qwen3.6-35B-A3B-4bit",
          api_base: "http://127.0.0.1:1246/v1",
          launchd_label: "com.nanobot.local-model-qwen36",
          running: true,
          endpoint_ok: true,
          supports_vision: false,
          vision_check_ok: true,
          vision_check_message: "Only 'text' content type is supported.",
          is_default: true,
        },
      ],
    });

    const { container } = render(
      <ThreadComposer
        onSend={vi.fn()}
        modelLabel="smart-router"
        activeTarget="smart-router"
        modelTargets={[
          { name: "smart-router", kind: "smart_router", display_name: "Auto", group: "smart-router", smart_router_mode: "auto", description: "smart-router runtime plugin target." },
          { name: "smart-router-local", kind: "smart_router", provider: "vllm", model: "mlx-community/Qwen3.6-35B-A3B-4bit", display_name: "Local", group: "smart-router", smart_router_mode: "local", description: "smart-router forced local tier (mlx-community/Qwen3.6-35B-A3B-4bit)" },
          { name: "smart-router-mini", kind: "smart_router", provider: "openrouter", model: "openai/gpt-5.4-mini", display_name: "Mini", group: "smart-router", smart_router_mode: "mini", description: "smart-router forced mini tier." },
        ]}
        loadLocalLlmStatus={loadLocalLlmStatus}
        onSelectModelTarget={onSelectModelTarget}
      />,
    );

    const fileInput = container.querySelector('input[type="file"]') as HTMLInputElement;
    const file = new File([new Uint8Array([137, 80, 78, 71])], "vision.png", { type: "image/png" });
    fireEvent.change(fileInput, { target: { files: [file] } });

    await user.click(screen.getByRole("button", { name: "Choose model target" }));
    await waitFor(() => expect(loadLocalLlmStatus).toHaveBeenCalledTimes(1));

    const localItem = screen.getByRole("menuitemradio", { name: /Local/i });
    expect(localItem).toHaveAttribute("data-disabled");
    expect(screen.getByText("Current local LLM does not support image input.")).toBeInTheDocument();

    await user.click(localItem);
    expect(onSelectModelTarget).not.toHaveBeenCalledWith("smart-router-local");
  });

  it("blocks sending image input when the active local target lacks vision support", async () => {
    const user = userEvent.setup();
    const onSend = vi.fn();
    const loadLocalLlmStatus = vi.fn().mockResolvedValue({
      default_target: "qwen36",
      default_model: "mlx-community/Qwen3.6-35B-A3B-4bit",
      default_api_base: "http://127.0.0.1:1246/v1",
      targets: [
        {
          name: "qwen36",
          label: "Qwen3.6",
          provider: "vllm",
          runtime: "mlx_lm.server",
          model: "mlx-community/Qwen3.6-35B-A3B-4bit",
          api_base: "http://127.0.0.1:1246/v1",
          launchd_label: "com.nanobot.local-model-qwen36",
          running: true,
          endpoint_ok: true,
          supports_vision: false,
          vision_check_ok: true,
          vision_check_message: "Only 'text' content type is supported.",
          is_default: true,
        },
      ],
    });

    const { container } = render(
      <ThreadComposer
        onSend={onSend}
        activeTarget="smart-router-local"
        modelLabel="Local"
        modelTargets={[
          { name: "smart-router-local", kind: "smart_router", provider: "vllm", model: "mlx-community/Qwen3.6-35B-A3B-4bit", display_name: "Local", group: "smart-router", smart_router_mode: "local", description: "smart-router forced local tier (mlx-community/Qwen3.6-35B-A3B-4bit)" },
        ]}
        loadLocalLlmStatus={loadLocalLlmStatus}
      />,
    );

    const fileInput = container.querySelector('input[type="file"]') as HTMLInputElement;
    const file = new File([new Uint8Array([137, 80, 78, 71])], "vision.png", { type: "image/png" });
    fireEvent.change(fileInput, { target: { files: [file] } });
    await user.type(screen.getByLabelText("Message input"), "What is in this image?");

    await waitFor(() => expect(loadLocalLlmStatus).toHaveBeenCalledTimes(1));
    expect(screen.getByText("Current local LLM does not support image input.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Send message" })).toBeDisabled();

    await user.click(screen.getByRole("button", { name: "Send message" }));
    expect(onSend).not.toHaveBeenCalled();
  });

  it("recalls prior sent text with up/down history navigation", async () => {
    const user = userEvent.setup();
    const onSend = vi.fn();

    render(<ThreadComposer onSend={onSend} />);
    const input = screen.getByLabelText("Message input");

    await user.type(input, "first prompt");
    await user.keyboard("{Enter}");
    await user.type(input, "second prompt");
    await user.keyboard("{Enter}");

    expect(onSend).toHaveBeenNthCalledWith(1, "first prompt", undefined, undefined);
    expect(onSend).toHaveBeenNthCalledWith(2, "second prompt", undefined, undefined);

    await user.keyboard("{ArrowUp}");
    expect(screen.getByDisplayValue("second prompt")).toBeInTheDocument();

    await user.keyboard("{ArrowUp}");
    expect(screen.getByDisplayValue("first prompt")).toBeInTheDocument();

    await user.keyboard("{ArrowDown}");
    expect(screen.getByDisplayValue("second prompt")).toBeInTheDocument();

    await user.keyboard("{ArrowDown}");
    expect((screen.getByLabelText("Message input") as HTMLTextAreaElement).value).toBe("");
  });
});
