import { useCallback, useEffect, useRef, useState } from "react";
import { Check, CheckCircle2, ChevronRight, Copy, FileIcon, ImageIcon, LoaderCircle, PlaySquare } from "lucide-react";
import { ShieldAlert, X } from "lucide-react";
import { useTranslation } from "react-i18next";

import { ImageLightbox } from "@/components/ImageLightbox";
import { MarkdownText } from "@/components/MarkdownText";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import type { UIImage, ReasoningVisibility, UIMediaAttachment, UIMessage } from "@/lib/types";

interface MessageBubbleProps {
  message: UIMessage;
  reasoningVisibility?: ReasoningVisibility;
  onApprovalResponse?: (messageId: string, decision: "yes" | "no") => void | Promise<void>;
}

/**
 * Render a single message. Following agent-chat-ui: user turns are a rounded
 * "pill" right-aligned with a muted fill; assistant turns render as bare
 * markdown so prose/code read like a document rather than a chat bubble.
 * Each turn fades+slides in for a touch of motion polish.
 *
 * Trace rows (tool-call hints, progress breadcrumbs) render as a subdued
 * collapsible group so intermediate steps never masquerade as replies.
 */
export function MessageBubble({
  message,
  reasoningVisibility = "summary",
  onApprovalResponse,
}: MessageBubbleProps) {
  const { t } = useTranslation();
  const [copied, setCopied] = useState(false);
  const copyResetRef = useRef<number | null>(null);
  const baseAnim = "animate-in fade-in-0 slide-in-from-bottom-1 duration-300";

  useEffect(() => {
    return () => {
      if (copyResetRef.current !== null) {
        window.clearTimeout(copyResetRef.current);
      }
    };
  }, []);

  const onCopyAssistantReply = useCallback(() => {
    if (!navigator.clipboard) return;
    void navigator.clipboard.writeText(message.content).then(() => {
      setCopied(true);
      if (copyResetRef.current !== null) {
        window.clearTimeout(copyResetRef.current);
      }
      copyResetRef.current = window.setTimeout(() => {
        setCopied(false);
        copyResetRef.current = null;
      }, 1_500);
    });
  }, [message.content]);

  if (message.kind === "trace") {
    if (reasoningVisibility === "off") return null;
    return (
      <TraceGroup
        message={message}
        animClass={baseAnim}
        visibility={reasoningVisibility}
      />
    );
  }

  if (message.kind === "approval") {
    return (
      <ApprovalCard
        message={message}
        animClass={baseAnim}
        onApprovalResponse={onApprovalResponse}
      />
    );
  }

  if (message.role === "user") {
    const images = message.images ?? [];
    const media = message.media ?? [];
    const hasImages = images.length > 0;
    const hasMedia = media.length > 0;
    const hasText = message.content.trim().length > 0;
    return (
      <div
        className={cn(
          "group ml-auto flex max-w-[min(85%,36rem)] flex-col items-end gap-1.5",
          baseAnim,
        )}
      >
        {hasImages ? <UserImages images={images} align="right" /> : null}
        {!hasImages && hasMedia ? (
          <MessageMedia media={media} align="right" />
        ) : null}
        {hasText ? (
          <p
            className={cn(
              "ml-auto w-fit rounded-[18px] border border-border/60 bg-secondary/70 px-4 py-2",
              "text-left whitespace-pre-wrap break-words",
              "shadow-[0_10px_24px_-18px_rgba(0,0,0,0.55)]",
            )}
            style={{
              fontSize: "var(--chat-font-size)",
              lineHeight: "var(--chat-line-height)",
            }}
          >
            {message.content}
          </p>
        ) : null}
      </div>
    );
  }

  const empty = message.content.trim().length === 0;
  const blocks = splitAssistantBlocks(message.content);
  const media = message.media ?? [];
  const showAssistantActions = message.role === "assistant" && !message.isStreaming && !empty;
  return (
    <div
      className={cn("w-full", baseAnim)}
      style={{
        fontSize: "var(--chat-font-size)",
        lineHeight: "var(--chat-line-height, var(--cjk-line-height))",
      }}
    >
      {empty && message.isStreaming ? (
        <TypingDots />
      ) : (
        <>
          {blocks.length > 0 ? (
            <div className="flex flex-col gap-4">
              {blocks.map((block, index) =>
                block.kind === "status" ? (
                  <StatusFooterCard key={`status-${index}`} content={block.content} />
                ) : (
                  <MarkdownText key={`markdown-${index}`}>{block.content}</MarkdownText>
                ),
              )}
            </div>
          ) : (
            <MarkdownText>{message.content}</MarkdownText>
          )}
          {message.isStreaming && <StreamCursor />}
          {media.length > 0 ? <MessageMedia media={media} align="left" /> : null}
          {showAssistantActions ? (
            <div className="mt-2 flex items-center gap-1 text-muted-foreground">
              <button
                type="button"
                onClick={onCopyAssistantReply}
                aria-label={copied ? t("message.copiedReply") : t("message.copyReply")}
                title={copied ? t("message.copiedReply") : t("message.copyReply")}
                className={cn(
                  "inline-flex h-8 w-8 items-center justify-center rounded-full",
                  "transition-colors hover:bg-muted/55 hover:text-foreground",
                  "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
                )}
              >
                {copied ? (
                  <Check className="h-4 w-4" aria-hidden />
                ) : (
                  <Copy className="h-4 w-4" aria-hidden />
                )}
              </button>
            </div>
          ) : null}
        </>
      )}
    </div>
  );
}

function splitAssistantBlocks(content: string): Array<
  | { kind: "markdown"; content: string }
  | { kind: "status"; content: string }
> {
  const trimmed = content.trim();
  if (!trimmed) return [];
  return trimmed
    .split(/\n{2,}/)
    .map((part) => part.trim())
    .filter(Boolean)
    .map((part) => (
      part.startsWith("Status: ")
        ? { kind: "status" as const, content: part.slice("Status: ".length) }
        : { kind: "markdown" as const, content: part }
    ));
}

function StatusFooterCard({ content }: { content: string }) {
  const segments = content.split(" | ").map((segment) => segment.trim()).filter(Boolean);

  return (
    <div
      className={cn(
        "w-full overflow-x-auto rounded-xl border border-slate-300/45 bg-slate-50/70 px-3 py-2",
        "shadow-[0_10px_24px_-22px_rgba(15,23,42,0.45)] dark:border-slate-700/60 dark:bg-slate-950/20",
      )}
    >
      <div className="flex min-w-max items-center gap-2 whitespace-nowrap font-mono text-[11px] leading-4 text-slate-600 dark:text-slate-300">
        {segments.map((segment, index) => (
          <span key={segment} className="contents">
            {index > 0 ? (
              <span className="text-slate-400 dark:text-slate-500">|</span>
            ) : null}
            <span>{segment}</span>
          </span>
        ))}
      </div>
    </div>
  );
}

function ApprovalCard({
  message,
  animClass,
  onApprovalResponse,
}: {
  message: UIMessage;
  animClass: string;
  onApprovalResponse?: (messageId: string, decision: "yes" | "no") => void | Promise<void>;
}) {
  const { t } = useTranslation();
  const [submitting, setSubmitting] = useState(false);

  const respond = async (decision: "yes" | "no") => {
    if (!onApprovalResponse || submitting) return;
    setSubmitting(true);
    try {
      await onApprovalResponse(message.id, decision);
    } catch {
      setSubmitting(false);
    }
  };

  return (
    <div className={cn("w-full", animClass)}>
      <div
        className={cn(
          "max-w-[min(100%,38rem)] rounded-2xl border border-amber-300/40 bg-amber-50/80 px-4 py-3",
          "shadow-[0_10px_24px_-18px_rgba(120,53,15,0.45)] dark:border-amber-700/50 dark:bg-amber-950/20",
        )}
      >
        <div className="mb-2 flex items-center gap-2 text-sm font-medium text-amber-900 dark:text-amber-200">
          <ShieldAlert className="h-4 w-4" aria-hidden />
          <span>{t("message.approval.title")}</span>
        </div>
        <MarkdownText>{message.content}</MarkdownText>
        <div className="mt-3 flex flex-wrap gap-2">
          <Button
            type="button"
            size="sm"
            onClick={() => void respond("yes")}
            disabled={submitting || !onApprovalResponse}
            aria-label={t("message.approval.approve")}
          >
            <Check className="mr-1.5 h-4 w-4" aria-hidden />
            {t("message.approval.approve")}
          </Button>
          <Button
            type="button"
            size="sm"
            variant="outline"
            onClick={() => void respond("no")}
            disabled={submitting || !onApprovalResponse}
            aria-label={t("message.approval.block")}
          >
            <X className="mr-1.5 h-4 w-4" aria-hidden />
            {t("message.approval.block")}
          </Button>
        </div>
      </div>
    </div>
  );
}

function MessageMedia({
  media,
  align,
}: {
  media: UIMediaAttachment[];
  align: "left" | "right";
}) {
  if (media.length === 0) return null;
  const images = media
    .filter((item) => item.kind === "image")
    .map(({ url, name }) => ({ url, name }));
  const nonImages = media.filter((item) => item.kind !== "image");

  return (
    <div
      className={cn(
        "mt-2 flex flex-wrap gap-2",
        align === "right" ? "justify-end" : "justify-start",
      )}
    >
      {images.length > 0 ? (
        <UserImages images={images} align={align} size={align === "left" ? "large" : "compact"} />
      ) : null}
      {nonImages.map((item, i) => (
        <MediaCell key={`${item.url ?? item.name ?? item.kind}-${i}`} media={item} />
      ))}
    </div>
  );
}

function MediaCell({ media }: { media: UIMediaAttachment }) {
  const { t } = useTranslation();
  const hasUrl = typeof media.url === "string" && media.url.length > 0;

  if (media.kind === "video" && hasUrl) {
    return (
      <figure className="max-w-[min(100%,32rem)] overflow-hidden rounded-[14px] border border-border/60 bg-muted/40">
        <video
          src={media.url}
          controls
          preload="metadata"
          className="block max-h-[26rem] w-full bg-black"
          aria-label={media.name ? `${t("message.videoAttachment", { defaultValue: "Video attachment" })}: ${media.name}` : t("message.videoAttachment", { defaultValue: "Video attachment" })}
        />
        {media.name ? (
          <figcaption className="truncate px-3 py-1.5 text-[11.5px] text-muted-foreground">
            {media.name}
          </figcaption>
        ) : null}
      </figure>
    );
  }

  const label =
    media.kind === "video"
      ? t("message.videoAttachment", { defaultValue: "Video attachment" })
      : t("message.fileAttachment", { defaultValue: "File attachment" });
  const Icon = media.kind === "video" ? PlaySquare : FileIcon;

  return (
    <div
      className="flex max-w-[18rem] items-center gap-2 rounded-[14px] border border-border/60 bg-muted/40 px-3 py-2 text-xs text-muted-foreground"
      title={media.name ?? undefined}
      aria-label={label}
    >
      <Icon className="h-4 w-4 flex-none" aria-hidden />
      <span className="truncate">{media.name ?? label}</span>
    </div>
  );
}

/**
 * Right-aligned preview row for images attached to a user turn.
 *
 * Visual follows agent-chat-ui: a single wrapping row of fixed-size square
 * thumbnails that stay modest next to the text pill regardless of how many
 * images are attached.
 *
 * The URL is expected to be a self-contained ``data:`` URL (the Composer
 * hands the normalized base64 payload to the optimistic bubble so that the
 * preview survives React StrictMode double-mount — blob URLs would be
 * revoked by the Composer's cleanup before remount). Historical replays
 * have no URL (the backend strips data URLs before persisting), so we
 * render a labelled placeholder tile instead of a broken ``<img>``.
 */
function UserImages({
  images,
  align = "right",
  size = "compact",
}: {
  images: UIImage[];
  align?: "left" | "right";
  size?: "compact" | "large";
}) {
  const { t } = useTranslation();
  // Only real-URL images can open in the lightbox; historical-replay
  // placeholders (no URL) have nothing to zoom into.
  const viewable = images
    .map((img, i) => ({ img, i }))
    .filter(({ img }) => typeof img.url === "string" && img.url.length > 0);
  const viewableImages = viewable.map(({ img }) => img);
  const originalToViewable = new Map<number, number>(
    viewable.map(({ i }, v) => [i, v]),
  );

  const [lightboxIndex, setLightboxIndex] = useState<number | null>(null);

  return (
    <>
      <div
        className={cn(
          "flex flex-wrap items-end gap-2",
          size === "large" && "gap-3",
          align === "right" ? "ml-auto justify-end" : "mr-auto justify-start",
        )}
      >
        {images.map((img, i) => (
          <UserImageCell
            key={`${img.url ?? "placeholder"}-${i}`}
            image={img}
            size={size}
            placeholderLabel={t("message.imageAttachment")}
            openLabel={t("lightbox.open")}
            onOpen={
              originalToViewable.has(i)
                ? () => setLightboxIndex(originalToViewable.get(i)!)
                : undefined
            }
          />
        ))}
      </div>
      <ImageLightbox
        images={viewableImages}
        index={lightboxIndex}
        onIndexChange={setLightboxIndex}
        onOpenChange={(open) => {
          if (!open) setLightboxIndex(null);
        }}
      />
    </>
  );
}

function UserImageCell({
  image,
  size,
  placeholderLabel,
  openLabel,
  onOpen,
}: {
  image: UIImage;
  size: "compact" | "large";
  placeholderLabel: string;
  openLabel: string;
  onOpen?: () => void;
}) {
  const hasUrl = typeof image.url === "string" && image.url.length > 0;
  const tileClasses = cn(
    "relative overflow-hidden border border-border/60 bg-muted/40",
    size === "large"
      ? "h-56 w-[min(100%,22rem)] rounded-[18px] sm:h-72 sm:w-[26rem]"
      : "h-24 w-24 rounded-[14px]",
    "shadow-[0_6px_18px_-14px_rgba(0,0,0,0.45)]",
  );

  if (hasUrl && onOpen) {
    return (
      <button
        type="button"
        onClick={onOpen}
        aria-label={image.name ? `${openLabel}: ${image.name}` : openLabel}
        title={image.name ?? undefined}
        className={cn(
          tileClasses,
          "cursor-zoom-in transition-transform duration-150 motion-reduce:transition-none",
          "hover:scale-[1.02] hover:ring-2 hover:ring-primary/30",
          "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/50",
        )}
      >
        <img
          src={image.url}
          alt={image.name ?? ""}
          loading="lazy"
          decoding="async"
          draggable={false}
          className={cn("h-full w-full", size === "large" ? "object-contain" : "object-cover")}
        />
      </button>
    );
  }

  return (
    <div className={tileClasses} title={image.name ?? undefined}>
      <div
        className="flex h-full w-full flex-col items-center justify-center gap-1 px-2 text-[11px] text-muted-foreground"
        aria-label={placeholderLabel}
      >
        <ImageIcon className="h-4 w-4 flex-none" aria-hidden />
        <span className="line-clamp-2 text-center leading-tight">
          {image.name ?? placeholderLabel}
        </span>
      </div>
    </div>
  );
}

/** Blinking cursor appended at the end of streaming text. */
function StreamCursor() {
  const { t } = useTranslation();
  return (
    <span
      aria-label={t("message.streaming")}
      className={cn(
        "ml-0.5 inline-block h-[1em] w-[3px] translate-y-[2px] align-middle",
        "rounded-sm bg-foreground/70 animate-pulse",
      )}
    />
  );
}

/** Pre-token-arrival placeholder: three bouncing dots. */
function TypingDots() {
  const { t } = useTranslation();
  return (
    <span
      aria-label={t("message.assistantTyping")}
      className="inline-flex items-center gap-1 py-1"
    >
      <Dot delay="0ms" />
      <Dot delay="150ms" />
      <Dot delay="300ms" />
    </span>
  );
}

function Dot({ delay }: { delay: string }) {
  return (
    <span
      style={{ animationDelay: delay }}
      className={cn(
        "inline-block h-1.5 w-1.5 rounded-full bg-muted-foreground/60",
        "animate-bounce",
      )}
    />
  );
}

interface TraceGroupProps {
  message: UIMessage;
  animClass: string;
  visibility: Exclude<ReasoningVisibility, "off">;
}

/**
 * Neutral reasoning card for tool-call / progress breadcrumbs.
 * While the turn is active it stays expanded; once complete it folds down
 * to a compact summary that can be reopened on demand.
 */
function TraceGroup({ message, animClass, visibility }: TraceGroupProps) {
  if (message.traceVariant === "status") {
    return <StatusTraceLine message={message} animClass={animClass} />;
  }

  const { t } = useTranslation();
  const lines = message.traces ?? [message.content];
  const count = lines.length;
  const latestLine = lines[lines.length - 1] ?? message.content;
  const allowsExpansion = visibility === "summary" || visibility === "debug_trace";
  const visibleLines = visibility === "debug_trace" ? lines : lines.slice(-3);
  const [open, setOpen] = useState(Boolean(message.isStreaming) && allowsExpansion);

  useEffect(() => {
    if (!allowsExpansion) {
      setOpen(false);
      return;
    }
    setOpen(Boolean(message.isStreaming));
  }, [allowsExpansion, message.isStreaming]);

  return (
    <div className={cn("w-full", animClass)}>
      <div
        className={cn(
          "overflow-hidden rounded-[18px] border border-slate-300/55 bg-slate-50/90",
          "shadow-[0_10px_24px_-22px_rgba(15,23,42,0.35)]",
          "dark:border-slate-700/60 dark:bg-slate-950/30",
        )}
      >
        {allowsExpansion ? (
          <button
            type="button"
            onClick={() => setOpen((v) => !v)}
            className={cn(
              "flex w-full items-start gap-3 px-3 py-2.5 text-left",
              "transition-colors hover:bg-slate-100/80 dark:hover:bg-slate-900/40",
            )}
            aria-expanded={open}
          >
            <div
              className={cn(
                "mt-0.5 rounded-full p-1.5",
                "bg-slate-200/80 text-slate-600 dark:bg-slate-800/80 dark:text-slate-300",
              )}
            >
              {message.isStreaming ? (
                <LoaderCircle className="h-4 w-4 animate-spin" aria-hidden />
              ) : (
                <CheckCircle2 className="h-4 w-4" aria-hidden />
              )}
            </div>
            <div className="min-w-0 flex-1">
              <div className="mb-1 flex flex-wrap items-center gap-2">
                <span className="text-[11px] font-semibold uppercase tracking-[0.08em] text-slate-500 dark:text-slate-400">
                  {message.isStreaming
                    ? t("message.reasoningWorking", { defaultValue: "Working" })
                    : t("message.reasoningDone", { defaultValue: "Summary" })}
                </span>
                <span className="text-sm font-medium leading-5 text-slate-800 dark:text-slate-100">
                  {count === 1
                    ? t("message.toolSingle")
                    : t("message.toolMany", { count })}
                </span>
              </div>
              <p className="line-clamp-2 whitespace-pre-wrap break-words text-[12px] leading-5 text-slate-600 dark:text-slate-300">
                {latestLine}
              </p>
            </div>
            <ChevronRight
              aria-hidden
              className={cn(
                "mt-1 h-4 w-4 shrink-0 text-slate-500 transition-transform duration-200 dark:text-slate-400",
                open && "rotate-90",
              )}
            />
          </button>
        ) : (
          <div className="flex w-full items-start gap-3 px-3 py-2.5 text-left">
            <div
              className={cn(
                "mt-0.5 rounded-full p-1.5",
                "bg-slate-200/80 text-slate-600 dark:bg-slate-800/80 dark:text-slate-300",
              )}
            >
              {message.isStreaming ? (
                <LoaderCircle className="h-4 w-4 animate-spin" aria-hidden />
              ) : (
                <CheckCircle2 className="h-4 w-4" aria-hidden />
              )}
            </div>
            <div className="min-w-0 flex-1">
              <div className="mb-1 flex flex-wrap items-center gap-2">
                <span className="text-[11px] font-semibold uppercase tracking-[0.08em] text-slate-500 dark:text-slate-400">
                  {message.isStreaming
                    ? t("message.reasoningWorking", { defaultValue: "Working" })
                    : t("message.reasoningDone", { defaultValue: "Summary" })}
                </span>
                <span className="text-sm font-medium leading-5 text-slate-800 dark:text-slate-100">
                  {count === 1
                    ? t("message.toolSingle")
                    : t("message.toolMany", { count })}
                </span>
              </div>
              <p className="line-clamp-2 whitespace-pre-wrap break-words text-[12px] leading-5 text-slate-600 dark:text-slate-300">
                {latestLine}
              </p>
            </div>
          </div>
        )}
        {allowsExpansion && open ? (
          <div className="border-t border-slate-200/80 px-3 pb-3 pt-2 dark:border-slate-800/80">
            <ul
              className={cn(
                "space-y-1.5 border-l border-slate-300/70 pl-3",
                "animate-in fade-in-0 slide-in-from-top-1 duration-200",
                "dark:border-slate-700/70",
              )}
            >
              {visibleLines.map((line, i) => (
                <li
                  key={i}
                  className="whitespace-pre-wrap break-words font-mono leading-relaxed text-slate-600 dark:text-slate-300"
                  style={{ fontSize: "calc(var(--chat-font-size) * 0.78)" }}
                >
                  {line}
                </li>
              ))}
            </ul>
          </div>
        ) : null}
      </div>
    </div>
  );
}

function StatusTraceLine({
  message,
  animClass,
}: {
  message: UIMessage;
  animClass: string;
}) {
  const { t } = useTranslation();

  return (
    <div className={cn("w-full", animClass)}>
      <div
        className={cn(
          "flex items-center gap-2 rounded-[12px] border border-slate-200/80 bg-slate-50/70 px-3 py-2",
          "text-[12px] leading-5 text-slate-600 shadow-[0_8px_20px_-20px_rgba(15,23,42,0.4)]",
          "dark:border-slate-800/80 dark:bg-slate-950/25 dark:text-slate-300",
        )}
      >
        <span className="shrink-0 rounded-full bg-slate-200/80 p-1 text-slate-600 dark:bg-slate-800/80 dark:text-slate-300">
          {message.isStreaming ? (
            <LoaderCircle className="h-3.5 w-3.5 animate-spin" aria-hidden />
          ) : (
            <CheckCircle2 className="h-3.5 w-3.5" aria-hidden />
          )}
        </span>
        <span className="shrink-0 text-[11px] font-semibold uppercase tracking-[0.08em] text-slate-500 dark:text-slate-400">
          {message.isStreaming
            ? t("message.reasoningWorking", { defaultValue: "Thinking" })
            : t("message.reasoningDone", { defaultValue: "Thought" })}
        </span>
        <p className="min-w-0 truncate whitespace-pre-wrap break-words text-[12px] leading-5 text-slate-600 dark:text-slate-300">
          {message.content}
        </p>
      </div>
    </div>
  );
}
