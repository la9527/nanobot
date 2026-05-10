import type { ChatSummary } from "@/lib/types";
import i18n from "@/i18n";

export interface DerivedTaskSummary {
  taskId: string | null;
  canonicalOwnerId: string | null;
  title: string | null;
  status: string | null;
  originChannel: string | null;
  originSessionKey: string | null;
  updatedAt: string | null;
  nextStepHint: string | null;
}

export interface DerivedOwnerProfile {
  canonicalOwnerId: string | null;
  preferredLanguage: string | null;
  timezone: string | null;
  responseTone: string | null;
  responseLength: string | null;
}

export interface DerivedMemoryCorrectionAction {
  code: string | null;
  phrase: string | null;
  target: string | null;
  store: string | null;
}

export interface DerivedActionResult {
  actionId: string | null;
  domain: string | null;
  action: string | null;
  status: string | null;
  title: string | null;
  summary: string | null;
  nextStep: string | null;
  badge: string | null;
  inlineStatus: string | null;
  linkedSummary: string | null;
  errorCode: string | null;
  errorMessage: string | null;
}

export interface DerivedProactiveSummary {
  status: string | null;
  category: string | null;
  title: string | null;
  summary: string | null;
  targetChannel: string | null;
  suppressedReason: string | null;
  updatedAt: string | null;
}

export interface DerivedPendingInteraction {
  id: string | null;
  domain: "calendar";
  kind: string | null;
  status: string | null;
  question: string | null;
  buttons: string[][];
}

type ActionResultMetadata = NonNullable<NonNullable<ChatSummary["metadata"]>["action_result"]>;
type ActionResultDetails = NonNullable<ActionResultMetadata["details"]>;

function cleanText(value: string | null | undefined): string | null {
  const text = String(value || "").trim();
  return text || null;
}

const GENERIC_COMPLETED_NEXT_STEP_HINTS = new Set([
  "Review the latest completed update if follow-up is needed.",
  "The request was cancelled; no follow-up is needed unless you start it again.",
  "최신 완료 내용을 검토하고 필요하면 후속 조치를 진행하세요.",
  "요청이 취소되었습니다. 다시 시작하지 않는 한 추가 조치는 필요 없습니다.",
]);

function normalizeTaskNextStepHint(
  status: string | null | undefined,
  hint: string | null | undefined,
): string | null {
  const cleanedHint = cleanText(hint);
  if (!cleanedHint) return null;
  const normalizedStatus = cleanText(status)?.toLowerCase();
  if (normalizedStatus === "completed" && GENERIC_COMPLETED_NEXT_STEP_HINTS.has(cleanedHint)) {
    return null;
  }
  return cleanedHint;
}

function normalizeActionStatus(status: string | null | undefined): string | null {
  const normalized = cleanText(status)?.toLowerCase().replaceAll("-", "_");
  return normalized || null;
}

function shouldLocalizeActionResultText(): boolean {
  return i18n.resolvedLanguage?.toLowerCase().startsWith("ko") ?? false;
}

function previewTitle(details: ActionResultDetails | undefined): string | null {
  return cleanText(details?.preview?.title) || cleanText(details?.preview?.subject);
}

function previewRecipients(details: ActionResultDetails | undefined): string | null {
  const recipients = details?.preview?.to_recipients
    ?.map((recipient) => cleanText(recipient))
    .filter((recipient): recipient is string => Boolean(recipient));
  return recipients?.length ? recipients.join(", ") : null;
}

function localizeCalendarActionResult(actionResult: ActionResultMetadata): Partial<DerivedActionResult> {
  const action = cleanText(actionResult.action);
  const status = normalizeActionStatus(actionResult.status);
  const errorCode = cleanText(actionResult.error?.code)?.toLowerCase();
  const details = actionResult.details;
  const fallbackTitle = previewTitle(details) || i18n.t("thread.inlineAction.fallback.untitledEvent");

  if (action === "create_event") {
    if (status === "waiting_approval") {
      return {
        title: i18n.t("thread.inlineAction.result.calendar.create.approval.title"),
        summary: i18n.t("thread.inlineAction.result.calendar.create.approval.summary", { title: fallbackTitle }),
        nextStep: i18n.t("thread.inlineAction.result.calendar.create.approval.nextStep"),
        inlineStatus: i18n.t("thread.inlineAction.result.calendar.create.approval.title"),
      };
    }
    if (status === "rejected" && errorCode === "approval_rejected") {
      return {
        title: i18n.t("thread.inlineAction.result.calendar.create.cancelled.title"),
        summary: i18n.t("thread.inlineAction.result.calendar.create.cancelled.summary"),
        nextStep: i18n.t("thread.inlineAction.result.calendar.create.cancelled.nextStep"),
        inlineStatus: i18n.t("thread.inlineAction.result.calendar.create.cancelled.title"),
      };
    }
    if (status === "blocked" && errorCode === "not_found") {
      return {
        title: i18n.t("thread.inlineAction.result.calendar.create.noPending.title"),
        summary: i18n.t("thread.inlineAction.result.calendar.create.noPending.summary"),
        nextStep: i18n.t("thread.inlineAction.result.calendar.create.noPending.nextStep"),
        inlineStatus: i18n.t("thread.inlineAction.result.calendar.create.noPending.title"),
      };
    }
    if (status === "completed") {
      return {
        title: i18n.t("thread.inlineAction.result.calendar.create.created.title"),
        summary: i18n.t("thread.inlineAction.result.calendar.create.created.summary", { title: fallbackTitle }),
        inlineStatus: i18n.t("thread.inlineAction.result.calendar.create.created.title"),
      };
    }
    if (status === "failed") {
      return {
        title: i18n.t("thread.inlineAction.result.calendar.create.failed.title"),
      };
    }
  }

  if (action === "update_event") {
    if (status === "waiting_approval") {
      return {
        title: i18n.t("thread.inlineAction.result.calendar.update.approval.title"),
        summary: i18n.t("thread.inlineAction.result.calendar.update.approval.summary", { title: fallbackTitle }),
        nextStep: i18n.t("thread.inlineAction.result.calendar.update.approval.nextStep"),
        inlineStatus: i18n.t("thread.inlineAction.result.calendar.update.approval.title"),
      };
    }
    if (status === "rejected" && errorCode === "approval_rejected") {
      return {
        title: i18n.t("thread.inlineAction.result.calendar.update.cancelled.title"),
        summary: i18n.t("thread.inlineAction.result.calendar.update.cancelled.summary"),
        nextStep: i18n.t("thread.inlineAction.result.calendar.update.cancelled.nextStep"),
        inlineStatus: i18n.t("thread.inlineAction.result.calendar.update.cancelled.title"),
      };
    }
    if (status === "blocked" && errorCode === "not_found") {
      return {
        title: i18n.t("thread.inlineAction.result.calendar.update.noPending.title"),
        summary: i18n.t("thread.inlineAction.result.calendar.update.noPending.summary"),
        nextStep: i18n.t("thread.inlineAction.result.calendar.update.noPending.nextStep"),
        inlineStatus: i18n.t("thread.inlineAction.result.calendar.update.noPending.title"),
      };
    }
    if (status === "completed") {
      return {
        title: i18n.t("thread.inlineAction.result.calendar.update.updated.title"),
        summary: i18n.t("thread.inlineAction.result.calendar.update.updated.summary", { title: fallbackTitle }),
        inlineStatus: i18n.t("thread.inlineAction.result.calendar.update.updated.title"),
      };
    }
    if (status === "failed") {
      return {
        title: i18n.t("thread.inlineAction.result.calendar.update.failed.title"),
      };
    }
  }

  if (action === "delete_event") {
    if (status === "waiting_approval") {
      return {
        title: i18n.t("thread.inlineAction.result.calendar.delete.approval.title"),
        summary: i18n.t("thread.inlineAction.result.calendar.delete.approval.summary", { title: fallbackTitle }),
        nextStep: i18n.t("thread.inlineAction.result.calendar.delete.approval.nextStep"),
        inlineStatus: i18n.t("thread.inlineAction.result.calendar.delete.approval.title"),
      };
    }
    if (status === "rejected" && errorCode === "approval_rejected") {
      return {
        title: i18n.t("thread.inlineAction.result.calendar.delete.cancelled.title"),
        summary: i18n.t("thread.inlineAction.result.calendar.delete.cancelled.summary"),
        nextStep: i18n.t("thread.inlineAction.result.calendar.delete.cancelled.nextStep"),
        inlineStatus: i18n.t("thread.inlineAction.result.calendar.delete.cancelled.title"),
      };
    }
    if (status === "blocked" && errorCode === "not_found") {
      return {
        title: i18n.t("thread.inlineAction.result.calendar.delete.noPending.title"),
        summary: i18n.t("thread.inlineAction.result.calendar.delete.noPending.summary"),
        nextStep: i18n.t("thread.inlineAction.result.calendar.delete.noPending.nextStep"),
        inlineStatus: i18n.t("thread.inlineAction.result.calendar.delete.noPending.title"),
      };
    }
    if (status === "completed") {
      return {
        title: i18n.t("thread.inlineAction.result.calendar.delete.deleted.title"),
        summary: i18n.t("thread.inlineAction.result.calendar.delete.deleted.summary", { title: fallbackTitle }),
        inlineStatus: i18n.t("thread.inlineAction.result.calendar.delete.deleted.title"),
      };
    }
    if (status === "failed") {
      return {
        title: i18n.t("thread.inlineAction.result.calendar.delete.failed.title"),
      };
    }
  }

  return {};
}

function localizeMailActionResult(actionResult: ActionResultMetadata): Partial<DerivedActionResult> {
  const action = cleanText(actionResult.action);
  const status = normalizeActionStatus(actionResult.status);
  const errorCode = cleanText(actionResult.error?.code)?.toLowerCase();
  const actionId = cleanText(actionResult.action_id)?.toLowerCase() || "";
  const details = actionResult.details;
  const recipients = previewRecipients(details) || i18n.t("thread.inlineAction.fallback.noSummary");
  const subject = cleanText(details?.preview?.subject) || i18n.t("thread.inlineAction.fallback.noSubject");
  const threadCount = details?.threads?.length ?? 0;

  if (action === "list_important_threads") {
    if (status === "completed" && threadCount > 0) {
      return {
        title: i18n.t("thread.inlineAction.result.mail.list.ready.title"),
        summary: i18n.t("thread.inlineAction.result.mail.list.ready.summary", { count: threadCount }),
        nextStep: i18n.t("thread.inlineAction.result.mail.list.nextStep"),
        inlineStatus: i18n.t("thread.inlineAction.result.mail.list.ready.title"),
      };
    }
    if (status === "completed") {
      return {
        title: i18n.t("thread.inlineAction.result.mail.list.empty.title"),
        summary: i18n.t("thread.inlineAction.result.mail.list.empty.summary"),
        inlineStatus: i18n.t("thread.inlineAction.result.mail.list.empty.title"),
      };
    }
    return {
      title: i18n.t("thread.inlineAction.result.mail.list.unavailable.title"),
    };
  }

  if (action === "summarize_threads") {
    if (status === "completed") {
      return {
        title: i18n.t("thread.inlineAction.result.mail.summaries.ready.title"),
        summary: i18n.t("thread.inlineAction.result.mail.summaries.ready.summary", { count: threadCount }),
        nextStep: i18n.t("thread.inlineAction.result.mail.summaries.nextStep"),
        inlineStatus: i18n.t("thread.inlineAction.result.mail.summaries.ready.title"),
      };
    }
    if (errorCode === "not_found") {
      return {
        title: i18n.t("thread.inlineAction.result.mail.summaries.unavailable.title"),
        summary: i18n.t("thread.inlineAction.result.mail.summaries.unavailable.summary"),
        inlineStatus: i18n.t("thread.inlineAction.result.mail.summaries.unavailable.title"),
      };
    }
  }

  if (action === "create_draft") {
    if (status === "completed") {
      return {
        title: i18n.t("thread.inlineAction.result.mail.draft.ready.title"),
        summary: i18n.t("thread.inlineAction.result.mail.draft.ready.summary", { recipients }),
        nextStep: i18n.t("thread.inlineAction.result.mail.draft.ready.nextStep"),
        inlineStatus: i18n.t("thread.inlineAction.result.mail.draft.ready.title"),
      };
    }
    return {
      title: i18n.t("thread.inlineAction.result.mail.draft.failed.title"),
    };
  }

  if (action === "send_message") {
    if (status === "waiting_approval") {
      return {
        title: i18n.t("thread.inlineAction.result.mail.send.approval.title"),
        summary: i18n.t("thread.inlineAction.result.mail.send.approval.summary", { subject, recipients }),
        nextStep: i18n.t("thread.inlineAction.result.mail.send.approval.nextStep"),
        inlineStatus: i18n.t("thread.inlineAction.result.mail.send.approval.inlineStatus"),
      };
    }
    if (status === "blocked" && actionId.includes("missing-draft")) {
      return {
        title: i18n.t("thread.inlineAction.result.mail.send.noDraft.title"),
        summary: i18n.t("thread.inlineAction.result.mail.send.noDraft.summary"),
        nextStep: i18n.t("thread.inlineAction.result.mail.send.noDraft.nextStep"),
        inlineStatus: i18n.t("thread.inlineAction.result.mail.send.noDraft.title"),
      };
    }
    if (status === "blocked" && actionId.includes("no-pending")) {
      return {
        title: i18n.t("thread.inlineAction.result.mail.send.noPending.title"),
        summary: i18n.t("thread.inlineAction.result.mail.send.noPending.summary"),
        nextStep: i18n.t("thread.inlineAction.result.mail.send.noPending.nextStep"),
        inlineStatus: i18n.t("thread.inlineAction.result.mail.send.noPending.title"),
      };
    }
    if (status === "rejected" && errorCode === "approval_rejected") {
      return {
        title: i18n.t("thread.inlineAction.result.mail.send.cancelled.title"),
        summary: i18n.t("thread.inlineAction.result.mail.send.cancelled.summary"),
        nextStep: i18n.t("thread.inlineAction.result.mail.send.cancelled.nextStep"),
        inlineStatus: i18n.t("thread.inlineAction.result.mail.send.cancelled.title"),
      };
    }
    if (status === "completed") {
      return {
        title: i18n.t("thread.inlineAction.result.mail.send.sent.title"),
        summary: i18n.t("thread.inlineAction.result.mail.send.sent.summary", { recipients }),
        inlineStatus: i18n.t("thread.inlineAction.result.mail.send.sent.title"),
      };
    }
    return {
      title: i18n.t("thread.inlineAction.result.mail.send.failed.title"),
    };
  }

  return {};
}

function localizeActionErrorMessage(actionResult: ActionResultMetadata): string | null {
  if (!shouldLocalizeActionResultText()) {
    return cleanText(actionResult.error?.message);
  }

  const domain = cleanText(actionResult.domain);
  const errorCode = cleanText(actionResult.error?.code)?.toLowerCase();
  if (!errorCode) return cleanText(actionResult.error?.message);

  if (domain === "calendar") {
    if (errorCode === "approval_needed") return i18n.t("thread.inlineAction.error.calendar.approval_needed");
    if (errorCode === "approval_rejected") return i18n.t("thread.inlineAction.error.calendar.approval_rejected");
    if (errorCode === "not_found") return i18n.t("thread.inlineAction.error.calendar.not_found");
    if (errorCode === "authentication_needed") return i18n.t("thread.inlineAction.error.calendar.authentication_needed");
    if (errorCode === "rate_limited") return i18n.t("thread.inlineAction.error.calendar.rate_limited");
    if (errorCode === "service_unavailable" || errorCode === "executor_unavailable") {
      return i18n.t("thread.inlineAction.error.calendar.service_unavailable");
    }
  }

  if (domain === "mail") {
    if (errorCode === "approval_needed") return i18n.t("thread.inlineAction.error.mail.approval_needed");
    if (errorCode === "approval_rejected") return i18n.t("thread.inlineAction.error.mail.approval_rejected");
    if (errorCode === "authentication_needed") return i18n.t("thread.inlineAction.error.mail.authentication_needed");
    if (errorCode === "executor_unavailable") return i18n.t("thread.inlineAction.error.mail.executor_unavailable");
    if (errorCode === "rate_limited") return i18n.t("thread.inlineAction.error.mail.rate_limited");
    if (errorCode === "service_unavailable") return i18n.t("thread.inlineAction.error.mail.service_unavailable");
  }

  return cleanText(actionResult.error?.message);
}

function localizeKnownActionResult(actionResult: ActionResultMetadata): Partial<DerivedActionResult> {
  if (!shouldLocalizeActionResultText()) return {};

  const domain = cleanText(actionResult.domain);
  if (domain === "calendar") return localizeCalendarActionResult(actionResult);
  if (domain === "mail") return localizeMailActionResult(actionResult);
  return {};
}

export function toChannelBadgeLabel(channel: string | null | undefined): string {
  if (!channel) return i18n.t("channels.webui");
  if (channel === "websocket") return i18n.t("channels.webui");
  if (channel === "telegram") return i18n.t("channels.telegram");
  if (channel === "discord") return i18n.t("channels.discord");
  if (channel === "email") return i18n.t("channels.email");
  if (channel === "slack") return i18n.t("channels.slack");
  return channel;
}

export function hasPendingApproval(session: ChatSummary | null | undefined): boolean {
  return session?.metadata?.approval_summary?.status === "pending";
}

export function approvalPendingBadgeLabel(): string {
  return i18n.t("thread.approval.pendingBadge");
}

export function approvalSummaryLabel(session: ChatSummary | null | undefined): string | null {
  const summary = session?.metadata?.approval_summary;
  if (!summary || summary.status !== "pending") return null;

  const toolName = summary.tool_name?.trim() || i18n.t("thread.approval.toolFallback");
  if (toolName === "calendar.create_event") {
    const request = session?.metadata?.calendar_create_approval;
    const pendingRequest = session?.metadata?.calendar_pending_interaction?.request;
    const pending = pendingRequest && typeof pendingRequest === "object" ? pendingRequest as Record<string, unknown> : null;
    const title = request?.title?.trim() || (typeof pending?.title === "string" ? pending.title.trim() : "");
    const startAt = request?.start_at?.trim() || (typeof pending?.start_at === "string" ? pending.start_at.trim() : "");
    const endAt = request?.end_at?.trim() || (typeof pending?.end_at === "string" ? pending.end_at.trim() : "");
    if (title && startAt && endAt) {
      return i18n.t("thread.approval.calendarCreatePendingWindow", { title, startAt, endAt });
    }
    if (title) return i18n.t("thread.approval.calendarCreatePendingTitle", { title });
    return i18n.t("thread.approval.calendarCreatePending");
  }
  const promptPreview = summary.prompt_preview?.trim();
  return promptPreview
    ? i18n.t("thread.approval.pendingWithPreview", { toolName, promptPreview })
    : i18n.t("thread.approval.pendingWithTool", { toolName });
}

export function getCalendarPendingInteraction(
  session: ChatSummary | null | undefined,
): DerivedPendingInteraction | null {
  const pending = session?.metadata?.calendar_pending_interaction;
  if (!pending || pending.status !== "pending") return null;
  const buttons = Array.isArray(pending.buttons)
    ? pending.buttons
      .filter((row): row is string[] => Array.isArray(row))
      .map((row) => row.filter((option) => typeof option === "string" && option.trim()))
      .filter((row) => row.length > 0)
    : [];
  if (buttons.length === 0) return null;
  return {
    id: pending.id?.trim() || null,
    domain: "calendar",
    kind: pending.kind?.trim() || null,
    status: pending.status?.trim() || null,
    question: pending.question?.trim() || null,
    buttons,
  };
}

export function getTaskSummary(
  session: ChatSummary | null | undefined,
): DerivedTaskSummary | null {
  const task = session?.metadata?.task_summary;
  if (!task) return null;

  return {
    taskId: task.task_id?.trim() || null,
    canonicalOwnerId: task.canonical_owner_id?.trim() || null,
    title: task.title?.trim() || null,
    status: task.status?.trim() || null,
    originChannel: task.origin_channel?.trim() || null,
    originSessionKey: task.origin_session_key?.trim() || null,
    updatedAt: task.updated_at?.trim() || null,
    nextStepHint: normalizeTaskNextStepHint(task.status, task.next_step_hint),
  };
}

export function getOwnerProfile(
  session: ChatSummary | null | undefined,
): DerivedOwnerProfile | null {
  const profile = session?.metadata?.owner_profile;
  if (!profile) return null;

  return {
    canonicalOwnerId: profile.canonical_owner_id?.trim() || null,
    preferredLanguage: profile.preferred_language?.trim() || null,
    timezone: profile.timezone?.trim() || null,
    responseTone: profile.response_tone?.trim() || null,
    responseLength: profile.response_length?.trim() || null,
  };
}

export function getMemoryCorrectionActions(
  session: ChatSummary | null | undefined,
): DerivedMemoryCorrectionAction[] {
  const actions = session?.metadata?.memory_correction?.actions;
  if (!Array.isArray(actions)) return [];

  return actions.map((action) => ({
    code: action.code?.trim() || null,
    phrase: action.phrase?.trim() || null,
    target: action.target?.trim() || null,
    store: action.store?.trim() || null,
  })).filter((action) => action.phrase);
}

export function getActionResult(
  session: ChatSummary | null | undefined,
): DerivedActionResult | null {
  const actionResult = session?.metadata?.action_result;
  if (!actionResult) return null;

  const localized = localizeKnownActionResult(actionResult);

  return {
    actionId: cleanText(actionResult.action_id),
    domain: cleanText(actionResult.domain),
    action: cleanText(actionResult.action),
    status: cleanText(actionResult.status),
    title: localized.title ?? cleanText(actionResult.title),
    summary: localized.summary ?? cleanText(actionResult.summary),
    nextStep: localized.nextStep ?? cleanText(actionResult.next_step),
    badge: localized.badge ?? cleanText(actionResult.visibility?.badge),
    inlineStatus: localized.inlineStatus ?? cleanText(actionResult.visibility?.inline_status),
    linkedSummary: localized.linkedSummary ?? cleanText(actionResult.visibility?.linked_summary),
    errorCode: cleanText(actionResult.error?.code),
    errorMessage: localizeActionErrorMessage(actionResult),
  };
}

export function getProactiveSummary(
  session: ChatSummary | null | undefined,
): DerivedProactiveSummary | null {
  const proactive = session?.metadata?.proactive_summary;
  if (!proactive) return null;

  return {
    status: proactive.status?.trim() || null,
    category: proactive.category?.trim() || null,
    title: proactive.title?.trim() || null,
    summary: proactive.summary?.trim() || null,
    targetChannel: proactive.target_channel?.trim() || null,
    suppressedReason: proactive.suppressed_reason?.trim() || null,
    updatedAt: proactive.updated_at?.trim() || null,
  };
}

export function taskStatusLabel(status: string | null | undefined): string {
  const normalized = normalizeActionStatus(status);
  if (!normalized) return i18n.t("thread.statusTone.unknown");
  if (normalized === "waiting_approval") return i18n.t("thread.statusTone.waitingApproval");
  if (normalized === "rejected") return i18n.t("thread.statusTone.rejected");
  if (normalized === "blocked") return i18n.t("thread.statusTone.blocked");
  if (normalized === "completed") return i18n.t("thread.statusTone.completed");
  if (normalized === "failed") return i18n.t("thread.statusTone.failed");
  if (normalized === "scheduled") return i18n.t("thread.statusTone.scheduled");
  if (normalized === "running") return i18n.t("thread.statusTone.running");
  return cleanText(status) || i18n.t("thread.statusTone.unknown");
}

export function actionResultReasonLabel(reason: string | null | undefined): string | null {
  const normalized = cleanText(reason)?.toLowerCase();
  if (!normalized) return null;
  if (normalized === "overlap_detected") return i18n.t("thread.inlineAction.reason.overlap_detected");
  return normalized.replaceAll("_", " ").replace(/^./, (char) => char.toUpperCase());
}

export function isBlockedSession(session: ChatSummary | null | undefined): boolean {
  const task = getTaskSummary(session);
  if (task?.status === "blocked") return true;
  if (task?.status === "waiting-approval" || task?.status === "completed") return false;

  if (!session || hasPendingApproval(session)) return false;
  if (session.metadata?.pending_user_turn) return true;

  const phase = session.metadata?.runtime_checkpoint?.phase?.trim().toLowerCase();
  if (!phase) return false;
  return phase.startsWith("awaiting") || phase === "interrupted" || phase === "blocked";
}

export function isCompletedSession(session: ChatSummary | null | undefined): boolean {
  const task = getTaskSummary(session);
  return task?.status === "completed";
}