import { type ReactNode, useCallback, useEffect, useRef, useState } from "react";
import { ArrowDown } from "lucide-react";
import { useTranslation } from "react-i18next";

import { ThreadMessages } from "@/components/thread/ThreadMessages";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import type { UIMessage } from "@/lib/types";

interface ThreadViewportProps {
  messages: UIMessage[];
  isStreaming: boolean;
  composer: ReactNode;
  emptyState?: ReactNode;
  onApprovalResponse?: (messageId: string, decision: "yes" | "no") => void | Promise<void>;
}

const NEAR_BOTTOM_PX = 48;

export function ThreadViewport({
  messages,
  isStreaming,
  composer,
  emptyState,
  onApprovalResponse,
}: ThreadViewportProps) {
  const { t } = useTranslation();
  const scrollRef = useRef<HTMLDivElement>(null);
  const contentRef = useRef<HTMLDivElement>(null);
  const composerWrapRef = useRef<HTMLDivElement>(null);
  const [atBottom, setAtBottom] = useState(true);
  const [composerHeight, setComposerHeight] = useState(112);
  const initialBottomPinnedRef = useRef(false);
  const atBottomRef = useRef(true);
  const hasMessages = messages.length > 0;

  const scrollToBottom = useCallback((smooth = false) => {
    const el = scrollRef.current;
    if (!el) return;
    el.scrollTo({
      top: el.scrollHeight,
      behavior: smooth ? "smooth" : "auto",
    });
  }, []);

  useEffect(() => {
    atBottomRef.current = atBottom;
  }, [atBottom]);

  useEffect(() => {
    if (!atBottom) return;
    scrollToBottom(!isStreaming);
  }, [messages, isStreaming, atBottom, scrollToBottom]);

  useEffect(() => {
    if (messages.length === 0) {
      initialBottomPinnedRef.current = false;
      return;
    }
    if (initialBottomPinnedRef.current) return;
    initialBottomPinnedRef.current = true;
    setAtBottom(true);
    scrollToBottom(false);
  }, [messages.length, scrollToBottom]);

  useEffect(() => {
    const scrollEl = scrollRef.current;
    const contentEl = contentRef.current;
    if (!scrollEl || !contentEl || !hasMessages) return;

    const keepPinned = () => {
      if (!initialBottomPinnedRef.current && !atBottomRef.current) return;
      scrollToBottom(false);
      requestAnimationFrame(() => {
        const distance = scrollEl.scrollHeight - scrollEl.scrollTop - scrollEl.clientHeight;
        const pinned = distance < NEAR_BOTTOM_PX;
        setAtBottom(pinned);
        if (pinned) {
          initialBottomPinnedRef.current = false;
        }
      });
    };

    const observer = new ResizeObserver(() => {
      keepPinned();
    });
    observer.observe(contentEl);
    keepPinned();
    return () => observer.disconnect();
  }, [hasMessages, scrollToBottom]);

  useEffect(() => {
    const el = scrollRef.current;
    if (!el) return;

    const onScroll = () => {
      const distance = el.scrollHeight - el.scrollTop - el.clientHeight;
      setAtBottom(distance < NEAR_BOTTOM_PX);
    };

    onScroll();
    el.addEventListener("scroll", onScroll, { passive: true });
    return () => el.removeEventListener("scroll", onScroll);
  }, []);

  useEffect(() => {
    const el = composerWrapRef.current;
    if (!el) return;
    const update = () => {
      const next = Math.max(72, Math.ceil(el.getBoundingClientRect().height));
      setComposerHeight(next);
    };
    update();
    const observer = new ResizeObserver(update);
    observer.observe(el);
    return () => observer.disconnect();
  }, [composer]);

  return (
    <div className="relative flex min-h-0 flex-1 overflow-hidden">
      <div
        ref={scrollRef}
        className={cn(
          "absolute inset-0 overflow-y-auto scroll-smooth scrollbar-thin",
          "[&::-webkit-scrollbar]:w-1.5",
          "[&::-webkit-scrollbar-thumb]:rounded-full",
          "[&::-webkit-scrollbar-thumb]:bg-muted-foreground/30",
          "[&::-webkit-scrollbar-track]:bg-transparent",
        )}
      >
        {hasMessages ? (
          <div ref={contentRef} className="mx-auto flex min-h-full w-full max-w-[64rem] flex-col">
            <div className="flex-1 px-4 pt-4" style={{ paddingBottom: composerHeight + 12 }}>
              <ThreadMessages messages={messages} onApprovalResponse={onApprovalResponse} />
            </div>

            <div ref={composerWrapRef} className="sticky bottom-0 z-10 mt-auto bg-background/95 backdrop-blur-sm">
              <div className="px-4 pb-3">
                {composer}
              </div>
            </div>
          </div>
        ) : (
          <div className="mx-auto flex min-h-full w-full max-w-[64rem] flex-col px-4">
            <div className="flex w-full flex-1 justify-center pb-16 pt-14 md:pt-[3.5rem]">
              <div className="flex w-full max-w-[40rem] flex-col gap-5">
                {emptyState}
                <div className="w-full">{composer}</div>
              </div>
            </div>
          </div>
        )}
      </div>

      <div
        aria-hidden
        className="pointer-events-none absolute inset-x-0 top-0 h-6 bg-gradient-to-b from-background to-transparent"
      />

      {!atBottom && (
        <Button
          variant="outline"
          size="icon"
          onClick={() => scrollToBottom(true)}
          className={cn(
            "absolute bottom-28 left-1/2 h-8 w-8 -translate-x-1/2 rounded-full shadow-md",
            "bg-background/90 backdrop-blur",
            "animate-in fade-in-0 zoom-in-95",
          )}
          aria-label={t("thread.scrollToBottom")}
        >
          <ArrowDown className="h-4 w-4" />
        </Button>
      )}
    </div>
  );
}
