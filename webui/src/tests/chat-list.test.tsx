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
    expect(screen.getByText("Telegram")).toBeInTheDocument();
    expect(screen.getByText("Telegram approval")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Approval pending" }));

    expect(
      screen.getByText("exec: Approval required for a high-risk command."),
    ).toBeInTheDocument();
  });

  it("shows compact calendar approval details instead of raw prompt text", () => {
    const sessions: ChatSummary[] = [
      {
        key: "websocket:calendar-demo",
        channel: "websocket",
        chatId: "calendar-demo",
        createdAt: "2026-05-02T10:00:00Z",
        updatedAt: "2026-05-02T10:01:00Z",
        preview: "Calendar approval",
        metadata: {
          calendar_create_approval: {
            title: "Nanobot webui calendar validation",
            start_at: "2026-05-04T14:00:00+09:00",
            end_at: "2026-05-04T14:30:00+09:00",
          },
          approval_summary: {
            status: "pending",
            channel: "websocket",
            tool_name: "calendar.create_event",
            tool_call_id: "call-1",
            prompt_preview:
              "Approval required before creating this calendar event. Title: Nanobot webui calendar validation. Start: 2026-05-04T14:00:00+09:00. End: 2026-05-04T14:30:00+09:00. Use /calendar approve to create it or /calendar deny to cancel.",
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

    fireEvent.click(screen.getByRole("button", { name: "Approval pending" }));

    expect(
      screen.getByText(
        "Calendar create approval pending: Nanobot webui calendar validation (2026-05-04T14:00:00+09:00 -> 2026-05-04T14:30:00+09:00)",
      ),
    ).toBeInTheDocument();
    expect(screen.queryByText(/Use \/calendar approve/)).not.toBeInTheDocument();
  });
});