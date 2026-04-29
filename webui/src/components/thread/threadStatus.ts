import type { StreamError } from "@/lib/nanobot-client";
import type { UIMessage } from "@/lib/types";

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
  } = params;

  if (streamError) {
    if (streamError.kind === "message_too_big") {
      return {
        tone: "failed",
        title: "Message rejected",
        body: "The last message exceeded the upload size limit. Remove some attachments or use smaller files, then try again.",
      };
    }
  }

  const approvalSource = pendingApprovalMessage?.content || pendingAsk?.question || "";
  if (pendingApprovalMessage || pendingAsk) {
    return {
      tone: "waiting-approval",
      title: "Assistant is waiting for confirmation",
      body: summarizeStatusText(approvalSource, "Review the pending action and choose how to continue."),
    };
  }

  if (modelTargetPending || booting || remoteReplyPending || isStreaming) {
    return {
      tone: "running",
      title: "Assistant is working",
      body: modelTargetPending
        ? "Applying the selected target for this session."
        : booting
          ? "Preparing the new chat before sending your first message."
          : remoteReplyPending
            ? "Waiting for the linked external session to return a reply."
            : "Streaming the current assistant response.",
    };
  }

  const lastMeaningful = [...messages].reverse().find(
    (message) => message.kind !== "trace" && message.role !== "user",
  );
  if (!lastMeaningful) return null;

  return {
    tone: "completed",
    title: "Latest assistant update is ready",
    body: summarizeStatusText(lastMeaningful.content, "The most recent assistant turn finished successfully."),
  };
}

function summarizeStatusText(content: string, fallback: string): string {
  const normalized = content.replace(/\s+/g, " ").trim();
  if (!normalized) return fallback;
  return normalized.length > 140 ? `${normalized.slice(0, 137)}...` : normalized;
}