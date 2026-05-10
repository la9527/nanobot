import type { StreamError } from "@/lib/nanobot-client";
import type { DerivedActionResult } from "@/lib/sessionMetadata";
import type { UIMessage } from "@/lib/types";
import i18n from "@/i18n";

import type { ThreadStatusTone } from "@/components/thread/ThreadStatusBlock";

export interface DerivedThreadStatus {
  tone: ThreadStatusTone;
  title: string;
  body: string;
}

export function injectSyntheticReasoningTrace(params: {
  messages: UIMessage[];
  statusLine: string | null;
  isStreaming: boolean;
  cacheKey: string | null;
}): UIMessage[] {
  const { messages, statusLine, isStreaming, cacheKey } = params;
  const line = statusLine?.trim();
  if (!line || messages.length === 0 || !cacheKey) return messages;

  const lastUserIndex = findLastIndex(messages, (message) => message.role === "user");
  if (lastUserIndex < 0) return messages;

  const lastAssistantIndex = findLastIndex(
    messages,
    (message, index) => index > lastUserIndex && message.role === "assistant",
  );
  const turnSlice = messages.slice(lastUserIndex + 1);
  if (turnSlice.some((message) => message.kind === "trace")) return messages;

  const syntheticTrace: UIMessage = {
    id: `reasoning-status:${cacheKey}:${lastUserIndex}:${lastAssistantIndex >= 0 ? "assistant" : "pending"}`,
    role: "tool",
    kind: "trace",
    traceVariant: "status",
    content: line,
    traces: [line],
    isStreaming,
    createdAt: lastAssistantIndex >= 0
      ? Math.max(0, messages[lastAssistantIndex].createdAt - 1)
      : Date.now(),
  };

  if (lastAssistantIndex >= 0) {
    return [
      ...messages.slice(0, lastAssistantIndex),
      syntheticTrace,
      ...messages.slice(lastAssistantIndex),
    ];
  }

  return [...messages, syntheticTrace];
}

export function deriveThreadStatus(params: {
  messages: UIMessage[];
  pendingAsk: { question: string; buttons: string[][] } | null;
  pendingApprovalMessage: UIMessage | null;
  streamError: StreamError | null;
  isStreaming: boolean;
  remoteReplyPending: boolean;
  booting: boolean;
  modelTargetPending: boolean;
  actionResult?: DerivedActionResult | null;
}): DerivedThreadStatus | null {
  const {
    messages,
    pendingAsk,
    pendingApprovalMessage,
    streamError,
    isStreaming,
    remoteReplyPending,
    booting,
    modelTargetPending,
    actionResult,
  } = params;

  if (streamError) {
    if (streamError.kind === "message_too_big") {
      return {
        tone: "failed",
        title: i18n.t("thread.statusSummary.error.messageRejected"),
        body: i18n.t("thread.statusSummary.error.messageTooBig"),
      };
    }
  }

  const approvalSource = pendingApprovalMessage?.content || pendingAsk?.question || "";
  if (pendingApprovalMessage || pendingAsk) {
    return {
      tone: "waiting-approval",
      title: i18n.t("thread.statusSummary.waitingApproval.title"),
      body: summarizeStatusText(approvalSource, i18n.t("thread.statusSummary.waitingApproval.body")),
    };
  }

  if (modelTargetPending || booting || remoteReplyPending || isStreaming) {
    return {
      tone: "running",
      title: i18n.t("thread.statusSummary.running.title"),
      body: modelTargetPending
        ? i18n.t("thread.statusSummary.running.applyingTarget")
        : booting
          ? i18n.t("thread.statusSummary.running.preparingChat")
          : remoteReplyPending
            ? i18n.t("thread.statusSummary.running.waitingExternal")
            : i18n.t("thread.statusSummary.running.streaming"),
    };
  }

  const lastMeaningful = [...messages].reverse().find(
    (message) => message.kind !== "trace" && message.role !== "user",
  );
  if (lastMeaningful) {
    return {
      tone: "completed",
      title: i18n.t("thread.statusSummary.completed.latestUpdateTitle"),
      body: summarizeStatusText(lastMeaningful.content, i18n.t("thread.statusSummary.completed.latestUpdateBody")),
    };
  }

  if (actionResult?.title || actionResult?.summary) {
    const status = actionResult.status;
    const tone: ThreadStatusTone =
      status === "running"
        ? "running"
        : status === "waiting_approval"
          ? "waiting-approval"
          : status === "failed" || status === "blocked" || status === "rejected"
            ? "failed"
            : "completed";
    return {
      tone,
      title: actionResult.title || i18n.t("thread.statusSummary.completed.latestActionTitle"),
      body: summarizeStatusText(
        actionResult.summary
          || actionResult.inlineStatus
          || actionResult.errorMessage
          || actionResult.nextStep
          || i18n.t("thread.statusSummary.completed.latestActionBody"),
        i18n.t("thread.statusSummary.completed.latestActionBody"),
      ),
    };
  }

  return null;
}

function summarizeStatusText(content: string, fallback: string): string {
  const normalized = content.replace(/\s+/g, " ").trim();
  if (!normalized) return fallback;
  return normalized.length > 140 ? `${normalized.slice(0, 137)}...` : normalized;
}

function findLastIndex<T>(items: T[], predicate: (item: T, index: number) => boolean): number {
  for (let index = items.length - 1; index >= 0; index -= 1) {
    if (predicate(items[index], index)) return index;
  }
  return -1;
}