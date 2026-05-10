import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { ThreadStatusBlock } from "@/components/thread/ThreadStatusBlock";

describe("ThreadStatusBlock", () => {
  it("renders running status as an expanded reasoning card in summary mode", () => {
    render(
      <ThreadStatusBlock
        tone="running"
        title="Task is in progress"
        body="Generating the current response."
        reasoningVisibility="summary"
      />,
    );

    expect(screen.getByRole("button", { name: /task is in progress/i })).toHaveAttribute("aria-expanded", "true");
    expect(screen.getAllByText(/generating the current response/i).length).toBeGreaterThan(0);
  });

  it("hides reasoning fallback cards when reasoning visibility is off", () => {
    const { container } = render(
      <ThreadStatusBlock
        tone="running"
        title="Task is in progress"
        body="Generating the current response."
        reasoningVisibility="off"
      />,
    );

    expect(container).toBeEmptyDOMElement();
  });

  it("renders completed status as a collapsed summary card that can expand", () => {
    render(
      <ThreadStatusBlock
        tone="completed"
        title="Latest update is ready"
        body="The most recent response finished successfully."
        reasoningVisibility="summary"
      />,
    );

    const toggle = screen.getByRole("button", { name: /latest update is ready/i });
    expect(toggle).toHaveAttribute("aria-expanded", "false");

    fireEvent.click(toggle);
    expect(toggle).toHaveAttribute("aria-expanded", "true");
  });

  it("keeps waiting-approval status visible even when reasoning visibility is off", () => {
    render(
      <ThreadStatusBlock
        tone="waiting-approval"
        title="Task needs confirmation"
        body="Review the pending action and choose how to continue."
        reasoningVisibility="off"
      />,
    );

    expect(screen.getByText(/task needs confirmation/i)).toBeInTheDocument();
  });
});