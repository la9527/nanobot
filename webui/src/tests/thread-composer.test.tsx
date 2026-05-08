import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { ThreadComposer } from "@/components/thread/ThreadComposer";
import type { SlashCommand } from "@/lib/types";

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

    render(
      <ThreadComposer
        onSend={vi.fn()}
        modelLabel="smart-router"
        activeTarget="smart-router"
        modelTargets={[
          { name: "default", kind: "provider_model", model: "openai/gpt-5.4", description: "Startup default provider/model." },
          { name: "local-llm", kind: "provider_model", provider: "vllm", model: "LiquidAI/LFM2-24B-A2B-GGUF:Q4_0", description: "현재 기본 local runtime (LiquidAI/LFM2-24B-A2B-GGUF:Q4_0)" },
          { name: "smart-router", kind: "smart_router", display_name: "Auto", group: "smart-router", smart_router_mode: "auto", description: "smart-router runtime plugin target." },
          { name: "smart-router-local", kind: "smart_router", display_name: "Local", group: "smart-router", smart_router_mode: "local", description: "smart-router forced local tier." },
          { name: "smart-router-mini", kind: "smart_router", display_name: "Mini", group: "smart-router", smart_router_mode: "mini", description: "smart-router forced mini tier." },
          { name: "smart-router-full", kind: "smart_router", display_name: "Full", group: "smart-router", smart_router_mode: "full", description: "smart-router forced full tier." },
        ]}
        onSelectModelTarget={onSelectModelTarget}
      />,
    );

    await user.click(screen.getByRole("button", { name: "Choose model target" }));
    expect(screen.getByText(/^Auto$/i)).toBeInTheDocument();
    expect(screen.getByText(/^Local$/i)).toBeInTheDocument();
    expect(screen.getByText(/^Mini$/i)).toBeInTheDocument();
    expect(screen.getByText(/^Full$/i)).toBeInTheDocument();
    expect(screen.getByText("vllm -> LiquidAI/LFM2-24B-A2B-GGUF:Q4_0")).toBeInTheDocument();
    expect(screen.getByText("현재 기본 local runtime (LiquidAI/LFM2-24B-A2B-GGUF:Q4_0)")).toBeInTheDocument();
    expect(screen.getByText("openai/gpt-5.4")).toBeInTheDocument();
    await user.click(screen.getByRole("menuitemradio", { name: /Mini/i }));

    expect(onSelectModelTarget).toHaveBeenCalledWith("smart-router-mini");
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
