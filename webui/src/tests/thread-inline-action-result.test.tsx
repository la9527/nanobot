import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { ThreadInlineActionResult } from "@/components/thread/ThreadInlineActionResult";

describe("ThreadInlineActionResult", () => {
  it("keeps mail preview details hidden until the user opens them", () => {
    render(
      <ThreadInlineActionResult
        domain="mail"
        status="completed"
        title="Draft ready"
        summary="Draft created for alice@example.com."
        preview={{
          subject: "Budget follow-up",
          body_preview: "Sharing the revised budget.",
          to_recipients: ["alice@example.com"],
        }}
      />,
    );

    expect(screen.getByText(/Draft ready\. Draft created for alice@example.com\./)).toBeInTheDocument();
    expect(screen.queryByText("Mail result")).not.toBeInTheDocument();
    expect(screen.queryByText(/To:/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/Subject:/i)).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Details" }));

    expect(screen.getByText(/To:/i)).toBeInTheDocument();
    expect(screen.getByText(/Subject:/i)).toBeInTheDocument();
    expect(screen.getByText(/Budget follow-up/)).toBeInTheDocument();
  });

  it("shows a details tooltip on the info icon", async () => {
    const user = userEvent.setup();

    render(
      <ThreadInlineActionResult
        domain="calendar"
        status="completed"
        title="Calendar event created"
        summary="5.2. 15:00부터 5.2. 16:00까지 치과 일정을 생성했습니다."
        preview={{
          title: "치과",
          start_at: "2026-05-02T15:00:00+09:00",
          end_at: "2026-05-02T16:00:00+09:00",
        }}
      />,
    );

    await user.hover(screen.getByRole("button", { name: "Details" }));

    expect(await screen.findByRole("tooltip")).toHaveTextContent("Details");
  });

  it("keeps calendar conflict details hidden until requested", () => {
    render(
      <ThreadInlineActionResult
        domain="calendar"
        status="blocked"
        title="Conflicts found"
        summary="The requested slot overlaps with 프로젝트 리뷰."
        conflict={{
          requestedStartAt: "2026-05-02T15:00:00+09:00",
          requestedEndAt: "2026-05-02T16:00:00+09:00",
          reason: "overlap_detected",
          conflictingEvents: [
            {
              event_id: "event-1",
              title: "프로젝트 리뷰",
              start_at: "2026-05-02T15:00:00+09:00",
              end_at: "2026-05-02T16:00:00+09:00",
            },
          ],
        }}
      />,
    );

    expect(screen.queryByText("Calendar result")).not.toBeInTheDocument();
    expect(screen.getByText(/Conflicts found\. The requested slot overlaps with 프로젝트 리뷰\./)).toBeInTheDocument();
    expect(screen.queryByText(/Reason:/i)).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Details" }));

    expect(screen.getByText(/Reason:/i)).toBeInTheDocument();
    expect(screen.getAllByText(/프로젝트 리뷰/)).toHaveLength(2);
  });
});