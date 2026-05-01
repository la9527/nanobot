import type { ChatSummary } from "@/lib/types";

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

export function toChannelBadgeLabel(channel: string | null | undefined): string {
  if (!channel) return "WebUI";
  if (channel === "websocket") return "WebUI";
  if (channel === "telegram") return "Telegram";
  if (channel === "discord") return "Discord";
  if (channel === "email") return "Email";
  if (channel === "slack") return "Slack";
  return channel;
}

export function hasPendingApproval(session: ChatSummary | null | undefined): boolean {
  return session?.metadata?.approval_summary?.status === "pending";
}

export function approvalPendingBadgeLabel(): string {
  return "Approval pending";
}

export function approvalSummaryLabel(session: ChatSummary | null | undefined): string | null {
  const summary = session?.metadata?.approval_summary;
  if (!summary || summary.status !== "pending") return null;

  const toolName = summary.tool_name?.trim() || "tool";
  const promptPreview = summary.prompt_preview?.trim();
  return promptPreview ? `${toolName}: ${promptPreview}` : `${toolName} approval pending`;
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
  if (!status) return "Unknown";
  if (status === "waiting-approval") return "Waiting approval";
  if (status === "blocked") return "Blocked";
  if (status === "completed") return "Completed";
  if (status === "failed") return "Failed";
  if (status === "scheduled") return "Scheduled";
  if (status === "running") return "Running";
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