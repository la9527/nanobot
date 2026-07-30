import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import type { PointerEvent as ReactPointerEvent } from "react";
import { useTranslation } from "react-i18next";

import { FilePreviewPanel } from "@/components/FilePreviewPanel";
import { PromptNavigator } from "@/components/thread/PromptNavigator";
import { SessionInfoPopover } from "@/components/thread/SessionInfoPopover";
import { ThreadComposer } from "@/components/thread/ThreadComposer";
import { ThreadHeader } from "@/components/thread/ThreadHeader";
import { StreamErrorNotice } from "@/components/thread/StreamErrorNotice";
import { ThreadViewport, type ThreadViewportHandle } from "@/components/thread/ThreadViewport";
import { useNanobotStream, type SendImage, type SendOptions } from "@/hooks/useNanobotStream";
import { hydrateSessionMessages, useSessionHistory } from "@/hooks/useSessions";
import {
  clearSessionActionResult,
  clearSessionModelTarget,
  clearSessionProactiveSummary,
  fetchInstalledCliApps,
  fetchMcpPresets,
  fetchSessionMessages,
  fetchSettings,
  listSlashCommands,
  selectSessionModelTarget,
} from "@/lib/api";
import {
  CLI_APPS_CHANGED_EVENT,
  installedCliAppsFromPayload,
  isCliAppsPayload,
} from "@/lib/cli-app-events";
import {
  MCP_PRESETS_CHANGED_EVENT,
  installedMcpPresetsFromPayload,
  isMcpPresetsPayload,
} from "@/lib/mcp-preset-events";
import { inferProviderFromModelName, providerDisplayLabel } from "@/lib/provider-brand";
import { modelTargetLabel } from "@/lib/sessionMetadata";
import type {
  ChatSummary,
  ModelTargetOption,
  SettingsPayload,
  SessionMetadata,
  SlashCommand,
  UIMessage,
  WorkspaceScopePayload,
  WorkspacesPayload,
} from "@/lib/types";
import { normalizeLegacyLongTaskMessages } from "@/lib/thread-display-compat";
import { scrubSubagentUiMessages } from "@/lib/subagent-channel-display";
import { useClient } from "@/providers/ClientProvider";

function projectWebuiThreadMessages(messages: UIMessage[]): UIMessage[] {
  return scrubSubagentUiMessages(normalizeLegacyLongTaskMessages(messages));
}

type MessageShape = Pick<UIMessage, "role" | "kind" | "content">;

function sameMessageShape(a: MessageShape, b: MessageShape): boolean {
  return (
    a.role === b.role
    && (a.kind ?? "") === (b.kind ?? "")
    && a.content === b.content
  );
}

function durableMessageShape(message: UIMessage): MessageShape | null {
  if (message.kind === "trace") return null;
  if (message.role !== "user" && message.role !== "assistant") return null;
  if (message.role === "assistant" && !message.content.trim() && !message.media?.length) {
    return null;
  }
  return {
    role: message.role,
    kind: message.kind,
    content: message.content,
  };
}

function preservesDurableMessages(current: UIMessage[], snapshot: UIMessage[]): boolean {
  // Canonical history refreshes can race with live websocket messages after fork/send.
  // Never accept a refreshed snapshot that drops a user/assistant message already shown.
  const expected = current
    .map(durableMessageShape)
    .filter((message): message is MessageShape => message !== null);
  if (expected.length === 0) return true;
  const candidates = snapshot
    .map(durableMessageShape)
    .filter((message): message is MessageShape => message !== null);

  let cursor = 0;
  for (const message of expected) {
    let found = false;
    while (cursor < candidates.length) {
      const candidate = candidates[cursor];
      cursor += 1;
      if (sameMessageShape(message, candidate)) {
        found = true;
        break;
      }
    }
    if (!found) return false;
  }
  return true;
}

function isStaleThreadSnapshot(current: UIMessage[], snapshot: UIMessage[]): boolean {
  if (current.length === 0) return false;
  if (snapshot.length === 0) return true;
  if (!preservesDurableMessages(current, snapshot)) return true;
  if (snapshot.length >= current.length) return false;
  return snapshot.every((message, index) => sameMessageShape(current[index], message));
}

const FILE_PREVIEW_DEFAULT_WIDTH = 544;
const FILE_PREVIEW_MIN_WIDTH = 360;
const FILE_PREVIEW_MAX_WIDTH = 860;
const FILE_PREVIEW_MIN_MAIN_WIDTH = 420;
const FILE_PREVIEW_CLOSE_ANIMATION_MS = 320;
const LINKED_REPLY_PLACEHOLDER_ID_PREFIX = "linked-pending:";

function clampFilePreviewWidth(width: number, maxWidth: number): number {
  return Math.min(Math.max(width, FILE_PREVIEW_MIN_WIDTH), maxWidth);
}

function maxFilePreviewWidth(containerWidth: number): number {
  return Math.max(
    FILE_PREVIEW_MIN_WIDTH,
    Math.min(FILE_PREVIEW_MAX_WIDTH, containerWidth - FILE_PREVIEW_MIN_MAIN_WIDTH),
  );
}

interface ThreadShellProps {
  session: ChatSummary | null;
  title: string;
  onToggleSidebar: () => void;
  onGoHome?: () => void;
  onNewChat?: () => void;
  onCreateChat?: (workspaceScope?: WorkspaceScopePayload | null) => Promise<string | null>;
  onForkChat?: (sourceChatId: string, beforeUserIndex: number) => Promise<string | null>;
  onTurnEnd?: () => void;
  theme?: "light" | "dark";
  onToggleTheme?: () => void;
  hideSidebarToggleForHostChrome?: boolean;
  hostChromeTitleInset?: boolean;
  hideThemeButton?: boolean;
  hideHeader?: boolean;
  workspaceScope?: WorkspaceScopePayload | null;
  workspaceDefaultScope?: WorkspaceScopePayload | null;
  workspaceControls?: WorkspacesPayload["controls"] | null;
  workspaceScopeDisabled?: boolean;
  workspaceError?: string | null;
  onWorkspaceScopeChange?: (scope: WorkspaceScopePayload) => void;
  settingsSnapshot?: SettingsPayload | null;
  onOpenModelSettings?: () => void;
  bootstrapActiveTarget?: string | null;
  bootstrapModelTargets?: ModelTargetOption[];
  onRefreshSessions?: () => Promise<void> | void;
}

function toModelBadgeLabel(modelName: string | null): string | null {
  if (!modelName) return null;
  const trimmed = modelName.trim();
  if (!trimmed) return null;
  const leaf = trimmed.split("/").pop() ?? trimmed;
  return leaf || trimmed;
}

interface ModelBadgeInfo {
  label: string | null;
  provider: string | null;
  providerLabel: string | null;
  needsSetup: boolean;
}

function activeModelPreset(settings: SettingsPayload | null): SettingsPayload["model_presets"][number] | null {
  if (!settings) return null;
  const configured = settings.agent.model_preset || "default";
  return (
    settings.model_presets.find((preset) => preset.name === configured)
    ?? settings.model_presets.find((preset) => preset.active)
    ?? null
  );
}

function resolvedModelProvider(settings: SettingsPayload | null, modelName: string | null): string | null {
  const preset = activeModelPreset(settings);
  const rawProvider = preset?.provider || settings?.agent.provider || null;
  if (rawProvider === "auto") {
    return settings?.agent.resolved_provider || inferProviderFromModelName(modelName) || null;
  }
  return rawProvider || inferProviderFromModelName(modelName);
}

function toModelBadgeInfo(modelName: string | null, settings: SettingsPayload | null): ModelBadgeInfo {
  const model = modelName || settings?.agent.model || null;
  const label = toModelBadgeLabel(model);
  const provider = resolvedModelProvider(settings, model);
  const providerRow = provider
    ? settings?.providers.find((item) => item.name === provider)
    : null;
  const needsSetup = Boolean(
    settings && (!model || !provider || !providerRow || !providerRow.configured),
  );
  return {
    label,
    provider,
    providerLabel: provider ? providerDisplayLabel(settings?.providers ?? [], provider) : null,
    needsSetup,
  };
}

const HERO_GREETING_KEYS = [
  "thread.empty.greetings.workOn",
  "thread.empty.greetings.start",
  "thread.empty.greetings.build",
  "thread.empty.greetings.tackle",
] as const;

function randomHeroGreetingKey(): (typeof HERO_GREETING_KEYS)[number] {
  const index = Math.floor(Math.random() * HERO_GREETING_KEYS.length);
  return HERO_GREETING_KEYS[index] ?? HERO_GREETING_KEYS[0];
}

interface PendingFirstMessage {
  content: string;
  images?: SendImage[];
  options?: SendOptions;
}

interface InstalledSettingItemsOptions<Payload, Item> {
  token: string;
  eventName: string;
  fetchPayload: (token: string) => Promise<Payload>;
  isPayload: (value: unknown) => value is Payload;
  selectItems: (payload: Payload) => Item[];
}

function useInstalledSettingItems<Payload, Item>({
  token,
  eventName,
  fetchPayload,
  isPayload,
  selectItems,
}: InstalledSettingItemsOptions<Payload, Item>): Item[] {
  const [items, setItems] = useState<Item[]>([]);

  const refresh = useCallback(async (isCancelled?: () => boolean) => {
    try {
      const payload = await fetchPayload(token);
      if (!isCancelled?.()) setItems(selectItems(payload));
    } catch {
      if (!isCancelled?.()) setItems([]);
    }
  }, [fetchPayload, selectItems, token]);

  useEffect(() => {
    let cancelled = false;
    void refresh(() => cancelled);

    const refreshOnFocus = () => {
      if (document.visibilityState === "hidden") return;
      void refresh();
    };
    const refreshOnChanged = (event: Event) => {
      const payload = (event as CustomEvent<unknown>).detail;
      if (isPayload(payload)) {
        setItems(selectItems(payload));
        return;
      }
      void refresh();
    };

    window.addEventListener("focus", refreshOnFocus);
    document.addEventListener("visibilitychange", refreshOnFocus);
    window.addEventListener(eventName, refreshOnChanged);
    return () => {
      cancelled = true;
      window.removeEventListener("focus", refreshOnFocus);
      document.removeEventListener("visibilitychange", refreshOnFocus);
      window.removeEventListener(eventName, refreshOnChanged);
    };
  }, [eventName, isPayload, refresh, selectItems]);

  return items;
}

export function ThreadShell({
  session,
  title,
  onToggleSidebar,
  onCreateChat,
  onForkChat,
  onTurnEnd,
  theme = "light",
  onToggleTheme = () => {},
  hideSidebarToggleForHostChrome = false,
  hostChromeTitleInset = false,
  hideThemeButton = false,
  hideHeader = false,
  workspaceScope = null,
  workspaceDefaultScope = null,
  workspaceControls = null,
  workspaceScopeDisabled = false,
  workspaceError = null,
  onWorkspaceScopeChange,
  settingsSnapshot = null,
  onOpenModelSettings,
  bootstrapActiveTarget = null,
  bootstrapModelTargets = [],
  onRefreshSessions,
}: ThreadShellProps) {
  const { t } = useTranslation();
  const isWebSocketSession = session?.channel === "websocket";
  const historyKey = session?.key ?? null;
  const chatId = isWebSocketSession ? session?.chatId ?? null : null;
  const streamChatId = isWebSocketSession
    ? session?.chatId ?? null
    : session?.channel === "telegram"
      ? historyKey
      : null;
  const threadKey = streamChatId ?? historyKey;
  const {
    messages: historical,
    loading,
    loadingOlder,
    loadOlder,
    hasMoreBefore,
    userMessageOffset,
    hasPendingToolCalls,
    refresh: refreshHistory,
    version: historyVersion,
    forkBoundaryMessageCount,
  } = useSessionHistory(historyKey);
  const { client, modelName, token } = useClient();
  const [booting, setBooting] = useState(false);
  const [slashCommands, setSlashCommands] = useState<SlashCommand[]>([]);
  const cliApps = useInstalledSettingItems({
    token,
    eventName: CLI_APPS_CHANGED_EVENT,
    fetchPayload: fetchInstalledCliApps,
    isPayload: isCliAppsPayload,
    selectItems: installedCliAppsFromPayload,
  });
  const mcpPresets = useInstalledSettingItems({
    token,
    eventName: MCP_PRESETS_CHANGED_EVENT,
    fetchPayload: fetchMcpPresets,
    isPayload: isMcpPresetsPayload,
    selectItems: installedMcpPresetsFromPayload,
  });
  const [settings, setSettings] = useState<SettingsPayload | null>(settingsSnapshot);
  const [sessionDetail, setSessionDetail] = useState<{
    activeTarget: string | null;
    metadata: SessionMetadata | null;
    workspaceScope: WorkspaceScopePayload | null;
  } | null>(null);
  const [modelTargetPending, setModelTargetPending] = useState(false);
  const [heroGreetingKey, setHeroGreetingKey] = useState(randomHeroGreetingKey);
  const [scrollToBottomSignal, setScrollToBottomSignal] = useState(0);
  const [scrollToLatestUserPromptSignal, setScrollToLatestUserPromptSignal] = useState(0);
  const [filePreviewPath, setFilePreviewPath] = useState<string | null>(null);
  const [filePreviewClosing, setFilePreviewClosing] = useState(false);
  const [filePreviewWidth, setFilePreviewWidth] = useState(FILE_PREVIEW_DEFAULT_WIDTH);
  const shellRef = useRef<HTMLElement | null>(null);
  const filePreviewWidthRef = useRef(FILE_PREVIEW_DEFAULT_WIDTH);
  const filePreviewCloseTimerRef = useRef<number | null>(null);
  const pendingFirstRef = useRef<PendingFirstMessage | null>(null);
  const viewportRef = useRef<ThreadViewportHandle | null>(null);
  const messageCacheRef = useRef<Map<string, UIMessage[]>>(new Map());
  /** Last thread key we associated with the in-memory thread (for cache-on-switch). */
  const prevThreadKeyForCacheRef = useRef<string | null>(null);
  /** Skip one message-cache write right after thread key changes (messages may not match yet). */
  const skipLayoutCacheRef = useRef(false);
  const appliedHistoryVersionRef = useRef<Map<string, number>>(new Map());
  const pendingCanonicalHydrateRef = useRef<Set<string>>(new Set());
  const bottomScrolledThreadKeyRef = useRef<string | null>(null);
  const [remoteReplyPending, setRemoteReplyPending] = useState(false);
  const remoteReplyBaselineRef = useRef<{
    assistantCount: number;
    startedAt: number;
  } | null>(null);
  const linkedReplyWaitingText = t("thread.linkedSession.waitingReply", {
    defaultValue: "Waiting for the linked external session to return a reply.",
  });

  const initial = useMemo(() => {
    if (!threadKey) return historical;
    return messageCacheRef.current.get(threadKey) ?? historical;
  }, [historical, threadKey]);
  const refreshSessionDetail = useCallback(async () => {
    if (!historyKey) {
      setSessionDetail(null);
      return;
    }
    try {
      const detail = await fetchSessionMessages(token, historyKey);
      setSessionDetail({
        activeTarget: detail.active_target ?? null,
        metadata: detail.metadata ?? null,
        workspaceScope: detail.workspace_scope ?? null,
      });
    } catch {
      setSessionDetail(null);
    }
  }, [historyKey, token]);
  const handleTurnEnd = useCallback(() => {
    void refreshSessionDetail();
    void onRefreshSessions?.();
    onTurnEnd?.();
  }, [onRefreshSessions, onTurnEnd, refreshSessionDetail]);
  const {
    messages,
    isStreaming,
    runStartedAt,
    goalState,
    send,
    transcribeAudio,
    stop,
    setMessages,
    streamError,
    dismissStreamError,
  } = useNanobotStream(streamChatId, initial, hasPendingToolCalls, handleTurnEnd);

  useEffect(() => {
    filePreviewWidthRef.current = filePreviewWidth;
  }, [filePreviewWidth]);

  useEffect(() => {
    if (filePreviewCloseTimerRef.current !== null) {
      window.clearTimeout(filePreviewCloseTimerRef.current);
      filePreviewCloseTimerRef.current = null;
    }
    setFilePreviewClosing(false);
    setFilePreviewPath(null);
    setSessionDetail(null);
    setModelTargetPending(false);
    setRemoteReplyPending(false);
    remoteReplyBaselineRef.current = null;
  }, [historyKey]);

  useEffect(() => {
    return () => {
      if (filePreviewCloseTimerRef.current !== null) {
        window.clearTimeout(filePreviewCloseTimerRef.current);
      }
    };
  }, []);

  const displayMessages = useMemo(() => projectWebuiThreadMessages(messages), [messages]);

  const showHeroComposer = messages.length === 0 && !loading;
  const wasShowingHeroComposerRef = useRef(showHeroComposer);
  const mergedSession = useMemo(() => {
    if (!session) return null;
    return {
      ...session,
      activeTarget: sessionDetail?.activeTarget ?? session.activeTarget ?? null,
      metadata: sessionDetail?.metadata ?? session.metadata ?? null,
      workspaceScope: sessionDetail?.workspaceScope ?? session.workspaceScope ?? null,
    };
  }, [session, sessionDetail]);
  const currentActiveTarget = session
    ? (mergedSession?.activeTarget ?? bootstrapActiveTarget ?? null)
    : bootstrapActiveTarget;
  const activeTargetOption = useMemo(
    () => bootstrapModelTargets.find((target) => target.name === currentActiveTarget) ?? null,
    [bootstrapModelTargets, currentActiveTarget],
  );
  const modelBadge = useMemo(() => {
    if (currentActiveTarget && currentActiveTarget !== "default") {
      const provider = activeTargetOption?.provider
        || inferProviderFromModelName(activeTargetOption?.model ?? null)
        || null;
      return {
        label: modelTargetLabel(currentActiveTarget, bootstrapModelTargets)
          ?? toModelBadgeLabel(activeTargetOption?.model ?? modelName)
          ?? "Model",
        provider,
        providerLabel: provider
          ? providerDisplayLabel(settings?.providers ?? [], provider)
          : null,
        needsSetup: false,
      };
    }
    return toModelBadgeInfo(modelName, settings);
  }, [
    activeTargetOption,
    bootstrapModelTargets,
    currentActiveTarget,
    modelName,
    settings,
  ]);
  const modelBadgeLabel = modelBadge.needsSetup
    ? t("thread.composer.modelNotConfigured", { defaultValue: "Model not configured" })
    : modelBadge.label;
  useEffect(() => {
    if (showHeroComposer && !wasShowingHeroComposerRef.current) {
      setHeroGreetingKey(randomHeroGreetingKey());
    }
    wasShowingHeroComposerRef.current = showHeroComposer;
  }, [showHeroComposer]);

  const withWorkspaceScope = useCallback(
    (options?: SendOptions): SendOptions | undefined => {
      if (!workspaceScope) return options;
      return {
        ...(options ?? {}),
        workspaceScope,
      };
    },
    [workspaceScope],
  );

  const refreshModelSettings = useCallback(async () => {
    try {
      setSettings(await fetchSettings(token));
    } catch {
      if (!settingsSnapshot) setSettings(null);
    }
  }, [settingsSnapshot, token]);

  useEffect(() => {
    if (settingsSnapshot) {
      setSettings(settingsSnapshot);
      return;
    }
    void refreshModelSettings();
  }, [refreshModelSettings, settingsSnapshot]);

  useEffect(() => {
    return client.onRuntimeModelUpdate(() => {
      void refreshModelSettings();
    });
  }, [client, refreshModelSettings]);

  useEffect(() => {
    void refreshSessionDetail();
  }, [refreshSessionDetail]);

  useEffect(() => {
    if (!threadKey || loading) return;
    const cached = messageCacheRef.current.get(threadKey);
    const appliedVersion = appliedHistoryVersionRef.current.get(threadKey) ?? 0;
    const hasPendingCanonicalHydrate = pendingCanonicalHydrateRef.current.has(threadKey);
    const hasNewCanonicalHistory = hasPendingCanonicalHydrate && historyVersion > appliedVersion;
    // When the user switches away and back, keep the local in-memory thread
    // state (including not-yet-persisted messages) instead of replacing it with
    // whatever the history endpoint currently knows about. Once a fresh
    // canonical replay arrives (e.g. after ``session_updated`` refresh), prefer it
    // so rendering converges to the same shape as a manual refresh.
    setMessages((prev) => {
      const normalizedHistory = projectWebuiThreadMessages(historical);
      const keepLiveMessages = (messagesToKeep: UIMessage[]) => {
        const projected = projectWebuiThreadMessages(messagesToKeep);
        messageCacheRef.current.set(threadKey, projected);
        return projected;
      };
      if (hasNewCanonicalHistory && historical.length > 0) {
        if (isStaleThreadSnapshot(prev, normalizedHistory)) return keepLiveMessages(prev);
        pendingCanonicalHydrateRef.current.delete(threadKey);
        appliedHistoryVersionRef.current.set(threadKey, historyVersion);
        messageCacheRef.current.set(threadKey, normalizedHistory);
        return normalizedHistory;
      }
      if (cached && cached.length > 0) {
        const normalizedCached = projectWebuiThreadMessages(cached);
        if (
          normalizedHistory.length > normalizedCached.length
          && !isStaleThreadSnapshot(prev, normalizedHistory)
        ) {
          messageCacheRef.current.set(threadKey, normalizedHistory);
          appliedHistoryVersionRef.current.set(threadKey, historyVersion);
          return normalizedHistory;
        }
        if (isStaleThreadSnapshot(prev, normalizedCached)) return keepLiveMessages(prev);
        return normalizedCached;
      }
      if (isStaleThreadSnapshot(prev, normalizedHistory)) return keepLiveMessages(prev);
      appliedHistoryVersionRef.current.set(threadKey, historyVersion);
      if (normalizedHistory.length > 0) messageCacheRef.current.set(threadKey, normalizedHistory);
      return normalizedHistory;
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [loading, historical, historyVersion, threadKey]);

  useEffect(() => {
    if (!threadKey) return;
    return client.onSessionUpdate((updatedChatId, scope) => {
      if (updatedChatId !== threadKey) return;
      void refreshSessionDetail();
      if (scope === "metadata") return;
      pendingCanonicalHydrateRef.current.add(threadKey);
      refreshHistory();
    });
  }, [client, refreshHistory, refreshSessionDetail, threadKey]);

  useEffect(() => {
    if (!threadKey) {
      bottomScrolledThreadKeyRef.current = null;
      return;
    }
    if (loading || bottomScrolledThreadKeyRef.current === threadKey) return;
    bottomScrolledThreadKeyRef.current = threadKey;
    setScrollToBottomSignal((value) => value + 1);
  }, [loading, threadKey]);

  useEffect(() => {
    if (streamChatId) return;
    setMessages(projectWebuiThreadMessages(historical));
  }, [historical, setMessages, streamChatId]);

  useLayoutEffect(() => {
    if (threadKey) {
      const prev = prevThreadKeyForCacheRef.current;
      if (prev && prev !== threadKey) {
        messageCacheRef.current.set(prev, projectWebuiThreadMessages(messages));
        skipLayoutCacheRef.current = true;
      }
      prevThreadKeyForCacheRef.current = threadKey;
    } else {
      if (prevThreadKeyForCacheRef.current) {
        messageCacheRef.current.set(
          prevThreadKeyForCacheRef.current,
          projectWebuiThreadMessages(messages),
        );
        skipLayoutCacheRef.current = true;
      }
      prevThreadKeyForCacheRef.current = null;
    }
  }, [messages, threadKey]);

  // Persist thread to in-memory cache after paint so ``useNanobotStream``'s chat switch
  // ``useEffect`` reset has flushed; ``skipLayoutCacheRef`` drops the first run that still
  // sees the *previous* chat's ``messages`` (avoids stale rows leaking across sessions).
  useEffect(() => {
    if (!threadKey) {
      return;
    }
    if (skipLayoutCacheRef.current) {
      skipLayoutCacheRef.current = false;
      return;
    }
    if (loading) {
      return;
    }
    messageCacheRef.current.set(threadKey, projectWebuiThreadMessages(messages));
  }, [loading, messages, threadKey]);

  useEffect(() => {
    if (!streamChatId || isWebSocketSession === false) return;
    const pending = pendingFirstRef.current;
    if (!pending) return;
    pendingFirstRef.current = null;
    setScrollToLatestUserPromptSignal((value) => value + 1);
    send(pending.content, pending.images, pending.options);
    setBooting(false);
  }, [isWebSocketSession, send, streamChatId]);

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

  const handleWelcomeSend = useCallback(
    async (content: string, images?: SendImage[], options?: SendOptions) => {
      if (booting) return;
      setBooting(true);
      pendingFirstRef.current = { content, images, options: withWorkspaceScope(options) };
      const newId = await onCreateChat?.(workspaceScope);
      if (!newId) {
        pendingFirstRef.current = null;
        setBooting(false);
      }
    },
    [booting, onCreateChat, withWorkspaceScope, workspaceScope],
  );

  const handleThreadSend = useCallback(
    (content: string, images?: SendImage[], options?: SendOptions) => {
      setScrollToLatestUserPromptSignal((value) => value + 1);
      send(content, images, withWorkspaceScope(options));
    },
    [send, withWorkspaceScope],
  );

  useEffect(() => {
    if (!remoteReplyPending) return;
    const baseline = remoteReplyBaselineRef.current;
    if (!baseline) return;
    const assistantMessages = messages.filter(
      (message) =>
        message.role === "assistant"
        && !message.id.startsWith(LINKED_REPLY_PLACEHOLDER_ID_PREFIX),
    );
    const hasFreshAssistantReply = assistantMessages.some(
      (message) => message.createdAt >= baseline.startedAt,
    );
    if (!hasFreshAssistantReply && assistantMessages.length <= baseline.assistantCount) return;
    setRemoteReplyPending(false);
    remoteReplyBaselineRef.current = null;
    setMessages((prev) =>
      prev.filter((message) => !message.id.startsWith(LINKED_REPLY_PLACEHOLDER_ID_PREFIX)),
    );
  }, [messages, remoteReplyPending, setMessages]);

  const handleBridgedSessionSend = useCallback(async (
    content: string,
    images?: SendImage[],
  ) => {
    if (!historyKey || session?.channel !== "telegram" || remoteReplyPending) return;
    const trimmedContent = content.trim();
    const wireMedia = images?.map((image) => image.media);
    if (!trimmedContent && (!wireMedia || wireMedia.length === 0)) return;

    setScrollToLatestUserPromptSignal((value) => value + 1);
    const startedAt = Date.now();
    const assistantCountBefore = messages.filter((message) => message.role === "assistant").length;
    remoteReplyBaselineRef.current = {
      assistantCount: assistantCountBefore,
      startedAt,
    };
    setRemoteReplyPending(true);
    setMessages((prev) => [
      ...prev,
      {
        id: crypto.randomUUID(),
        role: "user",
        content,
        ...(images?.length ? { images: images.map((image) => image.preview) } : {}),
        createdAt: startedAt,
      },
      {
        id: `${LINKED_REPLY_PLACEHOLDER_ID_PREFIX}${startedAt}`,
        role: "assistant",
        content: linkedReplyWaitingText,
        createdAt: startedAt + 1,
      },
    ]);

    try {
      client.sendSessionMessage(historyKey, content, wireMedia);
      for (let attempt = 0; attempt < 20; attempt += 1) {
        const body = await fetchSessionMessages(token, historyKey);
        const hydrated = projectWebuiThreadMessages(hydrateSessionMessages(body));
        const assistantCount = hydrated.filter((message) => message.role === "assistant").length;
        if (assistantCount > assistantCountBefore) {
          setMessages(hydrated);
          if (threadKey) messageCacheRef.current.set(threadKey, hydrated);
          refreshHistory();
          setRemoteReplyPending(false);
          remoteReplyBaselineRef.current = null;
          return;
        }
        await new Promise((resolve) => window.setTimeout(resolve, 250));
      }
      refreshHistory();
    } finally {
      setRemoteReplyPending(false);
      remoteReplyBaselineRef.current = null;
      setMessages((prev) =>
        prev.filter((message) => !message.id.startsWith(LINKED_REPLY_PLACEHOLDER_ID_PREFIX)),
      );
    }
  }, [
    client,
    historyKey,
    linkedReplyWaitingText,
    messages,
    refreshHistory,
    remoteReplyPending,
    session?.channel,
    setMessages,
    threadKey,
    token,
  ]);

  const handleOpenFilePreview = useCallback((path: string) => {
    if (filePreviewCloseTimerRef.current !== null) {
      window.clearTimeout(filePreviewCloseTimerRef.current);
      filePreviewCloseTimerRef.current = null;
    }
    setFilePreviewClosing(false);
    setFilePreviewPath(path);
  }, []);

  const handleCloseFilePreview = useCallback(() => {
    if (!filePreviewPath || filePreviewClosing) return;
    setFilePreviewClosing(true);
    filePreviewCloseTimerRef.current = window.setTimeout(() => {
      filePreviewCloseTimerRef.current = null;
      setFilePreviewPath(null);
      setFilePreviewClosing(false);
    }, FILE_PREVIEW_CLOSE_ANIMATION_MS);
  }, [filePreviewClosing, filePreviewPath]);

  const handleFilePreviewResizeStart = useCallback((event: ReactPointerEvent<HTMLButtonElement>) => {
    event.preventDefault();
    event.stopPropagation();
    const panel = event.currentTarget.closest<HTMLElement>("[data-file-preview-panel]");
    const shellRect = shellRef.current?.getBoundingClientRect();
    const rightEdge = shellRect?.right ?? window.innerWidth;
    const maxWidth = maxFilePreviewWidth(shellRect?.width ?? window.innerWidth);
    const originalBodyCursor = document.body.style.cursor;
    const originalBodyUserSelect = document.body.style.userSelect;
    const originalPanelTransition = panel?.style.transition ?? "";
    let nextWidth = filePreviewWidthRef.current;
    let frame: number | null = null;

    document.body.style.cursor = "col-resize";
    document.body.style.userSelect = "none";
    if (panel) panel.style.transition = "none";

    const applyWidth = (clientX: number) => {
      nextWidth = clampFilePreviewWidth(rightEdge - clientX, maxWidth);
      filePreviewWidthRef.current = nextWidth;
      if (frame !== null) return;
      frame = window.requestAnimationFrame(() => {
        frame = null;
        panel?.style.setProperty("--file-preview-width", `${nextWidth}px`);
        panel?.style.setProperty("--file-preview-slot-width", `${nextWidth}px`);
      });
    };
    const handlePointerMove = (moveEvent: PointerEvent) => {
      moveEvent.preventDefault();
      applyWidth(moveEvent.clientX);
    };
    const handlePointerUp = () => {
      if (frame !== null) {
        window.cancelAnimationFrame(frame);
        frame = null;
      }
      panel?.style.setProperty("--file-preview-width", `${nextWidth}px`);
      panel?.style.setProperty("--file-preview-slot-width", `${nextWidth}px`);
      if (panel) panel.style.transition = originalPanelTransition;
      setFilePreviewWidth(nextWidth);
      document.body.style.cursor = originalBodyCursor;
      document.body.style.userSelect = originalBodyUserSelect;
      window.removeEventListener("pointermove", handlePointerMove);
      window.removeEventListener("pointerup", handlePointerUp);
      window.removeEventListener("pointercancel", handlePointerUp);
    };

    applyWidth(event.clientX);
    window.addEventListener("pointermove", handlePointerMove);
    window.addEventListener("pointerup", handlePointerUp);
    window.addEventListener("pointercancel", handlePointerUp);
  }, []);

  useEffect(() => {
    if (!filePreviewPath) return;
    const clampToShell = () => {
      const shellWidth = shellRef.current?.getBoundingClientRect().width ?? window.innerWidth;
      const maxWidth = maxFilePreviewWidth(shellWidth);
      const nextWidth = clampFilePreviewWidth(filePreviewWidthRef.current, maxWidth);
      filePreviewWidthRef.current = nextWidth;
      setFilePreviewWidth(nextWidth);
    };
    clampToShell();
    window.addEventListener("resize", clampToShell);
    return () => {
      window.removeEventListener("resize", clampToShell);
    };
  }, [filePreviewPath]);

  const handleForkFromMessage = useCallback(
    async (beforeUserIndex: number) => {
      if (!chatId || !onForkChat) return;
      const forkedChatId = await onForkChat(chatId, beforeUserIndex);
      if (!forkedChatId) return;
      messageCacheRef.current.delete(forkedChatId);
      appliedHistoryVersionRef.current.delete(forkedChatId);
      pendingCanonicalHydrateRef.current.add(forkedChatId);
    },
    [chatId, onForkChat],
  );

  const handleSelectModelTarget = useCallback(async (targetName: string | null) => {
    if (!historyKey) return;
    setModelTargetPending(true);
    try {
      if (targetName) {
        await selectSessionModelTarget(token, historyKey, targetName);
      } else {
        await clearSessionModelTarget(token, historyKey);
      }
      await Promise.allSettled([
        refreshSessionDetail(),
        Promise.resolve(onRefreshSessions?.()),
      ]);
    } finally {
      setModelTargetPending(false);
    }
  }, [historyKey, onRefreshSessions, refreshSessionDetail, token]);

  const handleClearActionResult = useCallback(async () => {
    if (!historyKey) return;
    await clearSessionActionResult(token, historyKey);
    await Promise.allSettled([
      refreshSessionDetail(),
      Promise.resolve(onRefreshSessions?.()),
    ]);
  }, [historyKey, onRefreshSessions, refreshSessionDetail, token]);

  const handleClearProactiveSummary = useCallback(async () => {
    if (!historyKey) return;
    await clearSessionProactiveSummary(token, historyKey);
    await Promise.allSettled([
      refreshSessionDetail(),
      Promise.resolve(onRefreshSessions?.()),
    ]);
  }, [historyKey, onRefreshSessions, refreshSessionDetail, token]);

  const composer = (
    <>
      {streamError ? (
        <StreamErrorNotice
          error={streamError}
          onDismiss={dismissStreamError}
        />
      ) : null}
      {session ? (
        <ThreadComposer
          onSend={isWebSocketSession ? handleThreadSend : handleBridgedSessionSend}
          disabled={isWebSocketSession ? !chatId : !historyKey || remoteReplyPending}
          isStreaming={isStreaming}
          placeholder={
            showHeroComposer
              ? t("thread.composer.placeholderHero")
              : t("thread.composer.placeholderThread")
          }
          modelLabel={modelBadgeLabel}
          modelProvider={modelBadge.provider}
          modelProviderLabel={modelBadge.providerLabel}
          modelNeedsSetup={modelBadge.needsSetup}
          onModelBadgeClick={modelBadge.needsSetup ? onOpenModelSettings : undefined}
          modelTargets={bootstrapModelTargets}
          activeModelTarget={currentActiveTarget}
          modelTargetPending={modelTargetPending}
          onSelectModelTarget={isWebSocketSession && historyKey ? handleSelectModelTarget : undefined}
          variant={showHeroComposer ? "hero" : "thread"}
          slashCommands={slashCommands}
          cliApps={cliApps}
          mcpPresets={mcpPresets}
          onStop={isWebSocketSession ? stop : undefined}
          onTranscribeAudio={transcribeAudio}
          runStartedAt={runStartedAt}
          goalState={goalState}
          workspaceScope={workspaceScope}
          workspaceDefaultScope={workspaceDefaultScope}
          workspaceControls={workspaceControls}
          workspaceScopeDisabled={workspaceScopeDisabled}
          workspaceError={workspaceError}
          onWorkspaceScopeChange={onWorkspaceScopeChange}
          pendingQueueKey={threadKey}
        />
      ) : (
        <ThreadComposer
          onSend={handleWelcomeSend}
          disabled={booting}
          isStreaming={isStreaming}
          placeholder={
            booting
              ? t("thread.composer.placeholderOpening")
              : t("thread.composer.placeholderHero")
          }
          modelLabel={modelBadgeLabel}
          modelProvider={modelBadge.provider}
          modelProviderLabel={modelBadge.providerLabel}
          modelNeedsSetup={modelBadge.needsSetup}
          onModelBadgeClick={modelBadge.needsSetup ? onOpenModelSettings : undefined}
          modelTargets={bootstrapModelTargets}
          activeModelTarget={currentActiveTarget}
          variant="hero"
          slashCommands={slashCommands}
          cliApps={cliApps}
          mcpPresets={mcpPresets}
          runStartedAt={runStartedAt}
          onTranscribeAudio={transcribeAudio}
          goalState={goalState}
          workspaceScope={workspaceScope}
          workspaceDefaultScope={workspaceDefaultScope}
          workspaceControls={workspaceControls}
          workspaceScopeDisabled={workspaceScopeDisabled}
          workspaceError={workspaceError}
          onWorkspaceScopeChange={onWorkspaceScopeChange}
        />
      )}
    </>
  );

  const emptyState = loading ? (
    <div className="flex h-full items-center justify-center text-sm text-muted-foreground">
      {t("thread.loadingConversation")}
    </div>
  ) : (
    <div className="flex w-full flex-col items-center text-center animate-in fade-in-0 slide-in-from-bottom-2 duration-500">
      <h1 className="max-w-[44rem] text-balance text-[34px] font-normal leading-[1.08] tracking-normal text-foreground sm:text-[48px] sm:leading-tight">
        {t(heroGreetingKey)}
      </h1>
    </div>
  );
  const sessionInfoAction = historyKey ? (
    <SessionInfoPopover
      session={mergedSession ?? session!}
      token={token}
      modelTargets={bootstrapModelTargets}
      onClearActionResult={handleClearActionResult}
      onClearProactiveSummary={handleClearProactiveSummary}
    />
  ) : undefined;
  const promptNavigatorAction = historyKey ? (
    <PromptNavigator
      messages={displayMessages}
      onJumpToPrompt={(promptId) => viewportRef.current?.jumpToUserPrompt(promptId)}
    />
  ) : undefined;

  return (
    <section ref={shellRef} className="relative flex min-h-0 flex-1 overflow-hidden">
      <div className="relative flex min-w-0 flex-1 flex-col overflow-hidden">
        {!hideHeader ? (
          <ThreadHeader
            title={title}
            onToggleSidebar={onToggleSidebar}
            theme={theme}
            onToggleTheme={onToggleTheme}
            hideSidebarToggleForHostChrome={hideSidebarToggleForHostChrome}
            hostChromeTitleInset={hostChromeTitleInset}
            hideThemeButton={hideThemeButton}
            minimal={!session && !loading}
            promptNavigatorAction={promptNavigatorAction}
            sessionInfoAction={sessionInfoAction}
          />
        ) : null}
        <ThreadViewport
          ref={viewportRef}
          messages={displayMessages}
          isStreaming={isStreaming}
          emptyState={emptyState}
          composer={composer}
          scrollToBottomSignal={scrollToBottomSignal}
          scrollToLatestUserPromptSignal={scrollToLatestUserPromptSignal}
          conversationKey={historyKey}
          showScrollToBottomButton={!!session}
          cliApps={cliApps}
          mcpPresets={mcpPresets}
          forkBoundaryMessageCount={forkBoundaryMessageCount}
          hasMoreBefore={hasMoreBefore}
          loadingOlder={loadingOlder}
          userMessageOffset={userMessageOffset}
          onLoadOlder={loadOlder}
          onOpenFilePreview={historyKey ? handleOpenFilePreview : undefined}
          onForkFromMessage={onForkChat ? handleForkFromMessage : undefined}
        />
      </div>
      {filePreviewPath && historyKey ? (
        <FilePreviewPanel
          sessionKey={historyKey}
          path={filePreviewPath}
          token={token}
          desktopWidth={filePreviewWidth}
          isClosing={filePreviewClosing}
          onResizeStart={handleFilePreviewResizeStart}
          onClose={handleCloseFilePreview}
        />
      ) : null}
    </section>
  );
}
