import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";

import { ThreadComposer } from "@/components/thread/ThreadComposer";
import { ThreadHeader } from "@/components/thread/ThreadHeader";
import { StreamErrorNotice } from "@/components/thread/StreamErrorNotice";
import { ThreadViewport } from "@/components/thread/ThreadViewport";
import { useNanobotStream } from "@/hooks/useNanobotStream";
import { useSessionHistory } from "@/hooks/useSessions";
import { ApiError, fetchSessionModelTarget, selectSessionModelTarget } from "@/lib/api";
import type { ChatSummary, ModelTargetOption, SessionModelTargetResponse, UIMessage } from "@/lib/types";
import { createUuid } from "@/lib/uuid";
import { useClient } from "@/providers/ClientProvider";

interface ThreadShellProps {
  session: ChatSummary | null;
  title: string;
  onToggleSidebar: () => void;
  onGoHome: () => void;
  onNewChat: () => Promise<string | null>;
  hideSidebarToggleOnDesktop?: boolean;
}

function toModelBadgeLabel(
  modelName: string | null,
  activeTarget: string | null,
): string | null {
  if (typeof activeTarget === "string") {
    const target = activeTarget.trim();
    if (target && target !== "default") {
      return target === "smart_router" ? "smart-router" : target;
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
  title,
  onToggleSidebar,
  onGoHome,
  onNewChat,
  hideSidebarToggleOnDesktop = false,
}: ThreadShellProps) {
  const { t } = useTranslation();
  const chatId = session?.chatId ?? null;
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
  const pendingFirstRef = useRef<string | null>(null);
  const messageCacheRef = useRef<Map<string, UIMessage[]>>(new Map());

  const initial = useMemo(() => {
    if (!chatId) return historical;
    return messageCacheRef.current.get(chatId) ?? historical;
  }, [chatId, historical]);
  const {
    messages,
    isStreaming,
    send,
    setMessages,
    streamError,
    dismissStreamError,
  } = useNanobotStream(chatId, initial);
  const showHeroComposer = messages.length === 0 && !loading;

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
      />
      <ThreadViewport
        messages={messages}
        isStreaming={isStreaming}
        onApprovalResponse={handleApprovalResponse}
        emptyState={emptyState}
        composer={
          <>
            {streamError ? (
              <StreamErrorNotice
                error={streamError}
                onDismiss={dismissStreamError}
              />
            ) : null}
            {session ? (
              <ThreadComposer
                onSend={send}
                disabled={!chatId}
                placeholder={
                  showHeroComposer
                    ? t("thread.composer.placeholderHero")
                    : t("thread.composer.placeholderThread")
                }
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
