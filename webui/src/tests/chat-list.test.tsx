import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { ChatList } from "@/components/ChatList";
import type { ChatSummary } from "@/lib/types";

describe("ChatList", () => {
  it("shows an approval pending badge for sessions with pending approval metadata", () => {
    const sessions: ChatSummary[] = [
      {
        key: "telegram:12345",
        channel: "telegram",
        chatId: "12345",
        createdAt: "2026-04-30T10:00:00Z",
        updatedAt: "2026-04-30T10:01:00Z",
        preview: "Telegram approval",
        metadata: {
          approval_summary: {
            status: "pending",
            channel: "telegram",
            tool_name: "exec",
            tool_call_id: "call-1",
            prompt_preview: "Approval required for a high-risk command.",
          },
        },
      },
    ];

    render(
      <ChatList
        sessions={sessions}
        activeKey={null}
        onSelect={vi.fn()}
        onRequestDelete={vi.fn()}
      />,
    );

    expect(screen.getByText("Approval pending")).toBeInTheDocument();
    expect(screen.getByText("Telegram approval")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Approval pending" }));

    expect(
      screen.getByText("exec: Approval required for a high-risk command."),
    ).toBeInTheDocument();
  });
});