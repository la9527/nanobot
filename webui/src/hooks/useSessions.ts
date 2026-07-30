import { useCallback, useEffect, useRef, useState } from "react";

import { useClient } from "@/providers/ClientProvider";
import i18n from "@/i18n";
import {
  ApiError,
  deleteSession as apiDeleteSession,
  fetchSessionAutomations,
  fetchSessionMessages,
  fetchWebuiThread,
  listSessions,
} from "@/lib/api";
import { hasPendingAgentActivity } from "@/lib/activity-timeline";
import { deriveTitle } from "@/lib/format";
import { toMediaAttachment } from "@/lib/media";
import type {
  ChatSummary,
  SessionAutomationJob,
  SessionDeleteResult,
  SessionMessagesResponse,
  UIMessage,
  WorkspaceScopePayload,
} from "@/lib/types";

const EMPTY_MESSAGES: UIMessage[] = [];
const INITIAL_HISTORY_PAGE_LIMIT = 160;
const OLDER_HISTORY_PAGE_LIMIT = 120;
const CHAT_CREATE_TIMEOUT_MS = 60_000;
const REMOTE_SESSION_REFRESH_MS = 1_000;

type SessionHistoryMessage = SessionMessagesResponse["messages"][number];

function persistedMessagesToUi(messages: UIMessage[]): UIMessage[] {
  return messages.map((m, idx) => ({
    ...m,
    id: m.id ?? `hist-${idx}`,
    createdAt: typeof m.createdAt === "number" ? m.createdAt : Date.now(),
  }));
}

function shouldPollSessionHistory(key: string): boolean {
  return key.startsWith("telegram:");
}

function normalizeDuplicateText(content: string): string {
  return content.replace(/\s+/gu, " ").trim();
}

function historyMessageRichness(message: SessionHistoryMessage): number {
  let score = 0;
  if (message.metadata?.render_as === "text") score += 1;
  if (message.visible_reasoning?.trim()) score += 4;
  if (Array.isArray(message.buttons) && message.buttons.some((row) => row.length > 0)) score += 2;
  if (Array.isArray(message.media_urls) && message.media_urls.length > 0) score += 2;
  return score;
}

function haveSameTurnId(
  previous: SessionHistoryMessage,
  current: SessionHistoryMessage,
): boolean {
  return (
    typeof previous.turn_id === "string"
    && previous.turn_id.trim().length > 0
    && previous.turn_id.trim() === current.turn_id?.trim()
  );
}

function areDuplicateAssistantHistoryRows(
  previous: SessionHistoryMessage,
  current: SessionHistoryMessage,
): boolean {
  return (
    previous.role === "assistant"
    && current.role === "assistant"
    && (
      haveSameTurnId(previous, current)
      || normalizeDuplicateText(previous.content) === normalizeDuplicateText(current.content)
    )
    && JSON.stringify(previous.buttons ?? []) === JSON.stringify(current.buttons ?? [])
    && JSON.stringify(previous.media_urls ?? []) === JSON.stringify(current.media_urls ?? [])
  );
}

function collapseDuplicateAssistantHistoryRows(
  messages: SessionMessagesResponse["messages"],
): SessionMessagesResponse["messages"] {
  const deduped: SessionHistoryMessage[] = [];
  for (const message of messages) {
    if (message.role !== "user" && message.role !== "assistant") continue;
    const previous = deduped[deduped.length - 1];
    if (previous && areDuplicateAssistantHistoryRows(previous, message)) {
      deduped[deduped.length - 1] = historyMessageRichness(message) > historyMessageRichness(previous)
        ? message
        : previous;
      continue;
    }
    deduped.push(message);
  }
  return deduped;
}

function collapseConsecutiveAssistantDuplicates(messages: UIMessage[]): UIMessage[] {
  const deduped: UIMessage[] = [];
  for (const message of messages) {
    const previous = deduped[deduped.length - 1];
    if (
      previous
      && previous.role === "assistant"
      && message.role === "assistant"
      && !previous.isStreaming
      && !message.isStreaming
      && normalizeDuplicateText(previous.content) === normalizeDuplicateText(message.content)
    ) {
      deduped[deduped.length - 1] = message.reasoning && !previous.reasoning
        ? message
        : previous;
      continue;
    }
    deduped.push(message);
  }
  return deduped;
}

export function hydrateSessionMessages(body: SessionMessagesResponse): UIMessage[] {
  const hydrated: UIMessage[] = collapseDuplicateAssistantHistoryRows(body.messages).flatMap((m, idx) => {
    if (m.role !== "user" && m.role !== "assistant") return [];
    if (typeof m.content !== "string") return [];
    const createdAt = m.timestamp ? Date.parse(m.timestamp) : Date.now();
    const media =
      Array.isArray(m.media_urls) && m.media_urls.length > 0
        ? m.media_urls.map((entry) => toMediaAttachment(entry))
        : undefined;
    const images =
      m.role === "user" && media?.length
        ? media
            .filter((item) => item.kind === "image")
            .map((item) => ({ url: item.url, name: item.name }))
        : undefined;
    const turnId = typeof m.turn_id === "string" && m.turn_id.trim() ? m.turn_id.trim() : null;
    const messageId = turnId ?? `hist-${idx}`;
    const hydratedMessage: UIMessage = {
      id: messageId,
      role: m.role,
      content: m.content,
      createdAt,
      ...(images ? { images } : {}),
      ...(media ? { media } : {}),
      ...(Array.isArray(m.buttons) && m.buttons.some((row) => row.length > 0)
        ? { buttons: m.buttons }
        : {}),
    };
    const visibleReasoning = m.role === "assistant" && typeof m.visible_reasoning === "string"
      ? m.visible_reasoning.trim()
      : "";
    if (!visibleReasoning) return [hydratedMessage];
    return [
      {
        id: `${messageId}-reasoning`,
        role: "tool",
        kind: "trace",
        content: visibleReasoning,
        traces: [visibleReasoning],
        createdAt: Math.max(0, createdAt - 1),
      },
      hydratedMessage,
    ];
  });

  return collapseConsecutiveAssistantDuplicates(hydrated);
}

function hasPendingToolCallsFromThread(
  body: Awaited<ReturnType<typeof fetchWebuiThread>>,
  messages: UIMessage[],
): boolean {
  if (typeof body?.has_pending_tool_calls === "boolean") {
    return body.has_pending_tool_calls;
  }
  return hasPendingAgentActivity(messages);
}

/** Sidebar state: fetches the full session list and exposes create / delete actions. */
export function useSessions(): {
  sessions: ChatSummary[];
  loading: boolean;
  error: string | null;
  refresh: () => Promise<void>;
  createChat: (workspaceScope?: WorkspaceScopePayload | null) => Promise<string>;
  forkChat: (sourceChatId: string, beforeUserIndex: number, title?: string) => Promise<string>;
  deleteChat: (
    key: string,
    options?: { deleteAutomations?: boolean },
  ) => Promise<SessionDeleteResult>;
  getSessionAutomations: (key: string) => Promise<SessionAutomationJob[]>;
} {
  const { client, token } = useClient();
  const [sessions, setSessions] = useState<ChatSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const tokenRef = useRef(token);
  const optimisticKeysRef = useRef<Set<string>>(new Set());
  tokenRef.current = token;

  const refresh = useCallback(async () => {
    try {
      setLoading(true);
      const rows = await listSessions(tokenRef.current);
      const serverKeys = new Set(rows.map((row) => row.key));
      setSessions((prev) => [
        ...rows,
        ...prev.filter(
          (session) =>
            optimisticKeysRef.current.has(session.key) &&
            !serverKeys.has(session.key),
        ),
      ]);
      for (const key of Array.from(optimisticKeysRef.current)) {
        if (serverKeys.has(key)) optimisticKeysRef.current.delete(key);
      }
      setError(null);
    } catch (e) {
      const msg =
        e instanceof ApiError ? `HTTP ${e.status}` : (e as Error).message;
      setError(msg);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  useEffect(() => {
    return client.onSessionUpdate(() => {
      void refresh();
    });
  }, [client, refresh]);

  const createChat = useCallback(async (workspaceScope?: WorkspaceScopePayload | null): Promise<string> => {
    const chatId = await client.newChat(CHAT_CREATE_TIMEOUT_MS, workspaceScope);
    const key = `websocket:${chatId}`;
    optimisticKeysRef.current.add(key);
    // Optimistic insert; a subsequent refresh will replace it with the
    // authoritative row once the server persists the session.
    setSessions((prev) => [
      {
        key,
        channel: "websocket",
        chatId,
        createdAt: new Date().toISOString(),
        updatedAt: new Date().toISOString(),
        title: "",
        preview: "",
        workspaceScope: workspaceScope ?? null,
      },
      ...prev.filter((s) => s.key !== key),
    ]);
    return chatId;
  }, [client]);

  const forkChat = useCallback(async (
    sourceChatId: string,
    beforeUserIndex: number,
    title?: string,
  ): Promise<string> => {
    const chatId = await client.forkChat(
      sourceChatId,
      beforeUserIndex,
      title,
      CHAT_CREATE_TIMEOUT_MS,
    );
    const key = `websocket:${chatId}`;
    optimisticKeysRef.current.add(key);
    setSessions((prev) => [
      {
        key,
        channel: "websocket",
        chatId,
        createdAt: new Date().toISOString(),
        updatedAt: new Date().toISOString(),
        title: title ?? "",
        preview: "",
        workspaceScope: null,
      },
      ...prev.filter((s) => s.key !== key),
    ]);
    return chatId;
  }, [client]);

  const deleteChat = useCallback(
    async (key: string, options?: { deleteAutomations?: boolean }) => {
      const result = await apiDeleteSession(tokenRef.current, key, options);
      if (!result.deleted) return result;
      optimisticKeysRef.current.delete(key);
      setSessions((prev) => prev.filter((s) => s.key !== key));
      return result;
    },
    [],
  );

  const getSessionAutomations = useCallback(async (key: string) => {
    const result = await fetchSessionAutomations(tokenRef.current, key);
    return result.jobs;
  }, []);

  return {
    sessions,
    loading,
    error,
    refresh,
    createChat,
    forkChat,
    deleteChat,
    getSessionAutomations,
  };
}

/** Lazy-load a session's on-disk messages the first time the UI displays it. */
export function useSessionHistory(key: string | null): {
  messages: UIMessage[];
  loading: boolean;
  loadingOlder: boolean;
  error: string | null;
  refresh: () => void;
  loadOlder: () => Promise<void>;
  hasMoreBefore: boolean;
  userMessageOffset: number;
  version: number;
  forkBoundaryMessageCount: number | null;
  /** ``true`` when the replayed transcript ends with a trace row (turn still in flight). */
  hasPendingToolCalls: boolean;
} {
  const { token } = useClient();
  const loadingOlderRef = useRef(false);
  const [refreshSeq, setRefreshSeq] = useState(0);
  const refresh = useCallback(() => {
    setRefreshSeq((value) => value + 1);
  }, []);
  const [state, setState] = useState<{
    key: string | null;
    messages: UIMessage[];
    loading: boolean;
    loadingOlder: boolean;
    error: string | null;
    hasPendingToolCalls: boolean;
    forkBoundaryMessageCount: number | null;
    beforeCursor: string | null;
    hasMoreBefore: boolean;
    userMessageOffset: number;
    version: number;
  }>({
    key: null,
    messages: [],
    loading: false,
    loadingOlder: false,
    error: null,
    hasPendingToolCalls: false,
    forkBoundaryMessageCount: null,
    beforeCursor: null,
    hasMoreBefore: false,
    userMessageOffset: 0,
    version: 0,
  });

  useEffect(() => {
    if (!key || !shouldPollSessionHistory(key)) return;
    const timer = window.setInterval(() => {
      setRefreshSeq((value) => value + 1);
    }, REMOTE_SESSION_REFRESH_MS);
    return () => {
      window.clearInterval(timer);
    };
  }, [key]);

  useEffect(() => {
    if (!key) {
      setState({
        key: null,
        messages: [],
        loading: false,
        loadingOlder: false,
        error: null,
        hasPendingToolCalls: false,
        forkBoundaryMessageCount: null,
        beforeCursor: null,
        hasMoreBefore: false,
        userMessageOffset: 0,
        version: 0,
      });
      return;
    }
    let cancelled = false;
    // Mark the new key as loading immediately so callers never see stale
    // messages from the previous session during the render right after a switch.
    setState((prev) => prev.key === key
      ? { ...prev, loading: true, loadingOlder: false, error: null }
      : {
          key,
          messages: [],
          loading: true,
          loadingOlder: false,
          error: null,
          hasPendingToolCalls: false,
          forkBoundaryMessageCount: null,
          beforeCursor: null,
          hasMoreBefore: false,
          userMessageOffset: 0,
          version: 0,
        });
    (async () => {
      try {
        if (shouldPollSessionHistory(key)) {
          const body = await fetchSessionMessages(token, key);
          if (cancelled) return;
          const ui = hydrateSessionMessages(body);
          setState((prev) => ({
            key,
            messages: ui,
            loading: false,
            loadingOlder: false,
            error: null,
            hasPendingToolCalls: hasPendingAgentActivity(ui),
            forkBoundaryMessageCount: null,
            beforeCursor: null,
            hasMoreBefore: false,
            userMessageOffset: 0,
            version: prev.key === key ? prev.version + 1 : 1,
          }));
          return;
        }
        const body = await fetchWebuiThread(token, key, {
          limit: INITIAL_HISTORY_PAGE_LIMIT,
          direction: "latest",
        });
        if (cancelled) return;
        if (!body?.messages?.length) {
          setState((prev) => ({
            key,
            messages: [],
            loading: false,
            loadingOlder: false,
            error: null,
            hasPendingToolCalls: false,
            forkBoundaryMessageCount: null,
            beforeCursor: null,
            hasMoreBefore: false,
            userMessageOffset: 0,
            version: prev.key === key ? prev.version + 1 : 1,
          }));
          return;
        }
        const ui = persistedMessagesToUi(body.messages);
        const hasPending = hasPendingToolCallsFromThread(body, ui);
        const forkBoundary = typeof body.fork_boundary_message_count === "number"
          ? Math.max(0, Math.min(body.fork_boundary_message_count, ui.length))
          : null;
        setState((prev) => ({
          key,
          messages: ui,
          loading: false,
          loadingOlder: false,
          error: null,
          hasPendingToolCalls: hasPending,
          forkBoundaryMessageCount: forkBoundary,
          beforeCursor: body.page?.before_cursor ?? null,
          hasMoreBefore: body.page?.has_more_before === true,
          userMessageOffset: Math.max(0, body.page?.user_message_offset ?? 0),
          version: prev.key === key ? prev.version + 1 : 1,
        }));
      } catch (e) {
        if (cancelled) return;
        if (e instanceof ApiError && e.status === 404) {
          setState((prev) => ({
            key,
            messages: [],
            loading: false,
            loadingOlder: false,
            error: null,
            hasPendingToolCalls: false,
            forkBoundaryMessageCount: null,
            beforeCursor: null,
            hasMoreBefore: false,
            userMessageOffset: 0,
            version: prev.key === key ? prev.version + 1 : 1,
          }));
        } else {
          setState((prev) => ({
            key,
            messages: [],
            loading: false,
            loadingOlder: false,
            error: (e as Error).message,
            hasPendingToolCalls: false,
            forkBoundaryMessageCount: null,
            beforeCursor: null,
            hasMoreBefore: false,
            userMessageOffset: 0,
            version: prev.key === key ? prev.version : 0,
          }));
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [key, token, refreshSeq]);

  const loadOlder = useCallback(async () => {
    if (!key || loadingOlderRef.current) return;
    if (shouldPollSessionHistory(key)) return;
    const before = state.key === key ? state.beforeCursor : null;
    if (!before || !state.hasMoreBefore) return;
    loadingOlderRef.current = true;
    setState((prev) => prev.key === key ? { ...prev, loadingOlder: true, error: null } : prev);
    try {
      const body = await fetchWebuiThread(token, key, {
        limit: OLDER_HISTORY_PAGE_LIMIT,
        before,
      });
      setState((prev) => {
        if (prev.key !== key) return prev;
        if (!body?.messages?.length) {
          return {
            ...prev,
            loadingOlder: false,
            hasMoreBefore: false,
            beforeCursor: null,
          };
        }
        const older = persistedMessagesToUi(body.messages);
        const olderBoundary = typeof body.fork_boundary_message_count === "number"
          ? Math.max(0, Math.min(body.fork_boundary_message_count, older.length))
          : null;
        const shiftedBoundary = prev.forkBoundaryMessageCount === null
          ? null
          : prev.forkBoundaryMessageCount + older.length;
        const nextMessages = [...older, ...prev.messages];
        return {
          ...prev,
          messages: nextMessages,
          loadingOlder: false,
          error: null,
          hasPendingToolCalls: hasPendingAgentActivity(nextMessages),
          forkBoundaryMessageCount: olderBoundary ?? shiftedBoundary,
          beforeCursor: body.page?.before_cursor ?? null,
          hasMoreBefore: body.page?.has_more_before === true,
          userMessageOffset: Math.max(0, body.page?.user_message_offset ?? 0),
          version: prev.version + 1,
        };
      });
    } catch (e) {
      setState((prev) => prev.key === key
        ? {
            ...prev,
            loadingOlder: false,
            error: (e as Error).message,
          }
        : prev);
    } finally {
      loadingOlderRef.current = false;
    }
  }, [
    key,
    state.beforeCursor,
    state.hasMoreBefore,
    state.key,
    token,
  ]);

  if (!key) {
    return {
      messages: EMPTY_MESSAGES,
      loading: false,
      loadingOlder: false,
      error: null,
      refresh,
      loadOlder,
      hasMoreBefore: false,
      userMessageOffset: 0,
      version: 0,
      forkBoundaryMessageCount: null,
      hasPendingToolCalls: false,
    };
  }

  // Even before the effect above commits its loading state, never surface the
  // previous session's payload for a brand-new key.
  if (state.key !== key) {
    return {
      messages: EMPTY_MESSAGES,
      loading: true,
      loadingOlder: false,
      error: null,
      refresh,
      loadOlder,
      hasMoreBefore: false,
      userMessageOffset: 0,
      version: 0,
      forkBoundaryMessageCount: null,
      hasPendingToolCalls: false,
    };
  }

  return {
    messages: state.messages,
    loading: state.loading,
    loadingOlder: state.loadingOlder,
    error: state.error,
    refresh,
    loadOlder,
    hasMoreBefore: state.hasMoreBefore,
    userMessageOffset: state.userMessageOffset,
    version: state.version,
    forkBoundaryMessageCount: state.forkBoundaryMessageCount,
    hasPendingToolCalls: state.hasPendingToolCalls,
  };
}

/** Produce a compact display title for a session. */
export function sessionTitle(
  session: ChatSummary,
  firstUserMessage?: string,
): string {
  return deriveTitle(
    session.title || firstUserMessage || session.preview,
    i18n.t("chat.newChat"),
  );
}
