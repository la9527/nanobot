import { render, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ThreadViewport } from "@/components/thread/ThreadViewport";
import type { UIMessage } from "@/lib/types";

const resizeObserverCallbacks = new Set<ResizeObserverCallback>();

class ResizeObserverStub {
  callback: ResizeObserverCallback;

  constructor(callback: ResizeObserverCallback) {
    this.callback = callback;
    resizeObserverCallbacks.add(callback);
  }

  observe() {}

  disconnect() {
    resizeObserverCallbacks.delete(this.callback);
  }
}

describe("ThreadViewport", () => {
  beforeEach(() => {
    resizeObserverCallbacks.clear();
    vi.stubGlobal("ResizeObserver", ResizeObserverStub);
    HTMLElement.prototype.scrollTo = vi.fn();
  });

  it("pins to the bottom when the first loaded messages appear", async () => {
    const { rerender } = render(
      <ThreadViewport
        messages={[]}
        isStreaming={false}
        composer={<div>composer</div>}
      />,
    );

    const messages: UIMessage[] = [
      {
        id: "m1",
        role: "assistant",
        content: "hello",
        createdAt: Date.now(),
      },
    ];

    rerender(
      <ThreadViewport
        messages={messages}
        isStreaming={false}
        composer={<div>composer</div>}
      />,
    );

    await waitFor(() => {
      expect(HTMLElement.prototype.scrollTo).toHaveBeenCalled();
    });
  });

  it("re-pins to the bottom when content height grows after initial load", async () => {
    const messages: UIMessage[] = [
      {
        id: "m1",
        role: "assistant",
        content: "hello",
        createdAt: Date.now(),
      },
    ];

    render(
      <ThreadViewport
        messages={messages}
        isStreaming={false}
        composer={<div>composer</div>}
      />,
    );

    const callsBeforeResize = vi.mocked(HTMLElement.prototype.scrollTo).mock.calls.length;

    resizeObserverCallbacks.forEach((callback) => {
      callback([], {} as ResizeObserver);
    });

    await waitFor(() => {
      expect(vi.mocked(HTMLElement.prototype.scrollTo).mock.calls.length).toBeGreaterThan(callsBeforeResize);
    });
  });
});