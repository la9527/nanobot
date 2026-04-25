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
          { name: "smart-router", kind: "smart_router", description: "smart-router runtime plugin target." },
        ]}
        onSelectModelTarget={onSelectModelTarget}
      />,
    );

    await user.click(screen.getByRole("button", { name: "Choose model target" }));
    expect(screen.getByText("openai/gpt-5.4")).toBeInTheDocument();
    await user.click(screen.getByRole("menuitemradio", { name: /default/i }));

    expect(onSelectModelTarget).toHaveBeenCalledWith("default");
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
