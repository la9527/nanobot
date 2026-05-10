import { useCallback, useEffect, useRef, useState } from "react";

import { useClient } from "@/providers/ClientProvider";
import i18n from "@/i18n";
import {
  ApiError,
  deleteSession as apiDeleteSession,
  fetchSessionMessages,
  listSessions,
} from "@/lib/api";
import { deriveTitle } from "@/lib/format";
import { toMediaAttachment } from "@/lib/media";
import type { ChatSummary, SessionMessagesResponse, UIMessage } from "@/lib/types";

const EMPTY_MESSAGES: UIMessage[] = [];
const REMOTE_SESSION_REFRESH_MS = 1000;

function shouldPollSessionHistory(key: string): boolean {
  return key.startsWith("telegram:");
}

export function hydrateSessionMessages(body: SessionMessagesResponse): UIMessage[] {
  return body.messages.flatMap((m, idx) => {
    if (m.role !== "user" && m.role !== "assistant") return [];
    if (typeof m.content !== "string") return [];
    const createdAt = m.timestamp ? Date.parse(m.timestamp) : Date.now();
    const media =
      Array.isArray(m.media_urls) && m.media_urls.length > 0
        ? m.media_urls.map((mu) => toMediaAttachment(mu))
        : undefined;
    const images =
      m.role === "user" && media?.length
        ? media
            .filter((item) => item.kind === "image")
            .map((item) => ({ url: item.url, name: item.name }))
        : undefined;
    const messageId = `hist-${idx}`;
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
    if (!visibleReasoning) {
      return [hydratedMessage];
    }
    return [
      {
        id: `${messageId}-reasoning`,
        role: "tool",
        kind: "trace",
        traceVariant: "status",
        content: visibleReasoning,
        traces: [visibleReasoning],
        createdAt: Math.max(0, createdAt - 1),
      },
      hydratedMessage,
    ];
  });
}

/** Sidebar state: fetches the full session list and exposes create / delete actions. */
export function useSessions(): {
  sessions: ChatSummary[];
  loading: boolean;
  error: string | null;
  refresh: () => Promise<void>;
  createChat: () => Promise<string>;
  deleteChat: (key: string) => Promise<void>;
} {
  const { client, token } = useClient();
  const [sessions, setSessions] = useState<ChatSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const tokenRef = useRef(token);
  tokenRef.current = token;

  const refresh = useCallback(async () => {
    try {
      setLoading(true);
      const rows = await listSessions(tokenRef.current);
      setSessions(rows);
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

  const createChat = useCallback(async (): Promise<string> => {
    const chatId = await client.newChat();
    const key = `websocket:${chatId}`;
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
      },
      ...prev.filter((s) => s.key !== key),
    ]);
    return chatId;
  }, [client]);

  const deleteChat = useCallback(
    async (key: string) => {
      await apiDeleteSession(tokenRef.current, key);
      setSessions((prev) => prev.filter((s) => s.key !== key));
    },
    [],
  );

  return { sessions, loading, error, refresh, createChat, deleteChat };
}

/** Lazy-load a session's on-disk messages the first time the UI displays it. */
export function useSessionHistory(key: string | null): {
  messages: UIMessage[];
  loading: boolean;
  error: string | null;
  /** ``true`` when the last persisted assistant turn has ``tool_calls`` but no
   *  final text yet — the model was still processing when the page loaded. */
  hasPendingToolCalls: boolean;
} {
  const { token } = useClient();
  const [state, setState] = useState<{
    key: string | null;
    messages: UIMessage[];
    loading: boolean;
    error: string | null;
    hasPendingToolCalls: boolean;
  }>({
    key: null,
    messages: [],
    loading: false,
    error: null,
    hasPendingToolCalls: false,
  });

  useEffect(() => {
    if (!key) {
      setState({
        key: null,
        messages: [],
        loading: false,
        error: null,
        hasPendingToolCalls: false,
      });
      return;
    }
    let cancelled = false;
    // Mark the new key as loading immediately so callers never see stale
    // messages from the previous session during the render right after a switch.
    setState({
      key,
      messages: [],
      loading: true,
      error: null,
      hasPendingToolCalls: false,
    });

    const load = async (mode: "initial" | "refresh") => {
      try {
        const body = await fetchSessionMessages(token, key);
        if (cancelled) return;
        const ui = hydrateSessionMessages(body);
        const lastRaw = [...body.messages]
          .reverse()
          .find((m) => m.role === "user" || m.role === "assistant");
        const hasPending =
          lastRaw?.role === "assistant" &&
          Array.isArray(lastRaw.tool_calls) &&
          lastRaw.tool_calls.length > 0;
        setState({
          key,
          messages: ui,
          loading: false,
          error: null,
          hasPendingToolCalls: hasPending,
        });
      } catch (e) {
        if (cancelled) return;
        if (e instanceof ApiError && e.status === 404) {
          setState({
            key,
            messages: [],
            loading: false,
            error: null,
            hasPendingToolCalls: false,
          });
          return;
          return;
        }
        if (mode === "refresh") {
          return;
        }
        setState({
          key,
          messages: [],
          loading: false,
          error: (e as Error).message,
          hasPendingToolCalls: false,
        });
      }
    };

    void load("initial");
    const refreshTimer = shouldPollSessionHistory(key)
      ? window.setInterval(() => {
          void load("refresh");
        }, REMOTE_SESSION_REFRESH_MS)
      : null;
    return () => {
      cancelled = true;
      if (refreshTimer !== null) {
        window.clearInterval(refreshTimer);
      }
    };
  }, [key, token]);

  if (!key) {
    return { messages: EMPTY_MESSAGES, loading: false, error: null, hasPendingToolCalls: false };
  }

  // Even before the effect above commits its loading state, never surface the
  // previous session's payload for a brand-new key.
  if (state.key !== key) {
    return { messages: EMPTY_MESSAGES, loading: true, error: null, hasPendingToolCalls: false };
  }

  return {
    messages: state.messages,
    loading: state.loading,
    error: state.error,
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
