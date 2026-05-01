import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type KeyboardEvent as ReactKeyboardEvent,
} from "react";
import {
  ArrowUp,
  ChevronDown,
  ImageIcon,
  Loader2,
  Paperclip,
  X,
} from "lucide-react";
import { useTranslation } from "react-i18next";

import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuLabel,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import {
  useAttachedImages,
  type AttachedImage,
  type AttachmentError,
  MAX_IMAGES_PER_MESSAGE,
} from "@/hooks/useAttachedImages";
import { useClipboardAndDrop } from "@/hooks/useClipboardAndDrop";
import type { SendImage } from "@/hooks/useNanobotStream";
import type { ModelTargetOption } from "@/lib/types";
import { cn } from "@/lib/utils";

/** ``<input accept>``: aligned with the server's MIME whitelist. SVG is
 * deliberately excluded to avoid an embedded-script XSS surface. */
const ACCEPT_ATTR = "image/png,image/jpeg,image/webp,image/gif";

function formatBytes(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / (1024 * 1024)).toFixed(1)} MB`;
}

function resizeTextarea(el: HTMLTextAreaElement | null) {
  if (!el) return;
  el.style.height = "auto";
  el.style.height = `${Math.min(el.scrollHeight, 260)}px`;
}

function describeModelTarget(target: ModelTargetOption): string | null {
  if (target.kind === "smart_router") {
    return target.smart_router_mode === "auto"
      ? "smart-router"
      : `smart-router -> ${target.smart_router_mode ?? "auto"}`;
  }
  const model = typeof target.model === "string" ? target.model.trim() : "";
  const provider = typeof target.provider === "string" ? target.provider.trim() : "";
  if (provider && model) return `${provider} -> ${model}`;
  if (model) return model;
  if (provider) return provider;
  return null;
}

function displayModelTargetName(target: ModelTargetOption): string {
  const label = typeof target.display_name === "string" ? target.display_name.trim() : "";
  return label || target.name;
}

function orderModelTargets(targets: ModelTargetOption[]): ModelTargetOption[] {
  const rank: Record<string, number> = {
    auto: 0,
    local: 1,
    mini: 2,
    full: 3,
  };
  return [...targets].sort((left, right) => {
    const leftGroup = left.group === "smart-router" ? 0 : 1;
    const rightGroup = right.group === "smart-router" ? 0 : 1;
    if (leftGroup !== rightGroup) return leftGroup - rightGroup;
    if (left.group === "smart-router" && right.group === "smart-router") {
      return (rank[left.smart_router_mode ?? "full"] ?? 99) - (rank[right.smart_router_mode ?? "full"] ?? 99);
    }
    return displayModelTargetName(left).localeCompare(displayModelTargetName(right));
  });
}

interface ThreadComposerProps {
  onSend: (content: string, images?: SendImage[]) => void;
  disabled?: boolean;
  placeholder?: string;
  injectedDraft?: string | null;
  injectedDraftNonce?: number;
  modelLabel?: string | null;
  activeTarget?: string | null;
  modelTargets?: ModelTargetOption[];
  modelTargetPending?: boolean;
  onSelectModelTarget?: (targetName: string) => void | Promise<void>;
  variant?: "thread" | "hero";
}

export function ThreadComposer({
  onSend,
  disabled,
  placeholder,
  injectedDraft = null,
  injectedDraftNonce = 0,
  modelLabel = null,
  activeTarget = null,
  modelTargets = [],
  modelTargetPending = false,
  onSelectModelTarget,
  variant = "thread",
}: ThreadComposerProps) {
  const { t } = useTranslation();
  const [value, setValue] = useState("");
  const [inlineError, setInlineError] = useState<string | null>(null);
  const [historyIndex, setHistoryIndex] = useState<number | null>(null);
  const [sentHistory, setSentHistory] = useState<string[]>([]);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const chipRefs = useRef(new Map<string, HTMLButtonElement>());
  const draftBeforeHistoryRef = useRef("");
  const isHero = variant === "hero";
  const resolvedPlaceholder =
    placeholder ?? t("thread.composer.placeholderThread");

  const { images, enqueue, remove, clear, encoding, full } =
    useAttachedImages();

  const formatRejection = useCallback(
    (reason: AttachmentError): string => {
      const key = `thread.composer.imageRejected.${reason}`;
      return t(key, { max: MAX_IMAGES_PER_MESSAGE });
    },
    [t],
  );

  const addFiles = useCallback(
    (files: File[]) => {
      if (files.length === 0) return;
      const { rejected } = enqueue(files);
      if (rejected.length > 0) {
        setInlineError(formatRejection(rejected[0].reason));
      } else {
        setInlineError(null);
      }
    },
    [enqueue, formatRejection],
  );

  const {
    isDragging,
    onPaste,
    onDragEnter,
    onDragOver,
    onDragLeave,
    onDrop,
  } = useClipboardAndDrop(addFiles);

  useEffect(() => {
    if (disabled) return;
    const el = textareaRef.current;
    if (!el) return;
    const id = requestAnimationFrame(() => el.focus());
    return () => cancelAnimationFrame(id);
  }, [disabled]);

  useEffect(() => {
    if (!injectedDraftNonce || typeof injectedDraft !== "string") return;
    setHistoryIndex(null);
    draftBeforeHistoryRef.current = injectedDraft;
    setValue(injectedDraft);
    requestAnimationFrame(() => {
      const el = textareaRef.current;
      if (!el) return;
      resizeTextarea(el);
      const pos = injectedDraft.length;
      el.focus();
      el.setSelectionRange(pos, pos);
    });
  }, [injectedDraft, injectedDraftNonce]);

  const readyImages = useMemo(
    () => images.filter((img): img is AttachedImage & { dataUrl: string } =>
      img.status === "ready" && typeof img.dataUrl === "string",
    ),
    [images],
  );
  const hasErrors = images.some((img) => img.status === "error");

  const canSend =
    !disabled
    && !encoding
    && !hasErrors
    && (value.trim().length > 0 || readyImages.length > 0);
  const canSelectModelTarget = !disabled && !modelTargetPending && modelTargets.length > 0 && !!onSelectModelTarget;
  const orderedTargets = useMemo(() => orderModelTargets(modelTargets), [modelTargets]);

  const submit = useCallback(() => {
    if (!canSend) return;
    const trimmed = value.trim();
    // Share the same normalized ``data:`` URL with both the wire payload and
    // the optimistic bubble preview: data URLs are self-contained (no blob
    // lifetime, safe under React StrictMode double-mount) and keep the
    // bubble in sync with whatever the backend actually sees.
    const payload: SendImage[] | undefined =
      readyImages.length > 0
        ? readyImages.map((img) => ({
            media: {
              data_url: img.dataUrl,
              name: img.file.name,
            },
            preview: { url: img.dataUrl, name: img.file.name },
          }))
        : undefined;
    onSend(trimmed, payload);
    if (trimmed) {
      setSentHistory((prev) => (
        prev.length > 0 && prev[prev.length - 1] === trimmed
          ? prev
          : [...prev, trimmed]
      ));
    }
    setHistoryIndex(null);
    draftBeforeHistoryRef.current = "";
    setValue("");
    setInlineError(null);
    // Bubble owns the data URL copy; safe to revoke every staged blob
    // preview here without affecting the rendered message.
    clear();
    requestAnimationFrame(() => {
      const el = textareaRef.current;
      if (el) {
        resizeTextarea(el);
        el.focus();
      }
    });
  }, [canSend, clear, onSend, readyImages, value]);

  const applyHistoryValue = useCallback((nextValue: string) => {
    setValue(nextValue);
    requestAnimationFrame(() => {
      const el = textareaRef.current;
      if (!el) return;
      resizeTextarea(el);
      const pos = nextValue.length;
      el.focus();
      el.setSelectionRange(pos, pos);
    });
  }, []);

  const onKeyDown = (e: ReactKeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
      e.preventDefault();
      submit();
      return;
    }

    const el = textareaRef.current;
    const singleCursor = !!el && el.selectionStart === el.selectionEnd;
    const atStart = !!el && singleCursor && el.selectionStart === 0;
    const atEnd = !!el && singleCursor && el.selectionStart === el.value.length;

    if (
      e.key === "ArrowUp"
      && !e.shiftKey
      && !e.altKey
      && !e.metaKey
      && !e.ctrlKey
      && (atStart || historyIndex !== null)
      && sentHistory.length > 0
    ) {
      e.preventDefault();
      if (historyIndex === null) {
        draftBeforeHistoryRef.current = value;
        const nextIndex = sentHistory.length - 1;
        setHistoryIndex(nextIndex);
        applyHistoryValue(sentHistory[nextIndex]);
        return;
      }
      const nextIndex = Math.max(0, historyIndex - 1);
      setHistoryIndex(nextIndex);
      applyHistoryValue(sentHistory[nextIndex]);
      return;
    }

    if (
      e.key === "ArrowDown"
      && !e.shiftKey
      && !e.altKey
      && !e.metaKey
      && !e.ctrlKey
      && historyIndex !== null
      && (atEnd || historyIndex !== null)
    ) {
      e.preventDefault();
      const nextIndex = historyIndex + 1;
      if (nextIndex >= sentHistory.length) {
        setHistoryIndex(null);
        applyHistoryValue(draftBeforeHistoryRef.current);
        return;
      }
      setHistoryIndex(nextIndex);
      applyHistoryValue(sentHistory[nextIndex]);
    }
  };

  const onInput: React.FormEventHandler<HTMLTextAreaElement> = (e) => {
    resizeTextarea(e.currentTarget);
  };

  const onFilePick: React.ChangeEventHandler<HTMLInputElement> = (e) => {
    const files = Array.from(e.target.files ?? []);
    e.target.value = "";
    addFiles(files);
  };

  const removeChip = useCallback(
    (id: string) => {
      const { nextFocusId } = remove(id);
      setInlineError(null);
      requestAnimationFrame(() => {
        const el = nextFocusId ? chipRefs.current.get(nextFocusId) : null;
        if (el) {
          el.focus();
        } else {
          textareaRef.current?.focus();
        }
      });
    },
    [remove],
  );

  const onChipKey = useCallback(
    (id: string) => (e: ReactKeyboardEvent<HTMLButtonElement>) => {
      if (
        e.key === "Delete" ||
        e.key === "Backspace" ||
        e.key === "Enter" ||
        e.key === " "
      ) {
        e.preventDefault();
        removeChip(id);
      }
    },
    [removeChip],
  );

  const attachButtonDisabled = disabled || full;

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        submit();
      }}
      onDragEnter={onDragEnter}
      onDragOver={onDragOver}
      onDragLeave={onDragLeave}
      onDrop={onDrop}
      className={cn("w-full", isHero ? "px-0" : "px-1 pb-1.5 pt-1 sm:px-0")}
    >
      <div
        className={cn(
          "relative mx-auto flex w-full flex-col overflow-hidden transition-all duration-200",
          isHero
            ? "max-w-[40rem] rounded-[24px] border border-border/75 bg-card shadow-[0_10px_30px_rgba(0,0,0,0.10)]"
            : "max-w-[49.5rem] rounded-[16px] border border-border/70 bg-card",
          "focus-within:ring-1 focus-within:ring-foreground/8",
          disabled && "opacity-60",
          isDragging && "ring-2 ring-primary/40 motion-reduce:ring-0 motion-reduce:border-primary",
        )}
      >
        {images.length > 0 ? (
          <div
            className="flex flex-wrap gap-2 px-3 pt-3"
            aria-label={t("thread.composer.attachImage")}
          >
            {images.map((img) => (
              <AttachmentChip
                key={img.id}
                image={img}
                labelRemove={t("thread.composer.remove")}
                labelEncoding={t("thread.composer.encoding")}
                normalizedHint={(orig, current) =>
                  t("thread.composer.normalizedSizeHint", {
                    orig: formatBytes(orig),
                    current: formatBytes(current),
                  })
                }
                formatError={formatRejection}
                onRemove={() => removeChip(img.id)}
                onKeyDown={onChipKey(img.id)}
                registerRef={(el) => {
                  if (el) chipRefs.current.set(img.id, el);
                  else chipRefs.current.delete(img.id);
                }}
              />
            ))}
          </div>
        ) : null}
        <textarea
          ref={textareaRef}
          value={value}
          onChange={(e) => {
            if (historyIndex !== null) {
              setHistoryIndex(null);
              draftBeforeHistoryRef.current = e.target.value;
            }
            setValue(e.target.value);
          }}
          onInput={onInput}
          onKeyDown={onKeyDown}
          onPaste={onPaste}
          rows={1}
          placeholder={resolvedPlaceholder}
          disabled={disabled}
          aria-label={t("thread.composer.inputAria")}
          className={cn(
            "w-full resize-none bg-transparent",
            isHero
              ? "min-h-[96px] px-4 pb-2 pt-4"
              : "min-h-[50px] px-4 pb-1.5 pt-3",
            "placeholder:text-muted-foreground",
            "focus:outline-none focus-visible:outline-none",
            "disabled:cursor-not-allowed",
          )}
          style={{
            fontSize: "var(--chat-font-size)",
            lineHeight: "var(--chat-line-height)",
          }}
        />
        {inlineError ? (
          <div
            role="alert"
            className={cn(
              "mx-3 mb-1 rounded-md border border-destructive/40 bg-destructive/8 px-2.5 py-1",
              "text-[11.5px] font-medium text-destructive",
            )}
          >
            {inlineError}
          </div>
        ) : null}
        <div
          className={cn(
            "flex items-center justify-between gap-2",
            isHero ? "px-3.5 pb-3.5" : "px-3 pb-2",
          )}
        >
          <div className="flex min-w-0 items-center gap-2">
            <input
              ref={fileInputRef}
              type="file"
              accept={ACCEPT_ATTR}
              multiple
              hidden
              onChange={onFilePick}
            />
            <Button
              type="button"
              size="icon"
              variant="ghost"
              disabled={attachButtonDisabled}
              aria-label={t("thread.composer.attachImage")}
              onClick={() => fileInputRef.current?.click()}
              className={cn(
                "rounded-full text-muted-foreground hover:text-foreground",
                isHero ? "h-8.5 w-8.5" : "h-7.5 w-7.5",
              )}
            >
              <Paperclip className={cn(isHero ? "h-4 w-4" : "h-3.5 w-3.5")} />
            </Button>
            {modelLabel ? (
              canSelectModelTarget ? (
                <DropdownMenu modal={false}>
                  <DropdownMenuTrigger asChild>
                    <button
                      type="button"
                      title={modelLabel}
                      aria-label={t("thread.composer.modelMenuAria")}
                      className={cn(
                        "inline-flex min-w-0 items-center gap-1.5 rounded-full border px-2.5 py-1",
                        "border-foreground/10 bg-foreground/[0.035] font-medium text-foreground/80 transition-colors hover:bg-foreground/[0.07]",
                        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2",
                        isHero ? "text-[11px]" : "text-[10.5px]",
                      )}
                      disabled={!canSelectModelTarget}
                    >
                      <span
                        aria-hidden
                        className="h-1.5 w-1.5 flex-none rounded-full bg-emerald-500/80"
                      />
                      <span className="truncate">{modelLabel}</span>
                      {modelTargetPending ? (
                        <Loader2 className="h-3 w-3 flex-none animate-spin" aria-hidden />
                      ) : (
                        <ChevronDown className="h-3 w-3 flex-none" aria-hidden />
                      )}
                    </button>
                  </DropdownMenuTrigger>
                  <DropdownMenuContent align="start" className="w-[20rem]">
                    <DropdownMenuLabel>{t("thread.composer.modelMenuLabel")}</DropdownMenuLabel>
                    <DropdownMenuSeparator />
                    <DropdownMenuRadioGroup
                      value={activeTarget ?? ""}
                      onValueChange={(value) => {
                        if (!value || value === activeTarget || !onSelectModelTarget) return;
                        void onSelectModelTarget(value);
                      }}
                    >
                      {orderedTargets.map((target) => (
                        <DropdownMenuRadioItem key={target.name} value={target.name}>
                          <span className="flex min-w-0 flex-col gap-0.5">
                            <span className="truncate font-medium">{displayModelTargetName(target)}</span>
                            {describeModelTarget(target) ? (
                              <span className="max-w-[15rem] whitespace-normal text-[11px] text-muted-foreground">
                                {describeModelTarget(target)}
                              </span>
                            ) : null}
                            {target.description ? (
                              <span className="max-w-[15rem] whitespace-normal text-xs text-muted-foreground">
                                {target.description}
                              </span>
                            ) : null}
                          </span>
                        </DropdownMenuRadioItem>
                      ))}
                    </DropdownMenuRadioGroup>
                  </DropdownMenuContent>
                </DropdownMenu>
              ) : (
                <span
                  title={modelLabel}
                  className={cn(
                    "inline-flex min-w-0 items-center gap-1.5 rounded-full border px-2.5 py-1",
                    "border-foreground/10 bg-foreground/[0.035] font-medium text-foreground/80",
                    isHero ? "text-[11px]" : "text-[10.5px]",
                  )}
                >
                  <span
                    aria-hidden
                    className="h-1.5 w-1.5 flex-none rounded-full bg-emerald-500/80"
                  />
                  <span className="truncate">{modelLabel}</span>
                </span>
              )
            ) : null}
            <span className="hidden select-none text-[10.5px] text-muted-foreground/60 sm:inline">
              {t("thread.composer.sendHint")}
            </span>
          </div>
          <span className="sm:hidden" aria-hidden />
          <Button
            type="submit"
            size="icon"
            disabled={!canSend}
            aria-label={t("thread.composer.send")}
            className={cn(
              "rounded-full border border-border/70 bg-secondary/85 text-secondary-foreground shadow-none transition-transform hover:bg-accent",
              isHero ? "h-8.5 w-8.5" : "h-7.5 w-7.5",
              canSend && "hover:scale-[1.03] active:scale-95",
            )}
          >
            <ArrowUp className={cn(isHero ? "h-4.5 w-4.5" : "h-4 w-4")} />
          </Button>
        </div>
      </div>
    </form>
  );
}

interface AttachmentChipProps {
  image: AttachedImage;
  labelRemove: string;
  labelEncoding: string;
  normalizedHint: (origBytes: number, currentBytes: number) => string;
  formatError: (reason: AttachmentError) => string;
  onRemove: () => void;
  onKeyDown: (e: ReactKeyboardEvent<HTMLButtonElement>) => void;
  registerRef: (el: HTMLButtonElement | null) => void;
}

function AttachmentChip({
  image,
  labelRemove,
  labelEncoding,
  normalizedHint,
  formatError,
  onRemove,
  onKeyDown,
  registerRef,
}: AttachmentChipProps) {
  const sizeLabel =
    image.status === "ready" && image.normalized && image.encodedBytes
      ? normalizedHint(image.file.size, image.encodedBytes)
      : formatBytes(image.file.size);
  const tone =
    image.status === "error"
      ? "border-destructive/40 bg-destructive/5 text-destructive"
      : "border-border/70 bg-muted/60";

  return (
    <div
      className={cn(
        "group relative flex items-center gap-2 rounded-[12px] border px-2 py-1.5",
        "transition-colors motion-reduce:transition-none",
        tone,
      )}
      data-testid="composer-chip"
    >
      <div className="relative h-10 w-10 overflow-hidden rounded-md bg-background">
        {image.previewUrl ? (
          <img
            src={image.previewUrl}
            alt=""
            aria-hidden
            loading="eager"
            draggable={false}
            className="h-full w-full object-cover"
          />
        ) : (
          <div className="flex h-full w-full items-center justify-center">
            <ImageIcon className="h-4 w-4 text-muted-foreground" aria-hidden />
          </div>
        )}
        {image.status === "encoding" ? (
          <div
            className="absolute inset-0 flex items-center justify-center bg-background/60"
            aria-label={labelEncoding}
          >
            <Loader2 className="h-4 w-4 animate-spin motion-reduce:animate-none" aria-hidden />
          </div>
        ) : null}
      </div>
      <div className="flex min-w-0 flex-col text-[11.5px] leading-4">
        <span className="truncate max-w-[14rem] font-medium" title={image.file.name}>
          {image.file.name}
        </span>
        <span className="truncate text-muted-foreground">
          {image.status === "error" && image.error
            ? formatError(image.error)
            : sizeLabel}
        </span>
      </div>
      <button
        type="button"
        ref={registerRef}
        onClick={onRemove}
        onKeyDown={onKeyDown}
        aria-label={labelRemove}
        className={cn(
          "ml-1 grid h-5 w-5 flex-none place-items-center rounded-full",
          "text-muted-foreground/80 hover:bg-foreground/8 hover:text-foreground",
          "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-foreground/30",
        )}
      >
        <X className="h-3.5 w-3.5" aria-hidden />
      </button>
    </div>
  );
}
