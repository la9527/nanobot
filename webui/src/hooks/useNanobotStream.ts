import { useCallback, useEffect, useRef, useState } from "react";

import { useClient } from "@/providers/ClientProvider";
import { createUuid } from "@/lib/uuid";
import { toMediaAttachment } from "@/lib/media";
import type { StreamError } from "@/lib/nanobot-client";
import type {
  InboundEvent,
  OutboundImageGeneration,
  OutboundMedia,
  UIImage,
  UIMessage,
} from "@/lib/types";

interface StreamBuffer {
  /** ID of the assistant message currently receiving deltas. */
  messageId: string;
  /** Sequence of deltas accumulated in order. */
  parts: string[];
}

const LIVE_DUPLICATE_WINDOW_MS = 10_000;

function hydrateInitialMessages(
  initialMessages: UIMessage[],
  hasPendingToolCalls: boolean,
): UIMessage[] {
  if (!hasPendingToolCalls || initialMessages.length === 0) return initialMessages;
  const last = initialMessages[initialMessages.length - 1];
  if (last.kind !== "trace" || last.isStreaming) return initialMessages;
  return [
    ...initialMessages.slice(0, -1),
    {
      ...last,
      isStreaming: true,
    },
  ];
}

/**
 * Subscribe to a chat by ID. Returns the in-memory message list for the chat,
 * a streaming flag, and a ``send`` function. Initial history must be seeded
 * separately (e.g. via ``fetchSessionMessages``) since the server only replays
 * live events.
 */
/** Payload passed to ``send`` when the user attaches one or more images.
 *
 * ``media`` is handed to the wire client verbatim; ``preview`` powers the
 * optimistic user bubble (blob URLs so the preview appears before the server
 * acks the frame). Keeping the two separate lets the bubble re-use the local
 * blob URL even after the server persists the file under a different name. */
export interface SendImage {
  media: OutboundMedia;
  preview: UIImage;
}

export interface SendOptions {
  imageGeneration?: OutboundImageGeneration;
}

export function useNanobotStream(
  chatId: string | null,
  initialMessages: UIMessage[] = [],
  hasPendingToolCalls = false,
  onTurnEnd?: () => void,
): {
  messages: UIMessage[];
  isStreaming: boolean;
  send: (content: string, images?: SendImage[], options?: SendOptions) => void;
  stop: () => void;
  setMessages: React.Dispatch<React.SetStateAction<UIMessage[]>>;
  /** Latest transport-level fault raised since the last ``dismissStreamError``.
   * ``null`` when there is nothing to show. */
  streamError: StreamError | null;
  /** Clear the current ``streamError`` (e.g. after the user dismisses the
   * notification or starts a fresh action). */
  dismissStreamError: () => void;
} {
  const { client, setActiveTarget, setModelName } = useClient();
  const hydratedInitialMessages = hydrateInitialMessages(initialMessages, hasPendingToolCalls);
  const [messages, setMessages] = useState<UIMessage[]>(hydratedInitialMessages);
  /** If the last loaded message is a trace row (e.g. "Using 2 tools"),
   * the model was still processing when the page loaded — keep the
   * loading spinner alive so the user sees the model is active. */
  const initialStreaming = hydratedInitialMessages.length > 0
    ? hydratedInitialMessages[hydratedInitialMessages.length - 1].isStreaming === true
    : false;
  const [isStreaming, setIsStreaming] = useState(initialStreaming || hasPendingToolCalls);
  const [streamError, setStreamError] = useState<StreamError | null>(null);
  const buffer = useRef<StreamBuffer | null>(null);
  const suppressStreamUntilTurnEndRef = useRef(false);
  /** Timer that defers ``isStreaming = false`` after ``stream_end``.
   *
   * When the model finishes a text segment and calls a tool, the server
   * sends ``stream_end`` but the agent is still "thinking" while the tool
   * executes.  By deferring the flag reset by a short window (1 s) we keep
   * the loading spinner alive across tool-call boundaries without needing
   * backend changes. */
  const streamEndTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    return client.onError((err) => setStreamError(err));
  }, [client]);

  const dismissStreamError = useCallback(() => setStreamError(null), []);

  // Reset local state when switching chats. Do not reset on every
  // ``initialMessages`` update: a brand-new chat can receive an empty/404
  // history response after the optimistic first message has already rendered.
  useEffect(() => {
    const nextInitialMessages = hydrateInitialMessages(initialMessages, hasPendingToolCalls);
    setMessages(nextInitialMessages);
    setIsStreaming(
      (nextInitialMessages.length > 0
        ? nextInitialMessages[nextInitialMessages.length - 1].isStreaming === true
        : false) || hasPendingToolCalls,
    );
    setStreamError(null);
    buffer.current = null;
    suppressStreamUntilTurnEndRef.current = false;
    if (streamEndTimerRef.current !== null) {
      clearTimeout(streamEndTimerRef.current);
      streamEndTimerRef.current = null;
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [chatId]);

  useEffect(() => {
    if (hasPendingToolCalls) setIsStreaming(true);
  }, [hasPendingToolCalls]);

  useEffect(() => {
    if (hasPendingToolCalls) setIsStreaming(true);
    if (!chatId) return;

    const applyModelHint = (ev: {
      active_target?: string;
      response_model?: string;
    }) => {
      if (typeof ev.active_target === "string" && ev.active_target.trim()) {
        setActiveTarget(ev.active_target);
      }
      if (typeof ev.response_model === "string" && ev.response_model.trim()) {
        setModelName(ev.response_model);
      }
    };

    const handle = (ev: InboundEvent) => {
      // Any incoming event while the debounce timer is alive means the model
      // is still working (e.g. tool result arrived, more text to stream).
      // Cancel the pending "stream ended" timer so we don't hide the spinner.
      if (streamEndTimerRef.current !== null) {
        clearTimeout(streamEndTimerRef.current);
        streamEndTimerRef.current = null;
      }

      if (ev.event === "delta") {
        const id = buffer.current?.messageId ?? createUuid();
  if (suppressStreamUntilTurnEndRef.current) return;
        if (!buffer.current) {
          buffer.current = { messageId: id, parts: [] };
          setMessages((prev) => [
            ...prev,
            {
              id,
              role: "assistant",
              content: "",
              isStreaming: true,
              createdAt: Date.now(),
            },
          ]);
          setIsStreaming(true);
        }
        buffer.current.parts.push(ev.text);
        const combined = buffer.current.parts.join("");
        const targetId = buffer.current.messageId;
        setMessages((prev) =>
          prev.map((m) => (m.id === targetId ? { ...m, content: combined } : m)),
        );
        return;
      }

      if (ev.event === "stream_end") {
        applyModelHint(ev);
        if (suppressStreamUntilTurnEndRef.current) {
          buffer.current = null;
          return;
        }
        // stream_end only means the text segment finished — the model may
        // still be executing tools.  Do NOT reset isStreaming here; the
        // definitive "turn is complete" signal is ``turn_end``.
        if (!buffer.current) return;
        buffer.current = null;
        return;
      }

      if (ev.event === "turn_end") {
        // Definitive signal that the turn is fully complete.  Cancel any
        // pending debounce timer and stop the loading indicator immediately.
        if (streamEndTimerRef.current !== null) {
          clearTimeout(streamEndTimerRef.current);
          streamEndTimerRef.current = null;
        }
        setIsStreaming(false);
        setMessages((prev) =>
          prev.map((m) => (m.isStreaming ? { ...m, isStreaming: false } : m)),
        );
        suppressStreamUntilTurnEndRef.current = false;
        onTurnEnd?.();
        return;
      }

      if (ev.event === "session_updated") {
        onTurnEnd?.();
        return;
      }

      if (ev.event === "message") {
        if (ev.kind === "remote_user") {
          setMessages((prev) => [
            ...prev,
            {
              id: createUuid(),
              role: "user",
              content: ev.text,
              createdAt: Date.now(),
            },
          ]);
          return;
        }
        if (
          suppressStreamUntilTurnEndRef.current &&
          (ev.kind === "tool_hint" || ev.kind === "progress")
        ) {
          return;
        }
        // Intermediate agent breadcrumbs (tool-call hints, raw progress).
        // Attach them to the last trace row if it was the last emitted item
        // so a sequence of calls collapses into one compact trace group.
        if (ev.kind === "tool_hint" || ev.kind === "progress") {
          const line = ev.text;
          setMessages((prev) => {
            const last = prev[prev.length - 1];
            if (last && last.kind === "trace") {
              const merged: UIMessage = {
                ...last,
                traces: [...(last.traces ?? [last.content]), line],
                content: line,
                isStreaming: true,
              };
              return [...prev.slice(0, -1), merged];
            }
            const assistantStreamingIndex = findLastIndex(
              prev,
              (message) => message.role === "assistant" && Boolean(message.isStreaming),
            );
            if (assistantStreamingIndex >= 0) {
              const beforeAssistant = prev[assistantStreamingIndex - 1];
              if (beforeAssistant?.kind === "trace") {
                const merged: UIMessage = {
                  ...beforeAssistant,
                  traces: [...(beforeAssistant.traces ?? [beforeAssistant.content]), line],
                  content: line,
                  isStreaming: true,
                };
                return [
                  ...prev.slice(0, assistantStreamingIndex - 1),
                  merged,
                  ...prev.slice(assistantStreamingIndex),
                ];
              }
              return [
                ...prev.slice(0, assistantStreamingIndex),
                {
                  id: createUuid(),
                  role: "tool",
                  kind: "trace",
                  content: line,
                  traces: [line],
                  isStreaming: true,
                  createdAt: Date.now(),
                },
                ...prev.slice(assistantStreamingIndex),
              ];
            }
            return [
              ...prev,
              {
                id: createUuid(),
                role: "tool",
                kind: "trace",
                content: line,
                traces: [line],
                isStreaming: true,
                createdAt: Date.now(),
              },
            ];
          });
          return;
        }

        if (ev.kind === "tool_approval") {
          setMessages((prev) => [
            ...prev,
            {
              id: createUuid(),
              role: "assistant",
              kind: "approval",
              content: ev.text,
              ...(ev.render_as === "text" ? { renderAs: "text" as const } : {}),
              createdAt: Date.now(),
            },
          ]);
          return;
        }

        applyModelHint(ev);
        const media = ev.media_urls?.length
          ? ev.media_urls.map((m) => toMediaAttachment(m))
          : ev.media?.map((url) => toMediaAttachment({ url }));
        const hasMedia = !!media && media.length > 0;
        const content = ev.buttons?.length ? (ev.button_prompt ?? ev.text) : ev.text;

        // A complete (non-streamed) assistant message. If a stream was in
        // flight, drop the placeholder so we don't render the text twice.
        const activeId = buffer.current?.messageId;
        buffer.current = null;
        // Do NOT reset isStreaming here — only ``turn_end`` signals that
        // the full turn (all tool calls + final text) is complete.
        setMessages((prev) => {
          const filtered = activeId ? prev.filter((m) => m.id !== activeId) : prev;
          if (matchesRecentAssistantMessage(filtered, {
            content,
            renderAs: ev.render_as === "text" ? "text" : undefined,
            buttons: ev.buttons,
            media,
          })) {
            return filtered;
          }
          return [
            ...filtered,
            {
              id: createUuid(),
              role: "assistant",
              content,
              ...(ev.render_as === "text" ? { renderAs: "text" as const } : {}),
              createdAt: Date.now(),
              ...(ev.buttons && ev.buttons.length > 0 ? { buttons: ev.buttons } : {}),
              ...(hasMedia ? { media } : {}),
            },
          ];
        });
        if (hasMedia) {
          suppressStreamUntilTurnEndRef.current = true;
        }
        return;
      }
      // ``attached`` / ``error`` frames aren't actionable here; the client
      // shell handles them separately.
    };

    const unsub = client.onChat(chatId, handle);
    return () => {
      unsub();
      buffer.current = null;
      if (streamEndTimerRef.current !== null) {
        clearTimeout(streamEndTimerRef.current);
        streamEndTimerRef.current = null;
      }
    };
  }, [chatId, client, hasPendingToolCalls, onTurnEnd, setActiveTarget, setModelName]);

  const send = useCallback(
    (content: string, images?: SendImage[], options?: SendOptions) => {
      if (!chatId) return;
      const hasImages = !!images && images.length > 0;
      // Text is optional when images are attached — the agent will still see
      // the image blocks via ``media`` paths.
      if (!hasImages && !content.trim()) return;

      const previews = hasImages ? images!.map((i) => i.preview) : undefined;
      setMessages((prev) => [
        ...prev,
        {
          id: createUuid(),
          role: "user",
          content,
          createdAt: Date.now(),
          ...(previews ? { images: previews } : {}),
        },
      ]);
      // Mark streaming immediately so the UI shows the loading indicator
      // right away, before the first delta arrives from the server.
      setIsStreaming(true);
      const wireMedia = hasImages ? images!.map((i) => i.media) : undefined;
      if (options) {
        client.sendMessage(chatId, content, wireMedia, options);
      } else {
        client.sendMessage(chatId, content, wireMedia);
      }
    },
    [chatId, client],
  );

  const stop = useCallback(() => {
    if (!chatId) return;
    setIsStreaming(false);
    setMessages((prev) =>
      prev.map((m) => (m.isStreaming ? { ...m, isStreaming: false } : m)),
    );
    suppressStreamUntilTurnEndRef.current = false;
    client.sendMessage(chatId, "/stop");
  }, [chatId, client]);

  return {
    messages,
    isStreaming,
    send,
    stop,
    setMessages,
    streamError,
    dismissStreamError,
  };
}

function findLastIndex<T>(items: T[], predicate: (item: T) => boolean): number {
  for (let index = items.length - 1; index >= 0; index -= 1) {
    if (predicate(items[index])) return index;
  }
  return -1;
}

function matchesRecentAssistantMessage(
  messages: UIMessage[],
  incoming: {
    content: string;
    renderAs?: UIMessage["renderAs"];
    buttons?: UIMessage["buttons"];
    media?: UIMessage["media"];
  },
): boolean {
  for (let index = messages.length - 1; index >= 0; index -= 1) {
    const message = messages[index];
    if (message.kind === "trace") continue;
    if (message.role !== "assistant") return false;
    if (message.isStreaming) return false;
    if (Date.now() - message.createdAt > LIVE_DUPLICATE_WINDOW_MS) return false;
    return (
      message.renderAs === incoming.renderAs
      &&
      normalizeDuplicateText(message.content) === normalizeDuplicateText(incoming.content)
      && JSON.stringify(message.buttons ?? []) === JSON.stringify(incoming.buttons ?? [])
      && JSON.stringify(message.media ?? []) === JSON.stringify(incoming.media ?? [])
    );
  }
  return false;
}

function normalizeDuplicateText(value: string): string {
  return value.replace(/\s+/g, " ").trim();
}
