import { describe, expect, it } from "vitest";

import { deriveThreadStatus, injectSyntheticReasoningTrace } from "@/components/thread/threadStatus";
import type { UIMessage } from "@/lib/types";

describe("deriveThreadStatus", () => {
  it("prefers the latest assistant reply over stale action results for completed summaries", () => {
    const messages: UIMessage[] = [
      {
        id: "user-1",
        role: "user",
        content: "check weather",
        createdAt: Date.now() - 1_000,
      },
      {
        id: "assistant-1",
        role: "assistant",
        content: "The latest weather summary is ready.",
        createdAt: Date.now(),
      },
    ];

    const status = deriveThreadStatus({
      messages,
      pendingAsk: null,
      pendingApprovalMessage: null,
      streamError: null,
      isStreaming: false,
      remoteReplyPending: false,
      booting: false,
      modelTargetPending: false,
      actionResult: {
        actionId: null,
        domain: "calendar",
        action: "create_event",
        status: "rejected",
        title: "Calendar create cancelled",
        summary: "The pending calendar create request was cancelled.",
        nextStep: null,
        badge: null,
        inlineStatus: null,
        linkedSummary: null,
        errorCode: null,
        errorMessage: null,
      },
    });

    expect(status).toMatchObject({
      tone: "completed",
      title: "Latest update is ready",
      body: "The latest weather summary is ready.",
    });
  });

  it("injects a one-line synthetic reasoning trace before the latest assistant reply", () => {
    const messages: UIMessage[] = [
      {
        id: "user-1",
        role: "user",
        content: "check weather",
        createdAt: 1,
      },
      {
        id: "assistant-1",
        role: "assistant",
        content: "The weather is sunny.",
        createdAt: 2,
      },
    ];

    const next = injectSyntheticReasoningTrace({
      messages,
      statusLine: "현재 응답을 생성하고 있습니다.",
      isStreaming: false,
      cacheKey: "websocket:chat-a",
    });

    expect(next).toHaveLength(3);
    expect(next[1]).toMatchObject({
      kind: "trace",
      traceVariant: "status",
      content: "현재 응답을 생성하고 있습니다.",
    });
    expect(next[2].content).toBe("The weather is sunny.");
  });

  it("does not inject a synthetic reasoning trace when the turn already has real trace rows", () => {
    const messages: UIMessage[] = [
      {
        id: "user-1",
        role: "user",
        content: "check weather",
        createdAt: 1,
      },
      {
        id: "trace-1",
        role: "tool",
        kind: "trace",
        content: "searching workspace",
        traces: ["searching workspace"],
        createdAt: 2,
      },
      {
        id: "assistant-1",
        role: "assistant",
        content: "The weather is sunny.",
        createdAt: 3,
      },
    ];

    const next = injectSyntheticReasoningTrace({
      messages,
      statusLine: "현재 응답을 생성하고 있습니다.",
      isStreaming: false,
      cacheKey: "websocket:chat-a",
    });

    expect(next).toEqual(messages);
  });
});