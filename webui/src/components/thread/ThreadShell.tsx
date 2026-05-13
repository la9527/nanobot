import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import {
  BarChart3,
  BookOpen,
  ChevronRight,
  Code2,
  ImageIcon,
  LayoutGrid,
  Lightbulb,
  MoreHorizontal,
  Palette,
  Sparkles,
} from "lucide-react";
import type { TFunction } from "i18next";
import { useTranslation } from "react-i18next";

import { AssistantDashboard } from "@/components/home/AssistantDashboard";
import { ThreadAssistantDetailsSheet } from "@/components/thread/ThreadAssistantDetailsSheet";
import { AskUserPrompt } from "@/components/thread/AskUserPrompt";
import { ThreadComposer } from "@/components/thread/ThreadComposer";
import { ThreadContextWindowIndicator } from "@/components/thread/ThreadContextWindowIndicator";
import { ThreadHeader } from "@/components/thread/ThreadHeader";
import { ThreadInlineActionResult } from "@/components/thread/ThreadInlineActionResult";
import { ThreadStatusRail } from "@/components/thread/ThreadStatusRail";
import { ThreadStatusBlock } from "@/components/thread/ThreadStatusBlock";
import type { ThreadStatusTone } from "@/components/thread/ThreadStatusBlock";
import { ThreadViewport } from "@/components/thread/ThreadViewport";
import { deriveThreadStatus, injectSyntheticReasoningTrace } from "@/components/thread/threadStatus";
import { useNanobotStream, type SendImage, type SendOptions } from "@/hooks/useNanobotStream";
import { hydrateSessionMessages, useSessionHistory } from "@/hooks/useSessions";
import { ApiError, clearSessionActionResult, clearSessionProactiveSummary, fetchSessionMessages, fetchSessionModelTarget, listSlashCommands, selectSessionModelTarget } from "@/lib/api";
import { relativeTime } from "@/lib/format";
import {
  approvalPendingBadgeLabel,
  getCalendarPendingInteraction,
  getActionResult,
  getContextWindowSummary,
  getMemoryCorrectionActions,
  getOwnerProfile,
  getProactiveSummary,
  getTaskSummary,
  hasPendingApproval,
  isCompletedSession,
  isBlockedSession,
  toChannelBadgeLabel,
} from "@/lib/sessionMetadata";
import type {
  ChatSummary,
  ModelTargetOption,
  ReasoningVisibility,
  SessionModelTargetResponse,
  SlashCommand,
  UIMessage,
} from "@/lib/types";
import { createUuid } from "@/lib/uuid";
import { useClient } from "@/providers/ClientProvider";

interface ThreadShellProps {
  session: ChatSummary | null;
  sessions?: ChatSummary[];
  emptyView?: "dashboard" | "new-chat";
  title: string;
  reasoningVisibility?: ReasoningVisibility;
  onToggleSidebar: () => void;
  onGoHome?: () => void;
  onOpenSession?: (key: string) => void;
  onNewChat?: () => void;
  onCreateChat?: () => Promise<string | null>;
  onRefreshSessions?: () => Promise<void> | void;
  onTurnEnd?: () => void;
  theme?: "light" | "dark";
  onToggleTheme?: () => void;
  onOpenSettings?: () => void;
  hideSidebarToggleOnDesktop?: boolean;
}

const MEMORY_CORRECTION_KEYS = ["remember", "forget", "notPreference", "projectDone"] as const;
type MemoryCorrectionKey = typeof MEMORY_CORRECTION_KEYS[number];

function toModelBadgeLabel(
  modelName: string | null,
  activeTarget: string | null,
  t: TFunction,
): string | null {
  if (typeof activeTarget === "string") {
    const target = activeTarget.trim();
    if (target && target !== "default") {
      if (target === "smart-router" || target === "smart_router") return t("thread.modelTarget.auto");
      if (target === "smart-router-local") return t("thread.modelTarget.local");
      if (target === "smart-router-mini") return t("thread.modelTarget.mini");
      if (target === "smart-router-full") return t("thread.modelTarget.full");
      return target;
    }
  }
  if (!modelName) return null;
  const trimmed = modelName.trim();
  if (!trimmed) return null;
  const leaf = trimmed.split("/").pop() ?? trimmed;
  const label = leaf || trimmed;
  if (label === "smart_router" || label === "smart-router") return t("thread.modelTarget.auto");
  return label;
}

function formatContinuitySummary(session: ChatSummary | null, t: TFunction): {
  title: string;
  body: string;
} | null {
  if (!session?.channel || session.channel === "websocket") return null;
  const channelLabel = toChannelBadgeLabel(session.channel);
  const continuity = session.metadata?.continuity;
  const ownerId = continuity?.canonical_owner_id?.trim();
  const externalIdentity = continuity?.external_identity?.trim();
  const trustLevel = continuity?.trust_level?.trim();

  if (!ownerId && !externalIdentity && !trustLevel) {
    return {
      title: t("thread.details.linkedExternalSession.title"),
      body: t("thread.details.linkedExternalSession.bodySimple", { channel: channelLabel }),
    };
  }

  const parts = [
    t("thread.details.linkedExternalSession.bodyWithOwner", { channel: channelLabel, owner: ownerId || "primary-user" }),
  ];
  if (externalIdentity) {
    parts.push(t("thread.details.linkedExternalSession.identity", { identity: externalIdentity }));
  }
  if (trustLevel) {
    parts.push(t("thread.details.linkedExternalSession.trust", { trust: trustLevel }));
  }
  parts.push(t("thread.details.linkedExternalSession.repliesContinue"));

  return {
    title: t("thread.details.linkedExternalSession.title"),
    body: parts.join(" "),
  };
}

function memoryCorrectionKeyForPhrase(phrase: string, t: TFunction): MemoryCorrectionKey | null {
  for (const key of MEMORY_CORRECTION_KEYS) {
    const translationKey = `thread.memoryCorrection.phrases.${key}`;
    if (phrase === t(translationKey) || phrase === t(translationKey, { lng: "ko" })) {
      return key;
    }
  }
  return null;
}

function buildMemoryCorrectionDraft(phrase: string, taskTitle: string | null, t: TFunction): string {
  const key = memoryCorrectionKeyForPhrase(phrase, t);
  if (key === "remember") {
    return [
      phrase,
      t("thread.memoryCorrection.draft.rememberContent"),
      taskTitle ? t("thread.memoryCorrection.draft.currentTask", { title: taskTitle }) : null,
      t("thread.memoryCorrection.draft.storeMemory"),
    ].filter(Boolean).join("\n");
  }
  if (key === "forget") {
    return [
      phrase,
      t("thread.memoryCorrection.draft.forgetContent"),
      taskTitle ? t("thread.memoryCorrection.draft.currentTask", { title: taskTitle }) : null,
      t("thread.memoryCorrection.draft.storeUserOrMemory"),
    ].filter(Boolean).join("\n");
  }
  if (key === "notPreference") {
    return [
      phrase,
      t("thread.memoryCorrection.draft.preferenceContent"),
      taskTitle ? t("thread.memoryCorrection.draft.currentTask", { title: taskTitle }) : null,
      t("thread.memoryCorrection.draft.storeUser"),
    ].filter(Boolean).join("\n");
  }
  if (key === "projectDone") {
    return [
      phrase,
      t("thread.memoryCorrection.draft.projectMemo"),
      taskTitle ? t("thread.memoryCorrection.draft.currentTask", { title: taskTitle }) : null,
      t("thread.memoryCorrection.draft.storeMemory"),
    ].filter(Boolean).join("\n");
  }
  return [phrase, t("thread.memoryCorrection.draft.genericContent")]
    .filter(Boolean)
    .join("\n");
}

function isMemoryCorrectionDraft(content: string, t: TFunction): boolean {
  const lines = content
    .split(/\r?\n/u)
    .map((line) => line.trim())
    .filter(Boolean);
  if (lines.length === 0) return false;
  const header = lines[0];
  const phrases = MEMORY_CORRECTION_KEYS.flatMap((key) => {
    const translationKey = `thread.memoryCorrection.phrases.${key}`;
    return [t(translationKey), t(translationKey, { lng: "ko" })];
  });
  return phrases.some(
    (phrase) => header === phrase || header.startsWith(`${phrase}:`),
  );
}

function canonicalOwnerId(session: ChatSummary | null): string {
  const owner = session?.metadata?.continuity?.canonical_owner_id?.trim();
  return owner || "primary-user";
}

function deriveOwnerAwareSummary(params: {
  session: ChatSummary | null;
  sessions: ChatSummary[];
  assistantActive: boolean;
  currentThreadTone: ThreadStatusTone | null;
  t: TFunction;
}): {
  title: string;
  body: string;
  approvalPendingCount: number;
  blockedCount: number;
  linkedSessionCount: number;
  suppressedProactiveCount: number;
  nextStepHint: string | null;
} | null {
  const { session, sessions, assistantActive, currentThreadTone, t } = params;
  if (!session) return null;

  const ownerId = canonicalOwnerId(session);
  const ownerSessions = [session, ...sessions]
    .filter((candidate, index, rows) => {
      return canonicalOwnerId(candidate) === ownerId
        && rows.findIndex((row) => row.key === candidate.key) === index;
    });
  const relatedSessions = ownerSessions.filter(
    (candidate) => candidate.key !== session.key,
  );
  const linkedSessionCount = relatedSessions.length;
  const approvalPendingCount = ownerSessions.filter(
    (candidate) => hasPendingApproval(candidate),
  ).length;
  const activeTaskCount = assistantActive ? 1 : 0;
  const blockedSessions = ownerSessions.filter((candidate) => isBlockedSession(candidate));
  const currentThreadBlocked = currentThreadTone === "failed";
  const blockedCount = blockedSessions.length + (
    currentThreadBlocked && !blockedSessions.some((candidate) => candidate.key === session.key)
      ? 1
      : 0
  );
  const suppressedProactiveSessions = ownerSessions.filter(
    (candidate) => getProactiveSummary(candidate)?.status === "suppressed",
  );
  const suppressedProactiveCount = suppressedProactiveSessions.length;

  if (
    linkedSessionCount === 0
    && approvalPendingCount === 0
    && activeTaskCount === 0
    && blockedCount === 0
    && suppressedProactiveCount === 0
  ) {
    return null;
  }

  const metrics: string[] = [];
  if (activeTaskCount > 0) {
    metrics.push(t("thread.details.ownerSummary.metrics.activeNow", { count: activeTaskCount }));
  }
  if (approvalPendingCount > 0) {
    metrics.push(t("thread.details.ownerSummary.metrics.approvalPending", { count: approvalPendingCount }));
  }
  if (blockedCount > 0) {
    metrics.push(t("thread.details.ownerSummary.metrics.blocked", { count: blockedCount }));
  }
  if (suppressedProactiveCount > 0) {
    metrics.push(t("thread.details.ownerSummary.metrics.proactiveHeld", { count: suppressedProactiveCount }));
  }
  if (linkedSessionCount > 0) {
    metrics.push(t("thread.details.ownerSummary.metrics.linkedSessions", { count: linkedSessionCount }));
  }

  const latestSuppressedProactive = [...suppressedProactiveSessions]
    .sort((left, right) => {
      const leftStamp = Date.parse(
        getProactiveSummary(left)?.updatedAt ?? left.updatedAt ?? left.createdAt ?? "",
      ) || 0;
      const rightStamp = Date.parse(
        getProactiveSummary(right)?.updatedAt ?? right.updatedAt ?? right.createdAt ?? "",
      ) || 0;
      return rightStamp - leftStamp;
    })[0];

  const recentCompletedSession = [...ownerSessions]
    .filter((candidate) => {
      if (hasPendingApproval(candidate) || isBlockedSession(candidate)) return false;
      if (candidate.key === session.key && currentThreadTone !== "completed" && !isCompletedSession(candidate)) {
        return false;
      }
      return Boolean(candidate.updatedAt ?? candidate.createdAt);
    })
    .sort((left, right) => {
      const leftStamp = Date.parse(left.updatedAt ?? left.createdAt ?? "") || 0;
      const rightStamp = Date.parse(right.updatedAt ?? right.createdAt ?? "") || 0;
      return rightStamp - leftStamp;
    })[0];

  const latestExternalSession = [...relatedSessions]
    .filter((candidate) => candidate.channel !== "websocket")
    .sort((left, right) => {
      const leftStamp = Date.parse(left.updatedAt ?? left.createdAt ?? "") || 0;
      const rightStamp = Date.parse(right.updatedAt ?? right.createdAt ?? "") || 0;
      return rightStamp - leftStamp;
    })[0];

  const bodyParts = [metrics.join(" • ")];
  if (latestExternalSession) {
    const updatedLabel = relativeTime(
      latestExternalSession.updatedAt ?? latestExternalSession.createdAt,
    );
    const channelLabel = toChannelBadgeLabel(latestExternalSession.channel);
    const updatedSuffix = updatedLabel
      ? t("thread.details.ownerSummary.updatedSuffix", { updated: updatedLabel })
      : "";
    bodyParts.push(
      t("thread.details.ownerSummary.latestExternalActivity", { channel: channelLabel, updatedSuffix }),
    );
  }
  if (recentCompletedSession) {
    const updatedLabel = relativeTime(
      recentCompletedSession.updatedAt ?? recentCompletedSession.createdAt,
    );
    const channelLabel = toChannelBadgeLabel(recentCompletedSession.channel);
    const updatedSuffix = updatedLabel
      ? t("thread.details.ownerSummary.updatedSuffix", { updated: updatedLabel })
      : "";
    bodyParts.push(
      t("thread.details.ownerSummary.recentCompletion", { channel: channelLabel, updatedSuffix }),
    );
  }
  if (latestSuppressedProactive) {
    const proactive = getProactiveSummary(latestSuppressedProactive);
    const channelLabel = toChannelBadgeLabel(
      proactive?.targetChannel ?? latestSuppressedProactive.channel,
    );
    const updatedLabel = relativeTime(
      proactive?.updatedAt ?? latestSuppressedProactive.updatedAt ?? latestSuppressedProactive.createdAt,
    );
    const updatedSuffix = updatedLabel
      ? t("thread.details.ownerSummary.updatedLead", { updated: updatedLabel })
      : "";
    const heldMessageKey = proactive?.suppressedReason === "quiet_hours"
      ? "thread.details.ownerSummary.quietHoursHeld"
      : proactive?.suppressedReason === "duplicate"
        ? "thread.details.ownerSummary.duplicateHeld"
        : "thread.details.ownerSummary.held";
    bodyParts.push(
      t(heldMessageKey, {
        title: proactive?.title ?? t("thread.details.ownerSummary.latestProactiveUpdate"),
        channel: channelLabel,
        updatedSuffix,
      }),
    );
  }
  const nextTaskHint = [
    ownerSessions.find((candidate) => getTaskSummary(candidate)?.status === "waiting-approval"),
    ownerSessions.find((candidate) => getTaskSummary(candidate)?.status === "blocked"),
  ]
    .map((candidate) => getTaskSummary(candidate)?.nextStepHint ?? null)
    .find((hint) => Boolean(hint));

  if (nextTaskHint) {
    bodyParts.push(t("thread.details.currentTask.nextStep", { hint: nextTaskHint }));
  } else if (approvalPendingCount > 0) {
    bodyParts.push(t("thread.details.ownerSummary.nextStepReviewApproval"));
  } else if (blockedCount > 0) {
    bodyParts.push(t("thread.details.ownerSummary.nextStepReopenBlocked"));
  } else if (suppressedProactiveCount > 0) {
    bodyParts.push(t("thread.details.ownerSummary.nextStepOpenWebUI"));
  }

  return {
    title: t("thread.details.assistantOverview.title"),
    body: bodyParts.join(" "),
    approvalPendingCount,
    blockedCount,
    linkedSessionCount,
    suppressedProactiveCount,
    nextStepHint: nextTaskHint ?? null,
  };
}

function deriveModelNameFromTarget(target: ModelTargetOption | null | undefined): string | null {
  if (!target) return null;
  if (target.kind === "smart_router") {
    return target.name || "smart-router";
  }
  if (typeof target.model === "string") {
    const trimmed = target.model.trim();
    return trimmed || null;
  }
  return null;
}

function applyModelTargetResponse(
  response: SessionModelTargetResponse,
  setActiveTarget: (value: string | null) => void,
  setModelName: (value: string | null) => void,
) {
  setActiveTarget(response.active_target ?? null);
  setModelName(deriveModelNameFromTarget(response.target));
}

const QUICK_ACTION_KEYS = [
  { key: "plan", icon: LayoutGrid, tone: "text-[#f25b8f]" },
  { key: "analyze", icon: BarChart3, tone: "text-[#4f9de8]" },
  { key: "brainstorm", icon: Lightbulb, tone: "text-[#53c59d]" },
  { key: "code", icon: Code2, tone: "text-[#eba45d]" },
  { key: "summarize", icon: BookOpen, tone: "text-[#a877e7]" },
  { key: "more", icon: MoreHorizontal, tone: "text-muted-foreground/65" },
] as const;

const IMAGE_QUICK_ACTION_KEYS = [
  { key: "icon", icon: ImageIcon, tone: "text-[#4f9de8]" },
  { key: "sticker", icon: Sparkles, tone: "text-[#f25b8f]" },
  { key: "poster", icon: Palette, tone: "text-[#eba45d]" },
  { key: "product", icon: LayoutGrid, tone: "text-[#53c59d]" },
  { key: "portrait", icon: ImageIcon, tone: "text-[#a877e7]" },
  { key: "edit", icon: MoreHorizontal, tone: "text-muted-foreground/65" },
] as const;

interface PendingFirstMessage {
  content: string;
  images?: SendImage[];
  options?: SendOptions;
}

export function ThreadShell({
  session,
  sessions = [],
  emptyView = "dashboard",
  title,
  reasoningVisibility = "summary",
  onToggleSidebar,
  onGoHome: _onGoHome,
  onOpenSession,
  onNewChat,
  onRefreshSessions,
  onCreateChat,
  onTurnEnd,
  theme = "light",
  onToggleTheme = () => {},
  onOpenSettings = () => {},
  hideSidebarToggleOnDesktop = false,
}: ThreadShellProps) {
  const { t } = useTranslation();
  const isWebSocketSession = session?.channel === "websocket";
  const chatId = isWebSocketSession ? (session?.chatId ?? null) : null;
  const historyKey = session?.key ?? null;
  const streamChatId = isWebSocketSession
    ? (session?.chatId ?? null)
    : session?.channel === "telegram"
      ? historyKey
      : null;
  const { messages: historical, loading, hasPendingToolCalls } = useSessionHistory(historyKey);
  const {
    client,
    token,
    modelName,
    activeTarget,
    modelTargets,
    setModelName,
    setActiveTarget,
    resetModelSelection,
  } = useClient();
  const [booting, setBooting] = useState(false);
  const [modelTargetPending, setModelTargetPending] = useState(false);
  const [remoteReplyPending, setRemoteReplyPending] = useState(false);
  const [detailsOpen, setDetailsOpen] = useState(false);
  const [contextWindowOpen, setContextWindowOpen] = useState(false);
  const [dismissingActionResult, setDismissingActionResult] = useState(false);
  const [dismissedActionSignature, setDismissedActionSignature] = useState<string | null>(null);
  const [composerDraft, setComposerDraft] = useState<string | null>(null);
  const [composerDraftNonce, setComposerDraftNonce] = useState(0);
  const [slashCommands, setSlashCommands] = useState<SlashCommand[]>([]);
  const [heroImageMode, setHeroImageMode] = useState(false);
  const [websocketHistorySyncTick, setWebsocketHistorySyncTick] = useState(0);
  const [liveMetadata, setLiveMetadata] = useState<ChatSummary["metadata"] | null>(session?.metadata ?? null);
  const pendingFirstRef = useRef<PendingFirstMessage | null>(null);
  const pendingSessionRefreshRef = useRef(false);
  const remoteReplyPollRef = useRef(0);
  const remoteReplyPlaceholderIdRef = useRef<string | null>(null);
  const messageCacheRef = useRef<Map<string, UIMessage[]>>(new Map());
  const lastCachedChatIdRef = useRef<string | null>(null);
  const tokenRef = useRef(token);
  const reasoningLineCacheRef = useRef<Map<string, string>>(new Map());
  const clearedProactiveSignatureRef = useRef<string | null>(null);

  useEffect(() => {
    tokenRef.current = token;
  }, [token]);

  useEffect(() => {
    setLiveMetadata(session?.metadata ?? null);
    setContextWindowOpen(false);
  }, [historyKey, session?.metadata]);

  const sessionWithLiveMetadata = useMemo(() => {
    if (!session) return null;
    return {
      ...session,
      metadata: liveMetadata ?? session.metadata,
    };
  }, [liveMetadata, session]);

  const initial = useMemo(() => {
    const cacheKey = streamChatId ?? historyKey;
    if (!cacheKey) return historical;
    return messageCacheRef.current.get(cacheKey) ?? historical;
  }, [streamChatId, historyKey, historical]);
  const handleStreamTurnEnd = useCallback(() => {
    onTurnEnd?.();
    if (!streamChatId || !historyKey) return;
    setWebsocketHistorySyncTick((tick) => tick + 1);
  }, [streamChatId, historyKey, onTurnEnd]);
  const {
    messages,
    isStreaming,
    send,
    stop,
    setMessages,
    streamError,
    dismissStreamError,
  } = useNanobotStream(streamChatId, initial, hasPendingToolCalls, handleStreamTurnEnd);
  const showHeroComposer = messages.length === 0 && !loading;
  const showDashboardEmptyState = !session && emptyView === "dashboard";
  const messagePendingAsk = useMemo(() => {
    for (let index = messages.length - 1; index >= 0; index -= 1) {
      const message = messages[index];
      if (message.kind === "trace") continue;
      if (message.role === "user") return null;
      if (message.role === "assistant" && message.buttons?.some((row) => row.length > 0)) {
        return {
          question: message.content,
          buttons: message.buttons,
        };
      }
      if (message.role === "assistant") return null;
    }
    return null;
  }, [messages]);
  const metadataPendingAsk = useMemo(() => {
    const pending = getCalendarPendingInteraction(sessionWithLiveMetadata);
    if (!pending) return null;
    return {
      question: pending.question || "Choose how to continue.",
      buttons: pending.buttons,
    };
  }, [sessionWithLiveMetadata]);
  const pendingAsk = metadataPendingAsk ?? messagePendingAsk;

  const pendingApprovalMessage = useMemo(() => {
    for (let index = messages.length - 1; index >= 0; index -= 1) {
      const message = messages[index];
      if (message.kind === "trace") continue;
      if (message.role === "user") return null;
      if (message.kind === "approval") return message;
      if (message.role === "assistant") return null;
    }
    return null;
  }, [messages]);

  const headerStatusBadges = useMemo(() => {
    const badges: Array<{
      label: string;
      tone?: "default" | "muted" | "warning" | "active";
    }> = [];
    const modelLabel = toModelBadgeLabel(modelName, activeTarget, t);
    if (modelLabel) {
      badges.push({ label: t("thread.headerBadges.target", { label: modelLabel }) });
    }
    badges.push({ label: t("thread.headerBadges.channel", { channel: toChannelBadgeLabel(sessionWithLiveMetadata?.channel) }), tone: "muted" });
    if (sessionWithLiveMetadata?.channel && sessionWithLiveMetadata.channel !== "websocket") {
      badges.push({ label: t("thread.headerBadges.linkedSession"), tone: "muted" });
    }
    if (pendingAsk || pendingApprovalMessage) {
      badges.push({ label: approvalPendingBadgeLabel(), tone: "warning" });
    }
    if (isStreaming || remoteReplyPending || booting || modelTargetPending) {
      badges.push({ label: t("thread.headerBadges.assistantActive"), tone: "active" });
    }
    return badges;
  }, [activeTarget, booting, isStreaming, modelName, modelTargetPending, pendingApprovalMessage, pendingAsk, remoteReplyPending, sessionWithLiveMetadata?.channel, t]);

  const continuityPlaceholder = useMemo(() => {
    return formatContinuitySummary(sessionWithLiveMetadata, t);
  }, [sessionWithLiveMetadata, t]);

  const threadStatus = useMemo(
    () => deriveThreadStatus({
      messages,
      pendingAsk,
      pendingApprovalMessage,
      streamError,
      isStreaming,
      remoteReplyPending,
      booting,
      modelTargetPending,
      actionResult: getActionResult(sessionWithLiveMetadata),
    }),
    [booting, isStreaming, messages, modelTargetPending, pendingApprovalMessage, pendingAsk, remoteReplyPending, sessionWithLiveMetadata, streamError],
  );

  const ownerAwareSummary = useMemo(() => {
    return deriveOwnerAwareSummary({
      session: sessionWithLiveMetadata,
      sessions,
      assistantActive: isStreaming || remoteReplyPending || booting || modelTargetPending,
      currentThreadTone: threadStatus?.tone ?? null,
      t,
    });
  }, [booting, isStreaming, modelTargetPending, remoteReplyPending, sessionWithLiveMetadata, sessions, t, threadStatus?.tone]);

  const currentTaskSummary = useMemo(() => getTaskSummary(sessionWithLiveMetadata), [sessionWithLiveMetadata]);
  const currentOwnerProfile = useMemo(() => getOwnerProfile(sessionWithLiveMetadata), [sessionWithLiveMetadata]);
  const currentProactiveSummary = useMemo(() => getProactiveSummary(sessionWithLiveMetadata), [sessionWithLiveMetadata]);
  const memoryCorrectionActions = useMemo(() => getMemoryCorrectionActions(sessionWithLiveMetadata), [sessionWithLiveMetadata]);
  const actionResult = useMemo(() => getActionResult(sessionWithLiveMetadata), [sessionWithLiveMetadata]);
  const contextWindowSummary = useMemo(() => getContextWindowSummary(sessionWithLiveMetadata), [sessionWithLiveMetadata]);
  const currentActionSignature = sessionWithLiveMetadata?.metadata?.action_result?.action_id
    ? `${sessionWithLiveMetadata.key}:${sessionWithLiveMetadata.metadata.action_result.action_id}`
    : null;
  const isActionResultDismissed = Boolean(currentActionSignature && dismissedActionSignature === currentActionSignature);
  const currentActionMetadata = isActionResultDismissed ? null : sessionWithLiveMetadata?.metadata?.action_result;
  const effectiveActionResult = isActionResultDismissed ? null : actionResult;
  const currentActionDetails = currentActionMetadata?.details;
  const currentActionStatus = currentActionMetadata?.status;
  const currentActionDomain = currentActionMetadata?.domain;
  const currentActionDraftPreview = currentActionDomain === "mail" ? currentActionDetails?.preview : null;
  const currentCalendarPreview = currentActionDomain === "calendar" ? currentActionDetails?.preview : null;
  const currentCalendarConflict = currentActionDomain === "calendar"
    && currentActionDetails?.requested_start_at
    && currentActionDetails?.requested_end_at
      ? {
          requestedStartAt: currentActionDetails.requested_start_at,
          requestedEndAt: currentActionDetails.requested_end_at,
          reason: currentActionDetails.reason,
          conflictingEvents: Array.isArray(currentActionDetails.conflicting_events)
            ? currentActionDetails.conflicting_events
            : [],
        }
      : null;
  const currentActionThreads = Array.isArray(currentActionDetails?.threads)
    ? currentActionDetails.threads.slice(0, 3)
    : [];
  const activeProactiveSignature = historyKey
    && currentProactiveSummary?.status === "suppressed"
      ? `${historyKey}:${currentProactiveSummary.updatedAt ?? ""}:${currentProactiveSummary.suppressedReason ?? ""}:${currentProactiveSummary.summary ?? ""}`
      : null;
  const hasInlineActionResult = Boolean(
    effectiveActionResult?.title
    || effectiveActionResult?.summary
    || currentActionDraftPreview
    || currentCalendarPreview
    || currentCalendarConflict
    || currentActionThreads.length,
  );
  const isReasoningThreadStatus = threadStatus?.tone === "running" || threadStatus?.tone === "completed";
  const reasoningCacheKey = streamChatId ?? historyKey;

  useEffect(() => {
    if (!reasoningCacheKey) return;
    if (threadStatus?.tone === "running") {
      if (remoteReplyPending) {
        reasoningLineCacheRef.current.delete(reasoningCacheKey);
        return;
      }
      reasoningLineCacheRef.current.set(reasoningCacheKey, threadStatus.body);
      return;
    }
    if (!messages.some((message) => message.role === "user")) {
      reasoningLineCacheRef.current.delete(reasoningCacheKey);
    }
  }, [messages, reasoningCacheKey, remoteReplyPending, threadStatus?.body, threadStatus?.tone]);

  const shouldShowThreadStatus = Boolean(threadStatus) && !(
    isReasoningThreadStatus
    || (
    hasInlineActionResult
    && !pendingAsk
    && !pendingApprovalMessage
    && !streamError
    && !booting
    && !remoteReplyPending
    && !isStreaming
    && !modelTargetPending
    )
  );
  const handleMemoryCorrectionClick = useCallback((phrase: string) => {
    setComposerDraft(buildMemoryCorrectionDraft(phrase, currentTaskSummary?.title ?? null, t));
    setComposerDraftNonce((value) => value + 1);
    setDetailsOpen(false);
  }, [currentTaskSummary?.title, t]);

  const statusRailItems = useMemo(() => {
    const items: string[] = [];
    if (ownerAwareSummary?.approvalPendingCount) {
      items.push(
        ownerAwareSummary.approvalPendingCount === 1
          ? t("thread.statusRail.approvalPending")
          : t("thread.statusRail.approvals", { count: ownerAwareSummary.approvalPendingCount }),
      );
    }
    if (ownerAwareSummary?.blockedCount) {
      items.push(
        ownerAwareSummary.blockedCount === 1
          ? t("thread.statusRail.blocked")
          : t("thread.statusRail.blockedCount", { count: ownerAwareSummary.blockedCount }),
      );
    }
    if (ownerAwareSummary?.suppressedProactiveCount) {
      items.push(t("thread.statusRail.held", { count: ownerAwareSummary.suppressedProactiveCount }));
    }
    if (ownerAwareSummary?.linkedSessionCount) {
      items.push(t("thread.statusRail.linkedSessions", { count: ownerAwareSummary.linkedSessionCount }));
    }
    if (sessionWithLiveMetadata?.channel && sessionWithLiveMetadata.channel !== "websocket") {
      items.push(t("thread.statusRail.linkedChannel", { channel: toChannelBadgeLabel(sessionWithLiveMetadata.channel) }));
    }
    const updatedLabel = relativeTime(sessionWithLiveMetadata?.updatedAt ?? sessionWithLiveMetadata?.createdAt);
    if (updatedLabel) {
      items.push(t("thread.statusRail.updated", { time: updatedLabel }));
    }
    return items.slice(0, 4);
  }, [ownerAwareSummary?.approvalPendingCount, ownerAwareSummary?.blockedCount, ownerAwareSummary?.suppressedProactiveCount, ownerAwareSummary?.linkedSessionCount, sessionWithLiveMetadata?.channel, sessionWithLiveMetadata?.createdAt, sessionWithLiveMetadata?.updatedAt, t]);

  const statusRailCaption = useMemo(() => {
    if (currentTaskSummary?.status === "waiting-approval" || currentTaskSummary?.status === "blocked") {
      return currentTaskSummary.nextStepHint || currentTaskSummary.title || null;
    }
    if (ownerAwareSummary?.nextStepHint) {
      return ownerAwareSummary.nextStepHint;
    }
    return null;
  }, [currentTaskSummary?.nextStepHint, currentTaskSummary?.status, currentTaskSummary?.title, ownerAwareSummary?.nextStepHint]);

  const refreshSessionsIfNeeded = useCallback(async () => {
    if (!pendingSessionRefreshRef.current || !onRefreshSessions) return;
    pendingSessionRefreshRef.current = false;
    try {
      await onRefreshSessions();
    } catch (error) {
      console.error("Failed to refresh sessions after memory correction", error);
    }
  }, [onRefreshSessions]);

  const handleDismissActionResult = useCallback(async () => {
    if (!historyKey || !currentActionSignature || dismissingActionResult) return;
    setDismissingActionResult(true);
    try {
      await clearSessionActionResult(token, historyKey);
      setDismissedActionSignature(currentActionSignature);
      if (onRefreshSessions) {
        await onRefreshSessions();
      }
    } catch (error) {
      console.error("Failed to dismiss action result", error);
    } finally {
      setDismissingActionResult(false);
    }
  }, [currentActionSignature, dismissingActionResult, historyKey, onRefreshSessions, token]);

  useEffect(() => {
    if (!historyKey || !activeProactiveSignature) return;
    if (clearedProactiveSignatureRef.current === activeProactiveSignature) return;

    let cancelled = false;
    clearedProactiveSignatureRef.current = activeProactiveSignature;

    (async () => {
      try {
        await clearSessionProactiveSummary(tokenRef.current, historyKey);
        if (cancelled) return;
        await onRefreshSessions?.();
      } catch (error) {
        if (cancelled) return;
        clearedProactiveSignatureRef.current = null;
        console.error("Failed to clear proactive summary after review", error);
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [activeProactiveSignature, historyKey, onRefreshSessions]);

  useEffect(() => {
    if (!streamChatId || loading) return;
    const cached = messageCacheRef.current.get(streamChatId);
    // When the user switches away and back, keep the local in-memory thread
    // state (including not-yet-persisted messages) instead of replacing it with
    // whatever the history endpoint currently knows about.
    setMessages((prev) => {
      if (cached && cached.length > 0) return cached;
      if (historical.length === 0 && prev.length > 0) return prev;
      return historical;
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [loading, streamChatId, historical]);

  useEffect(() => {
    if (streamChatId) return;
    if (remoteReplyPending) return;
    setMessages(historical);
  }, [streamChatId, historical, remoteReplyPending, setMessages]);

  useEffect(() => {
    if (!streamChatId || !historyKey || websocketHistorySyncTick === 0) return;

    let cancelled = false;
    (async () => {
      try {
        const body = await fetchSessionMessages(tokenRef.current, historyKey);
        if (cancelled) return;
        setLiveMetadata(body.metadata ?? null);
        const nextMessages = hydrateSessionMessages(body);
        if (nextMessages.length === 0) return;

        let applied = false;
        setMessages((current) => {
          const currentVisibleCount = current.filter((message) => message.kind !== "trace").length;
          const nextVisibleCount = nextMessages.filter((message) => message.kind !== "trace").length;
          if (nextVisibleCount < currentVisibleCount) {
            return current;
          }
          applied = true;
          return nextMessages;
        });
        if (!applied) return;
        messageCacheRef.current.set(streamChatId, nextMessages);
        messageCacheRef.current.set(historyKey, nextMessages);
      } catch (error) {
        if (cancelled) return;
        if (!(error instanceof ApiError && error.status === 404)) {
          console.error("Failed to refresh websocket session history", error);
        }
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [historyKey, setMessages, streamChatId, websocketHistorySyncTick]);

  useLayoutEffect(() => {
    if (!streamChatId) {
      lastCachedChatIdRef.current = null;
      return;
    }
    if (loading) return;
    // Skip the first cache write after a chat switch. During that render,
    // `messages` can still belong to the previous chat until the stream hook
    // resets its local state for the new session.
    if (lastCachedChatIdRef.current !== streamChatId) {
      lastCachedChatIdRef.current = streamChatId;
      if (messages.length > 0) {
        messageCacheRef.current.set(streamChatId, messages);
      }
      return;
    }
    messageCacheRef.current.set(streamChatId, messages);
  }, [loading, messages, streamChatId]);

  useEffect(() => {
    if (!historyKey || isWebSocketSession) return;
    messageCacheRef.current.set(historyKey, messages);
  }, [historyKey, isWebSocketSession, messages]);

  useEffect(() => {
    if (!remoteReplyPending) return;
    const lastMessage = messages[messages.length - 1];
    if (!lastMessage) return;
    if (lastMessage.role !== "assistant") return;
    if (lastMessage.isStreaming) return;
    remoteReplyPollRef.current += 1;
    const placeholderId = remoteReplyPlaceholderIdRef.current;
    remoteReplyPlaceholderIdRef.current = null;
    if (placeholderId) {
      setMessages((prev) => prev.filter((message) => message.id !== placeholderId));
    }
    setRemoteReplyPending(false);
  }, [messages, remoteReplyPending, setMessages]);

  useEffect(() => {
    if (!pendingSessionRefreshRef.current) return;
    const lastMessage = messages[messages.length - 1];
    if (!lastMessage || lastMessage.role !== "assistant" || lastMessage.isStreaming) return;
    void refreshSessionsIfNeeded();
  }, [messages, refreshSessionsIfNeeded]);

  useEffect(() => {
    let cancelled = false;
    if (!historyKey) {
      resetModelSelection();
      return () => {
        cancelled = true;
      };
    }

    (async () => {
      try {
        const current = await fetchSessionModelTarget(token, historyKey);
        if (cancelled) return;
        applyModelTargetResponse(current, setActiveTarget, setModelName);
      } catch (error) {
        if (cancelled) return;
        if (!(error instanceof ApiError && error.status === 404)) {
          console.error("Failed to fetch session model target", error);
        }
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [historyKey, resetModelSelection, setActiveTarget, setModelName, token]);

  useEffect(() => {
    if (!chatId) return;
    const pending = pendingFirstRef.current;
    if (!pending) return;
    pendingFirstRef.current = null;
    send(pending.content, pending.images, pending.options);
    setBooting(false);
  }, [chatId, send]);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const commands = await listSlashCommands(token);
        if (!cancelled) setSlashCommands(commands);
      } catch {
        if (!cancelled) setSlashCommands([]);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [token]);

  useEffect(() => () => {
    remoteReplyPollRef.current += 1;
  }, []);

  const handleWelcomeSend = useCallback(
    async (content: string, images?: SendImage[], options?: SendOptions) => {
      if (booting) return;
      setBooting(true);
      pendingFirstRef.current = { content, images, options };
      const newId = await onCreateChat?.();
      if (!newId) {
        pendingFirstRef.current = null;
        setBooting(false);
      }
    },
    [booting, onCreateChat],
  );

  const handleQuickAction = useCallback(
    (prompt: string) => {
      const options: SendOptions | undefined = heroImageMode
        ? { imageGeneration: { enabled: true, aspect_ratio: null } }
        : undefined;
      if (session) {
        send(prompt, undefined, options);
        return;
      }
      void handleWelcomeSend(prompt, undefined, options);
    },
    [handleWelcomeSend, heroImageMode, send, session],
  );

  const quickActionItems = heroImageMode ? IMAGE_QUICK_ACTION_KEYS : QUICK_ACTION_KEYS;
  const quickActionPrefix = heroImageMode
    ? "thread.empty.imageQuickActions"
    : "thread.empty.quickActions";
  const quickActions = (
    <div className="mx-auto grid w-full max-w-[58rem] grid-cols-2 gap-3 pt-4 sm:grid-cols-3 lg:grid-cols-6 lg:gap-4">
      {quickActionItems.map(({ key, icon: Icon, tone }) => {
        const title = t(`${quickActionPrefix}.${key}.title`);
        const prompt = t(`${quickActionPrefix}.${key}.prompt`);
        return (
          <button
            key={key}
            type="button"
            onClick={() => handleQuickAction(prompt)}
            disabled={booting || isStreaming}
            className="group flex min-h-[136px] flex-col justify-between rounded-[20px] border border-black/[0.035] bg-card px-5 py-5 text-left shadow-[0_14px_34px_rgba(15,23,42,0.07)] transition-all hover:-translate-y-0.5 hover:shadow-[0_18px_42px_rgba(15,23,42,0.10)] disabled:pointer-events-none disabled:opacity-60 dark:border-white/[0.06] dark:shadow-[0_16px_34px_rgba(0,0,0,0.28)]"
          >
            <Icon className={`h-[18px] w-[18px] ${tone}`} strokeWidth={2} />
            <span className="max-w-[7.5rem] text-[15px] font-medium leading-[1.28] tracking-[-0.01em] text-foreground/82">
              {title}
            </span>
            <ChevronRight className="h-4 w-4 self-end text-muted-foreground/45 transition-colors group-hover:text-muted-foreground" />
          </button>
        );
      })}
    </div>
  );

  const handleApprovalResponse = useCallback(
    (messageId: string, decision: "yes" | "no") => {
      if (!chatId) return;
      setMessages((prev) => prev.filter((message) => message.id !== messageId));
      client.sendMessage(chatId, decision);
    },
    [chatId, client, setMessages],
  );

  const handleBridgedSessionSend = useCallback(
    async (content: string, images?: SendImage[]) => {
      if (!session || !historyKey || remoteReplyPending) return;
      const hasImages = !!images && images.length > 0;
      if (!hasImages && !content.trim()) return;
      pendingSessionRefreshRef.current = isMemoryCorrectionDraft(content, t);

      const optimisticAssistantId = createUuid();
      remoteReplyPlaceholderIdRef.current = optimisticAssistantId;
      setMessages((prev) => [
        ...prev,
        {
          id: createUuid(),
          role: "user",
          content,
          createdAt: Date.now(),
          ...(hasImages ? { images: images!.map((img) => img.preview) } : {}),
        },
        {
          id: optimisticAssistantId,
          role: "assistant",
          content: "",
          isStreaming: true,
          createdAt: Date.now(),
        },
      ]);
      setRemoteReplyPending(true);

      const pollId = remoteReplyPollRef.current + 1;
      remoteReplyPollRef.current = pollId;
      const startedAt = Date.now();
      const baselineHistoryLength = historical.length;
      const wireMedia = hasImages ? images!.map((img) => img.media) : undefined;

      client.sendSessionMessage(historyKey, content, wireMedia);

      while (remoteReplyPollRef.current === pollId) {
        try {
          const body = await fetchSessionMessages(tokenRef.current, historyKey);
          if (remoteReplyPollRef.current !== pollId) return;
          setLiveMetadata(body.metadata ?? null);
          const nextMessages = hydrateSessionMessages(body);
          const hasAssistantReply =
            nextMessages.length > baselineHistoryLength
            && nextMessages[nextMessages.length - 1]?.role === "assistant";
          if (hasAssistantReply) {
            remoteReplyPlaceholderIdRef.current = null;
            setMessages(nextMessages);
            messageCacheRef.current.set(historyKey, nextMessages);
            setRemoteReplyPending(false);
            return;
          }
        } catch (error) {
          console.error("Failed to refresh bridged session", error);
        }

        if (Date.now() - startedAt > 90_000) {
          if (remoteReplyPlaceholderIdRef.current === optimisticAssistantId) {
            remoteReplyPlaceholderIdRef.current = null;
          }
          setMessages((prev) => prev.filter((message) => message.id !== optimisticAssistantId));
          pendingSessionRefreshRef.current = false;
          setRemoteReplyPending(false);
          return;
        }
        await new Promise((resolve) => window.setTimeout(resolve, 1000));
      }
    },
    [client, historical.length, historyKey, remoteReplyPending, session, setMessages, t],
  );

  const handleWebSocketSend = useCallback(
    (content: string, images?: SendImage[]) => {
      pendingSessionRefreshRef.current = isMemoryCorrectionDraft(content, t);
      send(content, images);
    },
    [send, t],
  );

  const handleSelectModelTarget = useCallback(
    async (targetName: string) => {
      if (modelTargetPending) return;
      setModelTargetPending(true);
      try {
        let sessionKey = historyKey;
        if (!sessionKey) {
          const newId = await onCreateChat?.();
          if (!newId) return;
          sessionKey = `websocket:${newId}`;
        }
        const response = await selectSessionModelTarget(token, sessionKey, targetName);
        applyModelTargetResponse(response, setActiveTarget, setModelName);
      } catch (error) {
        console.error("Failed to change model target", error);
      } finally {
        setModelTargetPending(false);
      }
    },
    [historyKey, modelTargetPending, onCreateChat, setActiveTarget, setModelName, token],
  );

  const emptyState = loading ? (
    <div className="flex h-full items-center justify-center text-sm text-muted-foreground">
      {t("thread.loadingConversation")}
    </div>
  ) : session ? (
    <div className="flex w-full max-w-[36rem] flex-col gap-2 text-left animate-in fade-in-0 slide-in-from-bottom-2 duration-500">
      <div className="inline-flex items-center gap-2 text-[11px] font-medium text-muted-foreground">
        <img
          src="/brand/nanobot_icon.png"
          alt=""
          aria-hidden
          draggable={false}
          className="h-4 w-4 rounded-sm opacity-90"
        />
        <span className="text-foreground/82">nanobot</span>
      </div>
      <p className="max-w-[28rem] text-[13px] leading-6 text-muted-foreground">
        {t("thread.empty.description")}
      </p>
    </div>
  ) : showDashboardEmptyState ? (
    <AssistantDashboard
      sessions={sessions}
      onOpenSession={onOpenSession}
      onNewChat={onCreateChat ?? (async () => {
        onNewChat?.();
        return null;
      })}
    />
  ) : null;
  const syntheticReasoningLine = isReasoningThreadStatus
    ? threadStatus?.tone === "running"
      ? threadStatus.body
      : (reasoningCacheKey
        ? reasoningLineCacheRef.current.get(reasoningCacheKey)
          ?? actionResult?.inlineStatus
          ?? actionResult?.linkedSummary
          ?? null
        : null)
    : null;
  const viewportMessages = session
    ? injectSyntheticReasoningTrace({
        messages,
        statusLine: reasoningVisibility === "off" ? null : syntheticReasoningLine,
        isStreaming: Boolean(isReasoningThreadStatus && threadStatus?.tone === "running"),
        cacheKey: reasoningCacheKey,
      })
    : [];
  const viewportStreaming = Boolean(session) && (isStreaming || remoteReplyPending);

  return (
    <section className="relative flex min-h-0 flex-1 flex-col overflow-hidden">
      <ThreadHeader
        title={title}
        onToggleSidebar={onToggleSidebar}
        theme={theme}
        onToggleTheme={onToggleTheme}
        onOpenSettings={onOpenSettings}
        hideSidebarToggleOnDesktop={hideSidebarToggleOnDesktop}
        minimal={!session && !loading}
        statusBadges={headerStatusBadges}
        contextIndicator={session ? (
          <ThreadContextWindowIndicator
            summary={contextWindowSummary}
            open={contextWindowOpen}
            onOpenChange={setContextWindowOpen}
          />
        ) : null}
      />
      {(session && !hasInlineActionResult && (statusRailItems.length > 0 || statusRailCaption || ownerAwareSummary || currentTaskSummary || continuityPlaceholder || memoryCorrectionActions.length > 0)) ? (
        <ThreadStatusRail
          items={statusRailItems}
          caption={statusRailCaption}
          onOpenDetails={() => setDetailsOpen(true)}
        />
      ) : null}
      {session && hasInlineActionResult ? (
        <ThreadInlineActionResult
          placement="pinned"
          domain={currentActionDomain}
          status={currentActionStatus}
          title={effectiveActionResult?.title}
          summary={effectiveActionResult?.summary}
          preview={currentActionDomain === "mail" ? currentActionDraftPreview : currentCalendarPreview}
          conflict={currentCalendarConflict}
          threads={currentActionThreads}
          onDismiss={currentActionSignature ? handleDismissActionResult : undefined}
          dismissDisabled={dismissingActionResult}
        />
      ) : null}
      <ThreadViewport
        messages={viewportMessages}
        isStreaming={viewportStreaming}
        reasoningVisibility={reasoningVisibility}
        onApprovalResponse={handleApprovalResponse}
        emptyState={emptyState}
        historySupplement={session ? (
          <>
            {threadStatus && shouldShowThreadStatus ? (
              <ThreadStatusBlock
                tone={threadStatus.tone}
                title={threadStatus.title}
                body={threadStatus.body}
                reasoningVisibility={reasoningVisibility}
                onDismiss={threadStatus.tone === "failed" ? dismissStreamError : undefined}
              />
            ) : null}
            {pendingAsk ? (
              <AskUserPrompt
                question={pendingAsk.question}
                buttons={pendingAsk.buttons}
                onAnswer={session && !isWebSocketSession ? handleBridgedSessionSend : send}
              />
            ) : null}
          </>
        ) : null}
        composer={
          <>
            {session ? (
              <ThreadComposer
                onSend={isWebSocketSession ? handleWebSocketSend : handleBridgedSessionSend}
                disabled={isWebSocketSession ? !chatId : remoteReplyPending}
                isStreaming={isStreaming}
                placeholder={
                  showHeroComposer
                    ? t("thread.composer.placeholderHero")
                    : t("thread.composer.placeholderThread")
                }
                injectedDraft={composerDraft}
                injectedDraftNonce={composerDraftNonce}
                modelLabel={toModelBadgeLabel(modelName, activeTarget, t)}
                activeTarget={activeTarget}
                modelTargets={modelTargets}
                modelTargetPending={modelTargetPending}
                onSelectModelTarget={handleSelectModelTarget}
                variant={showHeroComposer ? "hero" : "thread"}
                slashCommands={slashCommands}
                imageMode={showHeroComposer ? heroImageMode : undefined}
                onImageModeChange={showHeroComposer ? setHeroImageMode : undefined}
                onStop={isWebSocketSession ? stop : undefined}
              />
            ) : (
              <>
                <ThreadComposer
                  onSend={handleWelcomeSend}
                  disabled={booting}
                  isStreaming={isStreaming}
                  placeholder={
                    booting
                      ? t("thread.composer.placeholderOpening")
                      : t("thread.composer.placeholderHero")
                  }
                  injectedDraft={composerDraft}
                  injectedDraftNonce={composerDraftNonce}
                  modelLabel={toModelBadgeLabel(modelName, activeTarget, t)}
                  activeTarget={activeTarget}
                  modelTargets={modelTargets}
                  modelTargetPending={modelTargetPending}
                  onSelectModelTarget={handleSelectModelTarget}
                  variant="hero"
                  slashCommands={slashCommands}
                  imageMode={heroImageMode}
                  onImageModeChange={setHeroImageMode}
                />
                {!showDashboardEmptyState && showHeroComposer ? quickActions : null}
              </>
            )}
          </>
        }
      />
      <ThreadAssistantDetailsSheet
        open={detailsOpen}
        onOpenChange={setDetailsOpen}
        ownerSummaryBody={ownerAwareSummary?.body}
        continuityTitle={continuityPlaceholder?.title}
        continuityBody={continuityPlaceholder?.body}
        currentTask={currentTaskSummary}
        ownerProfile={currentOwnerProfile}
        memoryActions={memoryCorrectionActions}
        onMemoryAction={handleMemoryCorrectionClick}
      />
    </section>
  );
}
