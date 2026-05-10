import { CircleHelp, X } from "lucide-react";
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { Button } from "@/components/ui/button";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";
import { actionResultReasonLabel, taskStatusLabel } from "@/lib/sessionMetadata";
import { cn } from "@/lib/utils";

interface ThreadInlineActionResultProps {
  placement?: "inline" | "pinned";
  domain?: string | null;
  status?: string | null;
  title?: string | null;
  summary?: string | null;
  preview?: {
    subject?: string;
    body_preview?: string;
    to_recipients?: string[];
    title?: string;
    start_at?: string;
    end_at?: string;
    location?: string | null;
    description?: string | null;
  } | null;
  conflict?: {
    requestedStartAt: string;
    requestedEndAt: string;
    reason?: string | null;
    conflictingEvents?: Array<{
      event_id?: string | null;
      title?: string;
      start_at?: string;
      end_at?: string;
      location?: string | null;
    }>;
  } | null;
  threads?: Array<{
    thread_id?: string;
    subject?: string;
    summary?: string | null;
    sender_summary?: string;
    snippet?: string | null;
  }>;
  onDismiss?: () => void;
  dismissDisabled?: boolean;
}

export function ThreadInlineActionResult({
  placement = "inline",
  status = null,
  title = null,
  summary = null,
  preview = null,
  conflict = null,
  threads = [],
  onDismiss,
  dismissDisabled = false,
}: ThreadInlineActionResultProps) {
  const { t } = useTranslation();
  const visibleThreads = threads.slice(0, 2);
  const [detailsOpen, setDetailsOpen] = useState(false);
  if (!title && !summary && !preview && !conflict && visibleThreads.length === 0) {
    return null;
  }
  const statusLabel = !status
    ? null
    : status === "waiting_approval"
      ? t("thread.inlineAction.status.approvalPending")
      : taskStatusLabel(status);
  const visibleConflicts = conflict?.conflictingEvents?.slice(0, 3) ?? [];
  const extraConflictCount = Math.max(0, (conflict?.conflictingEvents?.length ?? 0) - visibleConflicts.length);
  const hasExpandableDetails = Boolean(preview || conflict || visibleThreads.length > 0);
  const toggleDetails = () => setDetailsOpen((open) => !open);
  const isPinned = placement === "pinned";
  const composeHeadline = () => {
    if (title && summary) {
      const separator = /[.!?]$/.test(title.trim()) ? " " : ". ";
      return `${title}${separator}${summary}`;
    }
    return title || summary || null;
  };
  const compactConflictSummary = conflict
    ? [
      visibleConflicts[0]?.title ? t("thread.inlineAction.conflict.withTitle", { title: visibleConflicts[0].title }) : null,
      extraConflictCount > 0 ? t("thread.inlineAction.conflict.moreCount", { count: extraConflictCount }) : null,
      `${conflict.requestedStartAt} -> ${conflict.requestedEndAt}`,
    ].filter(Boolean).join(" · ")
    : null;
  const compactHeadline = composeHeadline();
  const compactSummary = [compactHeadline, compactConflictSummary].filter(Boolean).join(" · ");
  const summaryContent = (
    <>
      {statusLabel ? (
        <span className="shrink-0 inline-flex items-center rounded-full border border-border/50 bg-background/85 px-2 py-0.5 text-[10px] font-medium tracking-wide text-foreground/80">
          {statusLabel}
        </span>
      ) : null}
      {compactSummary ? <p className="min-w-0 truncate text-[11px] leading-4 text-muted-foreground/95">{compactSummary}</p> : null}
    </>
  );

  return (
    <div
      data-testid={isPinned ? "thread-action-context" : "thread-inline-action-result"}
      className={cn(
        isPinned ? "px-2.5 pb-1.5" : "mb-1.5",
      )}
    >
      <div
        className={cn(
          "rounded-[12px] border border-border/45 bg-muted/10 px-2.5 text-sm text-muted-foreground",
          isPinned ? "py-2" : "py-1.5",
        )}
      >
      <div className="flex items-center gap-2.5">
        <div className="flex min-w-0 flex-1 items-center gap-1.5 overflow-hidden">
          {summaryContent}
        </div>
        {hasExpandableDetails ? (
          <TooltipProvider delayDuration={0}>
            <Tooltip>
              <TooltipTrigger asChild>
                <button
                  type="button"
                  onClick={toggleDetails}
                  aria-label={t("thread.inlineAction.actions.details")}
                  aria-expanded={detailsOpen}
                  className={cn(
                    "shrink-0 inline-flex size-8 items-center justify-center rounded-full border border-border/45 bg-background/80 text-foreground/70 transition-colors hover:bg-background hover:text-foreground",
                    detailsOpen ? "border-border/65 bg-background text-foreground shadow-sm" : undefined,
                    isPinned ? "shadow-sm" : undefined,
                  )}
                >
                  <CircleHelp className="size-4" />
                </button>
              </TooltipTrigger>
              <TooltipContent side="bottom">
                {t("thread.inlineAction.actions.details")}
              </TooltipContent>
            </Tooltip>
          </TooltipProvider>
        ) : null}
        {onDismiss ? (
          <Button
            type="button"
            variant="ghost"
            size="icon"
            onClick={onDismiss}
            aria-label={t("common.dismiss")}
            disabled={dismissDisabled}
            className="h-8 w-8 shrink-0 rounded-full text-foreground/70 hover:bg-background hover:text-foreground"
          >
            <X className="size-4" />
          </Button>
        ) : null}
      </div>

      {detailsOpen && (preview || conflict || visibleThreads.length) ? (
        <div className="mt-2 space-y-1.5 border-t border-border/35 pt-2 text-[11px] leading-4.5">
      {preview?.subject || preview?.title ? (
        <div className="space-y-0.5">
          {preview.to_recipients?.length ? <p><span className="font-medium text-foreground/82">{t("thread.inlineAction.fields.to")}</span> {preview.to_recipients.join(", ")}</p> : null}
          {preview.subject ? <p><span className="font-medium text-foreground/82">{t("thread.inlineAction.fields.subject")}</span> {preview.subject}</p> : null}
          {preview.body_preview ? <p><span className="font-medium text-foreground/82">{t("thread.inlineAction.fields.preview")}</span> {preview.body_preview}</p> : null}
          {preview.title ? <p><span className="font-medium text-foreground/82">{t("thread.inlineAction.fields.title")}</span> {preview.title}</p> : null}
          {preview.start_at && preview.end_at ? <p><span className="font-medium text-foreground/82">{t("thread.inlineAction.fields.when")}</span> {preview.start_at} -&gt; {preview.end_at}</p> : null}
          {preview.location ? <p><span className="font-medium text-foreground/82">{t("thread.inlineAction.fields.location")}</span> {preview.location}</p> : null}
          {preview.description ? <p><span className="font-medium text-foreground/82">{t("thread.inlineAction.fields.details")}</span> {preview.description}</p> : null}
        </div>
      ) : null}

      {conflict ? (
        <div className="space-y-0.5">
          {conflict.reason ? <p><span className="font-medium text-foreground/82">{t("thread.inlineAction.fields.reason")}</span> {actionResultReasonLabel(conflict.reason)}</p> : null}
          {visibleConflicts.length ? (
            <div className="space-y-1 pt-0.5">
              {visibleConflicts.map((event, index) => (
                <div key={event.event_id || `${index}-${event.title || "conflict"}`} className="rounded-[10px] border border-border/40 bg-background/75 px-2 py-1.5">
                  <p className="font-medium text-foreground/85">{event.title || t("thread.inlineAction.fallback.untitledEvent")}</p>
                  <p className="text-muted-foreground/95">{event.start_at || "?"} -&gt; {event.end_at || "?"}</p>
                  {event.location ? <p className="text-muted-foreground/95">{event.location}</p> : null}
                </div>
              ))}
            </div>
          ) : null}
        </div>
      ) : null}

      {visibleThreads.length ? (
        <div className="space-y-1.5">
          {visibleThreads.map((thread, index) => (
            <div key={thread.thread_id || `${index}-${thread.subject || "thread"}`} className="rounded-[10px] border border-border/40 bg-background/75 px-2 py-1.5">
              <p className="font-medium text-foreground/85">{thread.subject || t("thread.inlineAction.fallback.noSubject")}</p>
              <p className="text-muted-foreground/95">{thread.summary || thread.sender_summary || thread.snippet || t("thread.inlineAction.fallback.noSummary")}</p>
            </div>
          ))}
        </div>
      ) : null}
        </div>
      ) : null}
      </div>
    </div>
  );
}