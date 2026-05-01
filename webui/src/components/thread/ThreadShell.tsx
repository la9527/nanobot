import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";

import { AskUserPrompt } from "@/components/thread/AskUserPrompt";
import { ThreadComposer } from "@/components/thread/ThreadComposer";
import { ThreadHeader } from "@/components/thread/ThreadHeader";
import { ThreadStatusBlock } from "@/components/thread/ThreadStatusBlock";
import type { ThreadStatusTone } from "@/components/thread/ThreadStatusBlock";
import { ThreadViewport } from "@/components/thread/ThreadViewport";
import { deriveThreadStatus } from "@/components/thread/threadStatus";
import { type SendImage, useNanobotStream } from "@/hooks/useNanobotStream";
import { hydrateSessionMessages, useSessionHistory } from "@/hooks/useSessions";
import { ApiError, fetchSessionMessages, fetchSessionModelTarget, selectSessionModelTarget } from "@/lib/api";
import { relativeTime } from "@/lib/format";
import {
  approvalPendingBadgeLabel,
  getActionResult,
  getMemoryCorrectionActions,
  getOwnerProfile,
  getProactiveSummary,
  getTaskSummary,
  hasPendingApproval,
  isCompletedSession,
  isBlockedSession,
  taskStatusLabel,
  toChannelBadgeLabel,
} from "@/lib/sessionMetadata";
import type { ChatSummary, ModelTargetOption, SessionModelTargetResponse, UIMessage } from "@/lib/types";
import { createUuid } from "@/lib/uuid";
import { useClient } from "@/providers/ClientProvider";

interface ThreadShellProps {
  session: ChatSummary | null;
  sessions?: ChatSummary[];
  title: string;
  onToggleSidebar: () => void;
  onGoHome: () => void;
  onNewChat: () => Promise<string | null>;
  onRefreshSessions?: () => Promise<void> | void;
  hideSidebarToggleOnDesktop?: boolean;
}

const MEMORY_CORRECTION_PHRASES = [
  "기억해",
  "잊어",
  "이건 기본 선호가 아님",
  "이 프로젝트는 끝났어",
];

function toModelBadgeLabel(
  modelName: string | null,
  activeTarget: string | null,
): string | null {
  if (typeof activeTarget === "string") {
    const target = activeTarget.trim();
    if (target && target !== "default") {
      if (target === "smart-router" || target === "smart_router") return "Auto";
      if (target === "smart-router-local") return "Local";
      if (target === "smart-router-mini") return "Mini";
      if (target === "smart-router-full") return "Full";
      return target;
    }
  }
  if (!modelName) return null;
  const trimmed = modelName.trim();
  if (!trimmed) return null;
  const leaf = trimmed.split("/").pop() ?? trimmed;
  const label = leaf || trimmed;
  if (label === "smart_router") return "smart-router";
  return label;
}

function formatContinuitySummary(session: ChatSummary | null): {
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
      title: "Linked external session",
      body: `This thread is attached to the current ${channelLabel} conversation. Replies and approval steps may continue against that linked session.`,
    };
  }

  const parts = [
    `This thread is attached to the current ${channelLabel} conversation for owner ${ownerId || "primary-user"}.`,
  ];
  if (externalIdentity) {
    parts.push(`Linked identity: ${externalIdentity}.`);
  }
  if (trustLevel) {
    parts.push(`Trust: ${trustLevel}.`);
  }
  parts.push("Replies and approval steps may continue against that linked session.");
  return {
    title: "Linked external session",
    body: parts.join(" "),
  };
}

function buildMemoryCorrectionDraft(phrase: string, taskTitle: string | null): string {
  if (phrase === "기억해") {
    return [
      "기억해",
      "내용: [기억할 내용]",
      taskTitle ? `현재 task: ${taskTitle}` : null,
      "저장 위치: memory/MEMORY.md",
    ].filter(Boolean).join("\n");
  }
  if (phrase === "잊어") {
    return [
      "잊어",
      "내용: [지울 내용]",
      taskTitle ? `현재 task: ${taskTitle}` : null,
      "저장 위치: USER.md 또는 memory/MEMORY.md",
    ].filter(Boolean).join("\n");
  }
  if (phrase === "이건 기본 선호가 아님") {
    return [
      "이건 기본 선호가 아님",
      "수정할 기본 선호: [바꿀 선호]",
      taskTitle ? `현재 task: ${taskTitle}` : null,
      "저장 위치: USER.md",
    ].filter(Boolean).join("\n");
  }
  if (phrase === "이 프로젝트는 끝났어") {
    return [
      "이 프로젝트는 끝났어",
      "프로젝트 메모: [남길 종료 메모]",
      taskTitle ? `현재 task: ${taskTitle}` : null,
      "저장 위치: memory/MEMORY.md",
    ].filter(Boolean).join("\n");
  }
  return [phrase, "내용: [정리할 내용]"]
    .filter(Boolean)
    .join("\n");
}

function isMemoryCorrectionDraft(content: string): boolean {
  const lines = content
    .split(/\r?\n/u)
    .map((line) => line.trim())
    .filter(Boolean);
  if (lines.length === 0) return false;
  const header = lines[0];
  return MEMORY_CORRECTION_PHRASES.some(
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
}): {
  title: string;
  body: string;
} | null {
  const { session, sessions, assistantActive, currentThreadTone } = params;
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
    metrics.push(`${activeTaskCount} active now`);
  }
  if (approvalPendingCount > 0) {
    metrics.push(`${approvalPendingCount} approval pending`);
  }
  if (blockedCount > 0) {
    metrics.push(`${blockedCount} blocked`);
  }
  if (suppressedProactiveCount > 0) {
    metrics.push(`${suppressedProactiveCount} proactive held`);
  }
  if (linkedSessionCount > 0) {
    metrics.push(`${linkedSessionCount} linked sessions`);
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
    bodyParts.push(
      `Latest external activity: ${channelLabel}${updatedLabel ? ` updated ${updatedLabel}` : ""}.`,
    );
  }
  if (recentCompletedSession) {
    const updatedLabel = relativeTime(
      recentCompletedSession.updatedAt ?? recentCompletedSession.createdAt,
    );
    const channelLabel = toChannelBadgeLabel(recentCompletedSession.channel);
    bodyParts.push(
      `Recent completion: ${channelLabel}${updatedLabel ? ` updated ${updatedLabel}` : ""}.`,
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
    bodyParts.push(
      `Quiet hours held ${proactive?.title ?? "the latest proactive update"} for ${channelLabel}${updatedLabel ? ` ${updatedLabel}` : ""}.`,
    );
  }
  const nextTaskHint = [
    ownerSessions.find((candidate) => getTaskSummary(candidate)?.status === "waiting-approval"),
    ownerSessions.find((candidate) => getTaskSummary(candidate)?.status === "blocked"),
    ownerSessions.find((candidate) => getTaskSummary(candidate)?.status === "completed"),
  ]
    .map((candidate) => getTaskSummary(candidate)?.nextStepHint ?? null)
    .find((hint) => Boolean(hint));

  if (nextTaskHint) {
    bodyParts.push(`Next step: ${nextTaskHint}`);
  } else if (approvalPendingCount > 0) {
    bodyParts.push("Next step: review the pending approval request.");
  } else if (blockedCount > 0) {
    bodyParts.push("Next step: reopen the blocked session and continue the interrupted action.");
  } else if (suppressedProactiveCount > 0) {
    bodyParts.push("Next step: open WebUI to review the held proactive update.");
  }

  return {
    title: "Assistant summary",
    body: bodyParts.join(" "),
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

export function ThreadShell({
  session,
  sessions = [],
  title,
  onToggleSidebar,
  onGoHome,
  onNewChat,
  onRefreshSessions,
  hideSidebarToggleOnDesktop = false,
}: ThreadShellProps) {
  const { t } = useTranslation();
  const isWebSocketSession = session?.channel === "websocket";
  const chatId = isWebSocketSession ? (session?.chatId ?? null) : null;
  const historyKey = session?.key ?? null;
  const { messages: historical, loading } = useSessionHistory(historyKey);
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
  const [composerDraft, setComposerDraft] = useState<string | null>(null);
  const [composerDraftNonce, setComposerDraftNonce] = useState(0);
  const pendingFirstRef = useRef<string | null>(null);
  const pendingSessionRefreshRef = useRef(false);
  const remoteReplyPollRef = useRef(0);
  const messageCacheRef = useRef<Map<string, UIMessage[]>>(new Map());
  const tokenRef = useRef(token);

  useEffect(() => {
    tokenRef.current = token;
  }, [token]);

  const initial = useMemo(() => {
    const cacheKey = chatId ?? historyKey;
    if (!cacheKey) return historical;
    return messageCacheRef.current.get(cacheKey) ?? historical;
  }, [chatId, historyKey, historical]);
  const {
    messages,
    isStreaming,
    send,
    setMessages,
    streamError,
    dismissStreamError,
  } = useNanobotStream(chatId ?? historyKey, initial, chatId);
  const showHeroComposer = messages.length === 0 && !loading;
  const pendingAsk = useMemo(() => {
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
    const modelLabel = toModelBadgeLabel(modelName, activeTarget);
    if (modelLabel) {
      badges.push({ label: `Target ${modelLabel}` });
    }
    badges.push({ label: `Channel ${toChannelBadgeLabel(session?.channel)}`, tone: "muted" });
    if (session?.channel && session.channel !== "websocket") {
      badges.push({ label: "Linked session", tone: "muted" });
    }
    if (pendingAsk || pendingApprovalMessage) {
      badges.push({ label: approvalPendingBadgeLabel(), tone: "warning" });
    }
    if (isStreaming || remoteReplyPending || booting || modelTargetPending) {
      badges.push({ label: "Assistant active", tone: "active" });
    }
    return badges;
  }, [activeTarget, booting, isStreaming, modelName, modelTargetPending, pendingApprovalMessage, pendingAsk, remoteReplyPending, session?.channel]);

  const continuityPlaceholder = useMemo(() => {
    return formatContinuitySummary(session);
  }, [session]);

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
      actionResult: getActionResult(session),
    }),
    [booting, isStreaming, messages, modelTargetPending, pendingApprovalMessage, pendingAsk, remoteReplyPending, session, streamError],
  );

  const ownerAwareSummary = useMemo(() => {
    return deriveOwnerAwareSummary({
      session,
      sessions,
      assistantActive: isStreaming || remoteReplyPending || booting || modelTargetPending,
      currentThreadTone: threadStatus?.tone ?? null,
    });
  }, [booting, isStreaming, modelTargetPending, remoteReplyPending, session, sessions, threadStatus?.tone]);

  const currentTaskSummary = useMemo(() => getTaskSummary(session), [session]);
  const currentOwnerProfile = useMemo(() => getOwnerProfile(session), [session]);
  const memoryCorrectionActions = useMemo(() => getMemoryCorrectionActions(session), [session]);
  const currentActionDetails = session?.metadata?.action_result?.details;
  const currentActionStatus = session?.metadata?.action_result?.status;
  const currentActionDomain = session?.metadata?.action_result?.domain;
  const currentActionDraftPreview = currentActionDomain === "mail" ? currentActionDetails?.preview : null;
  const currentCalendarPreview = currentActionDomain === "calendar" ? currentActionDetails?.preview : null;
  const currentCalendarConflict = currentActionDomain === "calendar"
    && currentActionDetails?.requested_start_at
    && currentActionDetails?.requested_end_at
      ? {
          requestedStartAt: currentActionDetails.requested_start_at,
          requestedEndAt: currentActionDetails.requested_end_at,
          reason: currentActionDetails.reason,
        }
      : null;
  const currentActionThreads = Array.isArray(currentActionDetails?.threads)
    ? currentActionDetails.threads.slice(0, 3)
    : [];
  const handleMemoryCorrectionClick = useCallback((phrase: string) => {
    setComposerDraft(buildMemoryCorrectionDraft(phrase, currentTaskSummary?.title ?? null));
    setComposerDraftNonce((value) => value + 1);
  }, [currentTaskSummary?.title]);

  const refreshSessionsIfNeeded = useCallback(async () => {
    if (!pendingSessionRefreshRef.current || !onRefreshSessions) return;
    pendingSessionRefreshRef.current = false;
    try {
      await onRefreshSessions();
    } catch (error) {
      console.error("Failed to refresh sessions after memory correction", error);
    }
  }, [onRefreshSessions]);

  useEffect(() => {
    if (!chatId || loading) return;
    const cached = messageCacheRef.current.get(chatId);
    // When the user switches away and back, keep the local in-memory thread
    // state (including not-yet-persisted messages) instead of replacing it with
    // whatever the history endpoint currently knows about.
    setMessages(cached && cached.length > 0 ? cached : historical);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [loading, chatId, historical]);

  useEffect(() => {
    if (chatId) return;
    setMessages(historical);
  }, [chatId, historical, setMessages]);

  useEffect(() => {
    if (!chatId) return;
    messageCacheRef.current.set(chatId, messages);
  }, [chatId, messages]);

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
    setRemoteReplyPending(false);
  }, [messages, remoteReplyPending]);

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
    client.sendMessage(chatId, pending);
    setMessages((prev) => [
      ...prev,
      {
        id: createUuid(),
        role: "user",
        content: pending,
        createdAt: Date.now(),
      },
    ]);
    setBooting(false);
  }, [chatId, client, setMessages]);

  useEffect(() => () => {
    remoteReplyPollRef.current += 1;
  }, []);

  const handleWelcomeSend = useCallback(
    async (content: string) => {
      if (booting) return;
      setBooting(true);
      pendingFirstRef.current = content;
      const newId = await onNewChat();
      if (!newId) {
        pendingFirstRef.current = null;
        setBooting(false);
      }
    },
    [booting, onNewChat],
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
      pendingSessionRefreshRef.current = isMemoryCorrectionDraft(content);

      const optimisticAssistantId = createUuid();
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
          const nextMessages = hydrateSessionMessages(body);
          const hasAssistantReply =
            nextMessages.length > baselineHistoryLength
            && nextMessages[nextMessages.length - 1]?.role === "assistant";
          if (hasAssistantReply) {
            setMessages(nextMessages);
            messageCacheRef.current.set(historyKey, nextMessages);
            setRemoteReplyPending(false);
            return;
          }
        } catch (error) {
          console.error("Failed to refresh bridged session", error);
        }

        if (Date.now() - startedAt > 90_000) {
          setMessages((prev) => prev.filter((message) => message.id !== optimisticAssistantId));
          pendingSessionRefreshRef.current = false;
          setRemoteReplyPending(false);
          return;
        }
        await new Promise((resolve) => window.setTimeout(resolve, 1000));
      }
    },
    [client, historical.length, historyKey, remoteReplyPending, session, setMessages],
  );

  const handleWebSocketSend = useCallback(
    (content: string, images?: SendImage[]) => {
      pendingSessionRefreshRef.current = isMemoryCorrectionDraft(content);
      send(content, images);
    },
    [send],
  );

  const handleSelectModelTarget = useCallback(
    async (targetName: string) => {
      if (modelTargetPending) return;
      setModelTargetPending(true);
      try {
        let sessionKey = historyKey;
        if (!sessionKey) {
          const newId = await onNewChat();
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
    [historyKey, modelTargetPending, onNewChat, setActiveTarget, setModelName, token],
  );

  const emptyState = loading ? (
    <div className="flex h-full items-center justify-center text-sm text-muted-foreground">
      {t("thread.loadingConversation")}
    </div>
  ) : (
    <div className="flex w-full max-w-[40rem] flex-col gap-2 text-left animate-in fade-in-0 slide-in-from-bottom-2 duration-500">
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
  );

  return (
    <section className="relative flex min-h-0 flex-1 flex-col overflow-hidden">
      <ThreadHeader
        title={title}
        onToggleSidebar={onToggleSidebar}
        onGoHome={onGoHome}
        hideSidebarToggleOnDesktop={hideSidebarToggleOnDesktop}
        statusBadges={headerStatusBadges}
      />
      {ownerAwareSummary ? (
        <div className="px-3 pb-2">
          <div className="rounded-[16px] border border-border/60 bg-muted/35 px-3 py-2.5 text-sm text-muted-foreground">
            <p className="font-medium text-foreground/80">{ownerAwareSummary.title}</p>
            <p className="mt-1 text-[12px] leading-5">{ownerAwareSummary.body}</p>
          </div>
        </div>
      ) : null}
      {currentTaskSummary ? (
        <div className="px-3 pb-2">
          <div className="rounded-[16px] border border-border/60 bg-background/80 px-3 py-2.5 text-sm text-muted-foreground">
            <div className="flex flex-wrap items-center gap-2">
              <p className="font-medium text-foreground/85">Current task</p>
              <span className="inline-flex items-center rounded-full border border-border/60 bg-muted/50 px-2 py-0.5 text-[10px] font-medium tracking-wide text-muted-foreground">
                {taskStatusLabel(currentTaskSummary.status)}
              </span>
              {currentTaskSummary.originChannel ? (
                <span className="inline-flex items-center rounded-full border border-border/60 bg-muted/50 px-2 py-0.5 text-[10px] font-medium tracking-wide text-muted-foreground">
                  Origin {toChannelBadgeLabel(currentTaskSummary.originChannel)}
                </span>
              ) : null}
            </div>
            {currentTaskSummary.title ? (
              <p className="mt-1 text-[12px] leading-5 text-foreground/82">{currentTaskSummary.title}</p>
            ) : null}
            {currentTaskSummary.nextStepHint ? (
              <p className="mt-1 text-[12px] leading-5">Next step: {currentTaskSummary.nextStepHint}</p>
            ) : null}
            {currentOwnerProfile ? (
              <p className="mt-1 text-[11px] leading-5 text-muted-foreground/90">
                Owner defaults: {currentOwnerProfile.preferredLanguage || "unknown language"} · {currentOwnerProfile.timezone || "unknown timezone"} · {currentOwnerProfile.responseTone || "default tone"} · {currentOwnerProfile.responseLength || "default length"}
              </p>
            ) : null}
            {memoryCorrectionActions.length ? (
              <div className="mt-2 flex flex-wrap items-center gap-1.5">
                <span className="text-[11px] leading-5 text-muted-foreground/90">Memory corrections:</span>
                {memoryCorrectionActions.map((action) => (
                  <button
                    type="button"
                    key={action.code || action.phrase}
                    onClick={() => handleMemoryCorrectionClick(action.phrase || "")}
                    className="inline-flex items-center rounded-full border border-border/60 bg-muted/45 px-2 py-0.5 text-[10px] font-medium tracking-wide text-muted-foreground transition-colors hover:bg-muted/70 hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
                    title={action.store || undefined}
                  >
                    {action.phrase}
                  </button>
                ))}
              </div>
            ) : null}
          </div>
        </div>
      ) : null}
      {currentActionDraftPreview || currentActionThreads.length || currentCalendarPreview || currentCalendarConflict ? (
        <div className="px-3 pb-2">
          <div className="rounded-[16px] border border-border/60 bg-muted/20 px-3 py-2.5 text-sm text-muted-foreground">
            <div className="flex flex-wrap items-center gap-2">
              <p className="font-medium text-foreground/85">{currentActionDomain === "calendar" ? "Calendar result" : "Mail result"}</p>
              {currentActionDraftPreview ? (
                <span className="inline-flex items-center rounded-full border border-border/60 bg-muted/50 px-2 py-0.5 text-[10px] font-medium tracking-wide text-muted-foreground">
                  {currentActionStatus === "waiting_approval" ? "Approval pending" : "Draft preview"}
                </span>
              ) : null}
              {currentCalendarPreview ? (
                <span className="inline-flex items-center rounded-full border border-border/60 bg-muted/50 px-2 py-0.5 text-[10px] font-medium tracking-wide text-muted-foreground">
                  {currentActionStatus === "waiting_approval" ? "Approval pending" : "Event preview"}
                </span>
              ) : null}
              {currentCalendarConflict ? (
                <span className="inline-flex items-center rounded-full border border-border/60 bg-muted/50 px-2 py-0.5 text-[10px] font-medium tracking-wide text-muted-foreground">
                  Conflict check
                </span>
              ) : null}
              {!currentActionDraftPreview && currentActionThreads.length ? (
                <span className="inline-flex items-center rounded-full border border-border/60 bg-muted/50 px-2 py-0.5 text-[10px] font-medium tracking-wide text-muted-foreground">
                  Thread summary
                </span>
              ) : null}
            </div>
            {currentActionDraftPreview ? (
              <div className="mt-2 space-y-1 text-[12px] leading-5">
                <p><span className="font-medium text-foreground/82">To:</span> {(currentActionDraftPreview.to_recipients || []).join(", ") || "-"}</p>
                <p><span className="font-medium text-foreground/82">Subject:</span> {currentActionDraftPreview.subject || "(No subject)"}</p>
                <p><span className="font-medium text-foreground/82">Preview:</span> {currentActionDraftPreview.body_preview || "-"}</p>
              </div>
            ) : null}
            {currentCalendarPreview ? (
              <div className="mt-2 space-y-1 text-[12px] leading-5">
                <p><span className="font-medium text-foreground/82">Title:</span> {currentCalendarPreview.title || "(Untitled)"}</p>
                <p><span className="font-medium text-foreground/82">When:</span> {currentCalendarPreview.start_at || "-"} -&gt; {currentCalendarPreview.end_at || "-"}</p>
                {currentCalendarPreview.location ? (
                  <p><span className="font-medium text-foreground/82">Location:</span> {currentCalendarPreview.location}</p>
                ) : null}
                {currentCalendarPreview.description ? (
                  <p><span className="font-medium text-foreground/82">Details:</span> {currentCalendarPreview.description}</p>
                ) : null}
              </div>
            ) : null}
            {currentCalendarConflict ? (
              <div className="mt-2 space-y-1 text-[12px] leading-5">
                <p><span className="font-medium text-foreground/82">When:</span> {currentCalendarConflict.requestedStartAt} -&gt; {currentCalendarConflict.requestedEndAt}</p>
                {currentCalendarConflict.reason ? (
                  <p><span className="font-medium text-foreground/82">Reason:</span> {currentCalendarConflict.reason}</p>
                ) : null}
              </div>
            ) : null}
            {!currentActionDraftPreview && currentActionThreads.length ? (
              <div className="mt-2 space-y-2 text-[12px] leading-5">
                {currentActionThreads.map((thread, index) => (
                  <div key={thread.thread_id || `${index}-${thread.subject || "thread"}`} className="rounded-[12px] border border-border/50 bg-background/70 px-2.5 py-2">
                    <p className="font-medium text-foreground/85">{thread.subject || "(No subject)"}</p>
                    <p className="text-muted-foreground/95">{thread.summary || thread.sender_summary || thread.snippet || "No summary available."}</p>
                  </div>
                ))}
              </div>
            ) : null}
          </div>
        </div>
      ) : null}
      <ThreadViewport
        messages={messages}
        isStreaming={isStreaming || remoteReplyPending}
        onApprovalResponse={handleApprovalResponse}
        emptyState={emptyState}
        composer={
          <>
            {continuityPlaceholder ? (
              <div className="mb-2 rounded-[16px] border border-border/60 bg-muted/35 px-3 py-2.5 text-sm text-muted-foreground">
                <p className="font-medium text-foreground/80">{continuityPlaceholder.title}</p>
                <p className="mt-1 text-[12px] leading-5">{continuityPlaceholder.body}</p>
              </div>
            ) : null}
            {threadStatus ? (
              <ThreadStatusBlock
                tone={threadStatus.tone}
                title={threadStatus.title}
                body={threadStatus.body}
                onDismiss={threadStatus.tone === "failed" ? dismissStreamError : undefined}
              />
            ) : null}
            {pendingAsk ? (
              <AskUserPrompt
                question={pendingAsk.question}
                buttons={pendingAsk.buttons}
                onAnswer={send}
              />
            ) : null}
            {session ? (
              <ThreadComposer
                onSend={isWebSocketSession ? handleWebSocketSend : handleBridgedSessionSend}
                disabled={isWebSocketSession ? !chatId : remoteReplyPending}
                placeholder={
                  showHeroComposer
                    ? t("thread.composer.placeholderHero")
                    : t("thread.composer.placeholderThread")
                }
                injectedDraft={composerDraft}
                injectedDraftNonce={composerDraftNonce}
                modelLabel={toModelBadgeLabel(modelName, activeTarget)}
                activeTarget={activeTarget}
                modelTargets={modelTargets}
                modelTargetPending={modelTargetPending}
                onSelectModelTarget={handleSelectModelTarget}
                variant={showHeroComposer ? "hero" : "thread"}
              />
            ) : (
              <ThreadComposer
                onSend={handleWelcomeSend}
                disabled={booting}
                placeholder={
                  booting
                    ? t("thread.composer.placeholderOpening")
                    : t("thread.composer.placeholderHero")
                }
                injectedDraft={composerDraft}
                injectedDraftNonce={composerDraftNonce}
                modelLabel={toModelBadgeLabel(modelName, activeTarget)}
                activeTarget={activeTarget}
                modelTargets={modelTargets}
                modelTargetPending={modelTargetPending}
                onSelectModelTarget={handleSelectModelTarget}
                variant="hero"
              />
            )}
          </>
        }
      />
    </section>
  );
}
