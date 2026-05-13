import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { MessageBubble } from "@/components/MessageBubble";
import type { UIMessage } from "@/lib/types";

describe("MessageBubble", () => {
  it("renders user messages as right-aligned pills", () => {
    const message: UIMessage = {
      id: "u1",
      role: "user",
      content: "hello",
      createdAt: Date.now(),
    };

    const { container } = render(<MessageBubble message={message} />);
    const row = container.firstElementChild;
    const pill = screen.getByText("hello");

    expect(row).toHaveClass("ml-auto", "flex");
    expect(pill).toHaveClass("ml-auto", "w-fit", "rounded-[18px]");
    expect(screen.queryByRole("button", { name: "Copy reply" })).not.toBeInTheDocument();
  });

  it("copies completed assistant replies from the action row", async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, "clipboard", {
      configurable: true,
      value: { writeText },
    });
    const message: UIMessage = {
      id: "a-copy",
      role: "assistant",
      content: "I can help with the next step.",
      createdAt: Date.now(),
    };

    render(<MessageBubble message={message} />);

    fireEvent.click(screen.getByRole("button", { name: "Copy reply" }));

    expect(writeText).toHaveBeenCalledWith("I can help with the next step.");
    await waitFor(() =>
      expect(screen.getByRole("button", { name: "Copied reply" })).toBeInTheDocument(),
    );
  });

  it("does not show copy actions for streaming placeholders", () => {
    const message: UIMessage = {
      id: "a-streaming",
      role: "assistant",
      content: "",
      isStreaming: true,
      createdAt: Date.now(),
    };

    render(<MessageBubble message={message} />);

    expect(screen.queryByRole("button", { name: "Copy reply" })).not.toBeInTheDocument();
  });

  it("renders completed trace messages as collapsed reasoning cards", () => {
    const message: UIMessage = {
      id: "t1",
      role: "tool",
      kind: "trace",
      content: 'search "hk weather"',
      traces: ['weather("get")', 'search "hk weather"'],
      createdAt: Date.now(),
    };

    render(<MessageBubble message={message} />);
    const toggle = screen.getByRole("button", { name: /used 2 tools/i });

    expect(screen.getByText('search "hk weather"')).toBeInTheDocument();
    expect(screen.queryByText('weather("get")')).not.toBeInTheDocument();

    fireEvent.click(toggle);
    expect(screen.getByText('weather("get")')).toBeInTheDocument();
  });

  it("auto-collapses streaming trace cards when the turn completes", () => {
    const message: UIMessage = {
      id: "t-live",
      role: "tool",
      kind: "trace",
      content: 'search "hk weather"',
      traces: ['weather("get")', 'search "hk weather"'],
      isStreaming: true,
      createdAt: Date.now(),
    };

    const { rerender } = render(<MessageBubble message={message} />);

    expect(screen.getByText('weather("get")')).toBeInTheDocument();
    expect(screen.getAllByText('search "hk weather"')).toHaveLength(2);

    rerender(
      <MessageBubble
        message={{
          ...message,
          isStreaming: false,
        }}
      />,
    );

    expect(screen.queryByText('weather("get")')).not.toBeInTheDocument();
  });

  it("hides trace cards entirely when reasoning visibility is off", () => {
    const message: UIMessage = {
      id: "t-hidden",
      role: "tool",
      kind: "trace",
      content: "step",
      traces: ["step"],
      createdAt: Date.now(),
    };

    const { container } = render(
      <MessageBubble message={message} reasoningVisibility="off" />,
    );

    expect(container).toBeEmptyDOMElement();
  });

  it("renders compact reasoning cards in status_only mode", () => {
    const message: UIMessage = {
      id: "t-status",
      role: "tool",
      kind: "trace",
      content: 'search "hk weather"',
      traces: ['weather("get")', 'search "hk weather"'],
      isStreaming: true,
      createdAt: Date.now(),
    };

    render(<MessageBubble message={message} reasoningVisibility="status_only" />);

    expect(screen.getByText(/used 2 tools/i)).toBeInTheDocument();
    expect(screen.queryByText('weather("get")')).not.toBeInTheDocument();
  });

  it("renders status trace rows as one-line thinking entries", () => {
    const message: UIMessage = {
      id: "t-status-line",
      role: "tool",
      kind: "trace",
      traceVariant: "status",
      content: "현재 assistant 응답을 스트리밍하고 있습니다.",
      traces: ["현재 assistant 응답을 스트리밍하고 있습니다."],
      isStreaming: true,
      createdAt: Date.now(),
    };

    render(<MessageBubble message={message} reasoningVisibility="debug_trace" />);

    expect(screen.getByText(/현재 assistant 응답을 스트리밍하고 있습니다\./)).toBeInTheDocument();
    expect(screen.getByText(/thinking/i)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /used/i })).not.toBeInTheDocument();
  });

  it("renders approval messages with approve and block actions", () => {
    const onApprovalResponse = vi.fn();
    const message: UIMessage = {
      id: "a1",
      role: "assistant",
      kind: "approval",
      content: "Approval required for a high-risk command.",
      createdAt: Date.now(),
    };

    render(<MessageBubble message={message} onApprovalResponse={onApprovalResponse} />);

    fireEvent.click(screen.getByRole("button", { name: /approve/i }));
    expect(onApprovalResponse).toHaveBeenCalledWith("a1", "yes");
  });

  it("renders status footers as compact inline status text", () => {
    const message: UIMessage = {
      id: "s1",
      role: "assistant",
      content:
        "Status: model=LiquidAI/LFM2-24B-A2B-GGUF:Q4_0 | target=local-llm | tokens=🔵30377 in/🟢656 out | total=🟠31033 | cached=🟣29702 | context=🟡31k/⚪65k",
      createdAt: Date.now(),
    };

    render(<MessageBubble message={message} />);

    expect(screen.getByText(/model=LiquidAI\/LFM2-24B-A2B-GGUF:Q4_0/)).toBeInTheDocument();
    expect(screen.getByText(/target=local-llm/)).toBeInTheDocument();
    expect(screen.getByText(/tokens=🔵30377 in\/🟢656 out/)).toBeInTheDocument();
  });

  it("renders render_as=text assistant replies without markdown conversion", () => {
    const message: UIMessage = {
      id: "plain-text-help",
      role: "assistant",
      content: "## Help\n/status — Show status\n/help — Show help",
      renderAs: "text",
      createdAt: Date.now(),
    };

    const { container } = render(<MessageBubble message={message} />);

    expect(screen.getByText(/## Help/)).toBeInTheDocument();
    expect(screen.getByText(/\/status — Show status/)).toBeInTheDocument();
    expect(container.querySelector("h2")).not.toBeInTheDocument();
    expect(container.querySelector(".whitespace-pre-wrap")).toBeTruthy();
  });

  it("renders video media as an inline player", () => {
    const message: UIMessage = {
      id: "a1",
      role: "assistant",
      content: "here is the clip",
      createdAt: Date.now(),
      media: [
        {
          kind: "video",
          url: "/api/media/sig/payload",
          name: "demo.mp4",
        },
      ],
    };

    const { container } = render(<MessageBubble message={message} />);

    expect(screen.getByText("here is the clip")).toBeInTheDocument();
    const video = screen.getByLabelText(/video attachment/i);
    expect(video.tagName).toBe("VIDEO");
    expect(video).toHaveAttribute("src", "/api/media/sig/payload");
    expect(container.querySelector("video[controls]")).toBeInTheDocument();
  });

  it("renders assistant image media as a larger generated result", () => {
    const message: UIMessage = {
      id: "a-image",
      role: "assistant",
      content: "done",
      createdAt: Date.now(),
      media: [
        {
          kind: "image",
          url: "/api/media/sig/image",
          name: "generated.png",
        },
      ],
    };

    const { container } = render(<MessageBubble message={message} />);

    const imageButton = screen.getByRole("button", { name: /view image/i });
    expect(imageButton).toHaveClass("h-56", "sm:h-72");
    expect(container.querySelector("img")).toHaveClass("object-contain");
  });
});
