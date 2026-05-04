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

  const lastMeaningful = [...messages].reverse().find(
    (message) => message.kind !== "trace" && message.role !== "user",
  );
  if (!lastMeaningful) return null;

  return {
    tone: "completed",
    title: i18n.t("thread.statusSummary.completed.latestUpdateTitle"),
    body: summarizeStatusText(lastMeaningful.content, i18n.t("thread.statusSummary.completed.latestUpdateBody")),
  };
}

function summarizeStatusText(content: string, fallback: string): string {
  const normalized = content.replace(/\s+/g, " ").trim();
  if (!normalized) return fallback;
  return normalized.length > 140 ? `${normalized.slice(0, 137)}...` : normalized;
}