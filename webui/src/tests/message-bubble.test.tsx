import { fireEvent, render, screen } from "@testing-library/react";
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
  });

  it("renders trace messages as collapsible tool groups", () => {
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

    expect(screen.getByText('weather("get")')).toBeInTheDocument();
    expect(screen.getByText('search "hk weather"')).toBeInTheDocument();

    fireEvent.click(toggle);
    expect(screen.queryByText('weather("get")')).not.toBeInTheDocument();
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
});
