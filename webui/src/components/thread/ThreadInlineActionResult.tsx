import { useState } from "react";
import { useTranslation } from "react-i18next";

interface ThreadInlineActionResultProps {
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
}

export function ThreadInlineActionResult({
  domain = null,
  status = null,
  title = null,
  summary = null,
  preview = null,
  conflict = null,
  threads = [],
}: ThreadInlineActionResultProps) {
  const { t } = useTranslation();
  const visibleThreads = threads.slice(0, 2);
  const [detailsOpen, setDetailsOpen] = useState(false);
  if (!title && !summary && !preview && !conflict && visibleThreads.length === 0) {
    return null;
  }

  const label = domain === "calendar"
    ? t("thread.inlineAction.label.calendar")
    : domain === "mail"
      ? t("thread.inlineAction.label.mail")
      : t("thread.inlineAction.label.latest");
  const statusLabel = status === "waiting_approval"
    ? t("thread.inlineAction.status.approvalPending")
    : status
      ? status.replaceAll("_", " ").replace(/^./, (char) => char.toUpperCase())
      : null;
  const detailBadge = preview
    ? status === "waiting_approval"
      ? t("thread.inlineAction.status.approvalPending")
      : domain === "calendar"
        ? t("thread.inlineAction.badge.eventPreview")
        : t("thread.inlineAction.badge.draftPreview")
    : conflict
      ? t("thread.inlineAction.badge.conflictCheck")
      : visibleThreads.length
        ? t("thread.inlineAction.badge.threadSummary")
        : null;
  const humanizeStatus = (value: string | null | undefined) => value
    ? value.replaceAll("_", " ").replace(/^./, (char) => char.toUpperCase())
    : null;
  const visibleConflicts = conflict?.conflictingEvents?.slice(0, 3) ?? [];
  const extraConflictCount = Math.max(0, (conflict?.conflictingEvents?.length ?? 0) - visibleConflicts.length);
  const hasExpandableDetails = Boolean(preview || conflict || visibleThreads.length > 0);
  const compactConflictSummary = conflict
    ? [
      visibleConflicts[0]?.title ? t("thread.inlineAction.conflict.withTitle", { title: visibleConflicts[0].title }) : null,
      extraConflictCount > 0 ? t("thread.inlineAction.conflict.moreCount", { count: extraConflictCount }) : null,
      `${conflict.requestedStartAt} -> ${conflict.requestedEndAt}`,
    ].filter(Boolean).join(" · ")
    : null;
  const compactSummary = [title, summary, compactConflictSummary].filter(Boolean).join(" · ");

  return (
    <div className="mb-1.5 rounded-[12px] border border-border/45 bg-muted/10 px-2.5 py-1.5 text-sm text-muted-foreground">
      <div className="flex flex-wrap items-center gap-1.5">
        <p className="text-[12px] font-medium text-foreground/85">{label}</p>
        {statusLabel ? (
          <span className="inline-flex items-center rounded-full border border-border/50 bg-background/85 px-2 py-0.5 text-[10px] font-medium tracking-wide text-foreground/80">
            {statusLabel}
          </span>
        ) : null}
        {detailBadge && detailBadge !== statusLabel ? (
          <span className="inline-flex items-center rounded-full border border-border/50 bg-background/85 px-2 py-0.5 text-[10px] font-medium tracking-wide text-foreground/80">
            {detailBadge}
          </span>
        ) : null}
      </div>
      <div className="mt-1 flex items-start gap-2">
        <div className="min-w-0 flex-1">
          {compactSummary ? <p className="truncate text-[11px] leading-4 text-muted-foreground/95">{compactSummary}</p> : null}
        </div>
        {hasExpandableDetails ? (
          <button
            type="button"
            onClick={() => setDetailsOpen((open) => !open)}
            className="shrink-0 inline-flex items-center rounded-full border border-border/45 bg-background/80 px-2 py-0.5 text-[10px] font-medium tracking-wide text-foreground/75 transition-colors hover:bg-background"
          >
            {detailsOpen ? t("thread.inlineAction.actions.hide") : t("thread.inlineAction.actions.details")}
          </button>
        ) : null}
      </div>

      {detailsOpen && (preview?.subject || preview?.title) ? (
        <div className="mt-1.5 space-y-0.5 text-[11px] leading-4.5">
          {preview.to_recipients?.length ? <p><span className="font-medium text-foreground/82">{t("thread.inlineAction.fields.to")}</span> {preview.to_recipients.join(", ")}</p> : null}
          {preview.subject ? <p><span className="font-medium text-foreground/82">{t("thread.inlineAction.fields.subject")}</span> {preview.subject}</p> : null}
          {preview.body_preview ? <p><span className="font-medium text-foreground/82">{t("thread.inlineAction.fields.preview")}</span> {preview.body_preview}</p> : null}
          {preview.title ? <p><span className="font-medium text-foreground/82">{t("thread.inlineAction.fields.title")}</span> {preview.title}</p> : null}
          {preview.start_at && preview.end_at ? <p><span className="font-medium text-foreground/82">{t("thread.inlineAction.fields.when")}</span> {preview.start_at} -&gt; {preview.end_at}</p> : null}
          {preview.location ? <p><span className="font-medium text-foreground/82">{t("thread.inlineAction.fields.location")}</span> {preview.location}</p> : null}
          {preview.description ? <p><span className="font-medium text-foreground/82">{t("thread.inlineAction.fields.details")}</span> {preview.description}</p> : null}
        </div>
      ) : null}

      {detailsOpen && conflict ? (
        <div className="mt-1.5 space-y-0.5 text-[11px] leading-4.5">
          {conflict.reason ? <p><span className="font-medium text-foreground/82">{t("thread.inlineAction.fields.reason")}</span> {humanizeStatus(conflict.reason)}</p> : null}
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

      {detailsOpen && visibleThreads.length ? (
        <div className="mt-1.5 space-y-1.5 text-[11px] leading-4.5">
          {visibleThreads.map((thread, index) => (
            <div key={thread.thread_id || `${index}-${thread.subject || "thread"}`} className="rounded-[10px] border border-border/40 bg-background/75 px-2 py-1.5">
              <p className="font-medium text-foreground/85">{thread.subject || t("thread.inlineAction.fallback.noSubject")}</p>
              <p className="text-muted-foreground/95">{thread.summary || thread.sender_summary || thread.snippet || t("thread.inlineAction.fallback.noSummary")}</p>
            </div>
          ))}
        </div>
      ) : null}
    </div>
  );
}