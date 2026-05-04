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
    nextStepHint: task.next_step_hint?.trim() || null,
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

  return {
    actionId: actionResult.action_id?.trim() || null,
    domain: actionResult.domain?.trim() || null,
    action: actionResult.action?.trim() || null,
    status: actionResult.status?.trim() || null,
    title: actionResult.title?.trim() || null,
    summary: actionResult.summary?.trim() || null,
    nextStep: actionResult.next_step?.trim() || null,
    badge: actionResult.visibility?.badge?.trim() || null,
    inlineStatus: actionResult.visibility?.inline_status?.trim() || null,
    linkedSummary: actionResult.visibility?.linked_summary?.trim() || null,
    errorCode: actionResult.error?.code?.trim() || null,
    errorMessage: actionResult.error?.message?.trim() || null,
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
  if (!status) return i18n.t("thread.statusTone.unknown");
  if (status === "waiting-approval") return i18n.t("thread.statusTone.waitingApproval");
  if (status === "blocked") return i18n.t("thread.statusTone.blocked");
  if (status === "completed") return i18n.t("thread.statusTone.completed");
  if (status === "failed") return i18n.t("thread.statusTone.failed");
  if (status === "scheduled") return i18n.t("thread.statusTone.scheduled");
  if (status === "running") return i18n.t("thread.statusTone.running");
  return status;
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