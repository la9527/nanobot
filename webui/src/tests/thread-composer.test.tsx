import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { ThreadComposer } from "@/components/thread/ThreadComposer";

describe("ThreadComposer", () => {
  it("renders a readonly hero model composer when provided", () => {
    render(
      <ThreadComposer
        onSend={vi.fn()}
        modelLabel="claude-opus-4-5"
        placeholder="What's on your mind?"
        variant="hero"
      />,
    );

    expect(screen.getByText("claude-opus-4-5")).toBeInTheDocument();
    const input = screen.getByPlaceholderText("What's on your mind?");
    expect(input).toBeInTheDocument();
    expect(input.className).toContain("min-h-[96px]");
    expect(input.parentElement?.className).toContain("max-w-[40rem]");
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

    expect(onSend).toHaveBeenNthCalledWith(1, "first prompt", undefined);
    expect(onSend).toHaveBeenNthCalledWith(2, "second prompt", undefined);

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
