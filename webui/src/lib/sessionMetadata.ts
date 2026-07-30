import i18n from "@/i18n";
import type {
  ChatSummary,
  ModelTargetOption,
  SessionActionResult,
  SessionContextWindowSummary,
  SessionMemoryCorrectionAction,
  SessionMetadata,
  SessionOwnerProfile,
  SessionProactiveSummary,
  SessionTaskSummary,
} from "@/lib/types";

export interface SessionStatusBadge {
  key: string;
  label: string;
  tone: "neutral" | "info" | "success" | "warning" | "danger";
}

function text(value: string | null | undefined): string | null {
  const clean = String(value ?? "").trim();
  return clean || null;
}

function normalizeStatus(value: string | null | undefined): string | null {
  const clean = text(value)?.toLowerCase().replaceAll("-", "_");
  return clean || null;
}

function sentenceCase(value: string): string {
  return value
    .split(/[_\s]+/u)
    .filter(Boolean)
    .map((part) => part[0]?.toUpperCase() + part.slice(1))
    .join(" ");
}

export function channelLabel(value: string | null | undefined): string | null {
  const channel = text(value)?.toLowerCase();
  if (!channel) return null;
  if (channel === "websocket") return "Web";
  if (channel === "telegram") return "Telegram";
  if (channel === "discord") return "Discord";
  if (channel === "cron") return "Automation";
  return sentenceCase(channel);
}

export function modelTargetLabel(
  activeTarget: string | null | undefined,
  targets?: ModelTargetOption[] | null,
): string | null {
  const target = text(activeTarget);
  if (!target) return null;
  const matched = targets?.find((item) => item.name === target);
  const display = text(matched?.display_name);
  if (display) return display;
  if (target === "smart-router" || target === "smart_router") return "Auto";
  if (target === "smart-router-local") return "Local";
  if (target === "smart-router-mini") return "Mini";
  if (target === "smart-router-full") return "Full";
  if (target === "default") return "Default";
  return sentenceCase(target.replaceAll("-", " "));
}

export function taskStatusLabel(status: string | null | undefined): string {
  const normalized = normalizeStatus(status);
  switch (normalized) {
    case "running":
      return "In progress";
    case "waiting_approval":
      return "Approval pending";
    case "blocked":
      return "Needs review";
    case "failed":
      return "Failed";
    case "completed":
      return "Completed";
    case "suppressed":
      return "Suppressed";
    case "rejected":
      return "Cancelled";
    default:
      return normalized ? sentenceCase(normalized) : "Active";
  }
}

export function taskStatusTone(
  status: string | null | undefined,
): SessionStatusBadge["tone"] {
  const normalized = normalizeStatus(status);
  switch (normalized) {
    case "completed":
      return "success";
    case "waiting_approval":
      return "warning";
    case "blocked":
    case "failed":
      return "danger";
    case "running":
      return "info";
    default:
      return "neutral";
  }
}

export function getTaskSummary(session: ChatSummary | null): SessionTaskSummary | null {
  const summary = session?.metadata?.task_summary;
  return summary ? { ...summary } : null;
}

export function getOwnerProfile(session: ChatSummary | null): SessionOwnerProfile | null {
  const profile = session?.metadata?.owner_profile;
  return profile ? { ...profile } : null;
}

export function getMemoryCorrectionActions(
  session: ChatSummary | null,
): SessionMemoryCorrectionAction[] {
  return session?.metadata?.memory_correction?.actions ?? [];
}

export function getContextWindowSummary(
  session: ChatSummary | null,
): SessionContextWindowSummary | null {
  const summary = session?.metadata?.context_window;
  return summary ? { ...summary } : null;
}

export function getActionResult(session: ChatSummary | null): SessionActionResult | null {
  const action = session?.metadata?.action_result;
  return action ? { ...action } : null;
}

export function getProactiveSummary(
  session: ChatSummary | null,
): SessionProactiveSummary | null {
  const summary = session?.metadata?.proactive_summary;
  return summary ? { ...summary } : null;
}

export function hasPendingApproval(session: ChatSummary | null): boolean {
  return normalizeStatus(session?.metadata?.approval_summary?.status) === "pending";
}

export function approvalSummaryLabel(session: ChatSummary | null): string | null {
  const summary = session?.metadata?.approval_summary;
  const preview = text(summary?.prompt_preview);
  if (preview) return preview;
  if (summary) return taskStatusLabel("waiting_approval");
  return null;
}

export function linkedSessionSummary(session: ChatSummary | null): string | null {
  const continuity = session?.metadata?.continuity;
  if (!continuity) return null;
  const channel = channelLabel(continuity.channel_kind ?? session?.channel);
  const identity = text(continuity.external_identity);
  if (channel && identity) return `${channel} · ${identity}`;
  return channel || identity || null;
}

export function contextWindowLabel(summary: SessionContextWindowSummary | null): string | null {
  if (!summary) return null;
  const available = summary.available_tokens;
  const max = summary.max_tokens;
  if (typeof available === "number" && typeof max === "number" && max > 0) {
    const percent = Math.max(0, Math.min(100, Math.round((available / max) * 100)));
    return `${percent}% free`;
  }
  const status = text(summary.status);
  return status ? taskStatusLabel(status) : null;
}

export function actionResultReasonLabel(reason: string | null | undefined): string | null {
  const normalized = normalizeStatus(reason);
  if (!normalized) return null;
  if (normalized === "conflict") return "Conflicts found";
  if (normalized === "approval_rejected") return "Approval rejected";
  if (normalized === "not_found") return "No matching item";
  return sentenceCase(normalized);
}

export function statusTriggerSummary(
  session: ChatSummary | null,
  modelTargets?: ModelTargetOption[] | null,
): { label: string; tone: SessionStatusBadge["tone"] } | null {
  if (!session) return null;
  if (hasPendingApproval(session)) {
    return { label: "Approval pending", tone: "warning" };
  }
  const action = getActionResult(session);
  const actionStatus = normalizeStatus(action?.status);
  if (actionStatus === "failed" || actionStatus === "blocked") {
    return { label: taskStatusLabel(actionStatus), tone: "danger" };
  }
  const task = getTaskSummary(session);
  const taskStatus = normalizeStatus(task?.status);
  if (taskStatus && taskStatus !== "completed") {
    return { label: taskStatusLabel(taskStatus), tone: taskStatusTone(taskStatus) };
  }
  const proactive = getProactiveSummary(session);
  if (normalizeStatus(proactive?.status) === "suppressed") {
    return { label: "Quiet hours", tone: "neutral" };
  }
  const linked = linkedSessionSummary(session);
  if (linked) return { label: linked, tone: "neutral" };
  const target = modelTargetLabel(session.activeTarget, modelTargets);
  if (target && session.activeTarget && session.activeTarget !== "default") {
    return { label: target, tone: "info" };
  }
  return null;
}

export function sessionSidebarBadges(
  session: ChatSummary,
  modelTargets?: ModelTargetOption[] | null,
): SessionStatusBadge[] {
  const badges: SessionStatusBadge[] = [];
  if (hasPendingApproval(session)) {
    badges.push({ key: "approval", label: "Approval", tone: "warning" });
  }
  const task = getTaskSummary(session);
  const taskStatus = normalizeStatus(task?.status);
  if (taskStatus && taskStatus !== "completed" && taskStatus !== "waiting_approval") {
    badges.push({
      key: "task",
      label: taskStatusLabel(taskStatus),
      tone: taskStatusTone(taskStatus),
    });
  }
  const context = getContextWindowSummary(session);
  const contextStatus = normalizeStatus(context?.status);
  if (contextStatus === "warning" || contextStatus === "critical") {
    badges.push({
      key: "context",
      label: contextStatus === "critical" ? "Context low" : "Context warning",
      tone: contextStatus === "critical" ? "danger" : "warning",
    });
  }
  const target = modelTargetLabel(session.activeTarget, modelTargets);
  if (
    badges.length < 2
    && target
    && session.activeTarget
    && session.activeTarget !== "default"
  ) {
    badges.push({ key: "target", label: target, tone: "info" });
  }
  const linked = linkedSessionSummary(session);
  if (badges.length < 2 && linked) {
    badges.push({ key: "linked", label: linked, tone: "neutral" });
  }
  return badges.slice(0, 2);
}

export function metadataForSession(
  metadata: SessionMetadata | null | undefined,
): SessionMetadata | null {
  return metadata ? { ...metadata } : null;
}

export function ownerDefaultsLabel(session: ChatSummary | null): string | null {
  const profile = getOwnerProfile(session);
  if (!profile) return null;
  const language = text(profile.preferred_language);
  const timezone = text(profile.timezone);
  const tone = text(profile.response_tone);
  const length = text(profile.response_length);
  return [language, timezone, tone, length].filter(Boolean).join(" · ") || null;
}

export function localizeActionSummary(action: SessionActionResult | null): string | null {
  const title = text(action?.title);
  const summary = text(action?.summary);
  if (title && summary) return `${title}. ${summary}`;
  return title || summary || null;
}

export function defaultNoDetailsLabel(): string {
  return i18n.t("thread.sessionInfo.empty", { defaultValue: "No details yet." });
}
