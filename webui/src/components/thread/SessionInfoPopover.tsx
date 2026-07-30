import { useState } from "react";
import {
  CalendarClock,
  CircleAlert,
  ListTodo,
  RefreshCcw,
  Trash2,
} from "lucide-react";
import { useTranslation } from "react-i18next";

import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { useSessionAutomationJobs } from "@/hooks/useSessionAutomationJobs";
import { currentLocale } from "@/i18n";
import { fmtDateTime } from "@/lib/format";
import {
  actionResultReasonLabel,
  approvalSummaryLabel,
  channelLabel,
  contextWindowLabel,
  getActionResult,
  getContextWindowSummary,
  getOwnerProfile,
  getProactiveSummary,
  getTaskSummary,
  hasPendingApproval,
  linkedSessionSummary,
  localizeActionSummary,
  modelTargetLabel,
  ownerDefaultsLabel,
  statusTriggerSummary,
  taskStatusLabel,
  taskStatusTone,
} from "@/lib/sessionMetadata";
import type { ChatSummary, ModelTargetOption, SessionAutomationJob } from "@/lib/types";
import { cn } from "@/lib/utils";

const RELATIVE_THRESHOLDS: [number, Intl.RelativeTimeFormatUnit][] = [
  [60, "second"],
  [60, "minute"],
  [24, "hour"],
  [7, "day"],
  [4.345, "week"],
  [12, "month"],
  [Number.POSITIVE_INFINITY, "year"],
];

interface SessionInfoPopoverProps {
  session: ChatSummary;
  token: string;
  modelTargets?: ModelTargetOption[] | null;
  onClearActionResult?: () => void | Promise<void>;
  onClearProactiveSummary?: () => void | Promise<void>;
}

function Section({
  title,
  children,
  action,
}: {
  title: string;
  children: React.ReactNode;
  action?: React.ReactNode;
}) {
  return (
    <section className="rounded-[18px] border border-border/45 bg-muted/20 px-3 py-3">
      <div className="flex items-center justify-between gap-3">
        <h3 className="text-[12px] font-semibold text-foreground/88">{title}</h3>
        {action}
      </div>
      <div className="mt-2 text-[12.5px] leading-5 text-muted-foreground">{children}</div>
    </section>
  );
}

function InfoChip({
  label,
  tone = "neutral",
}: {
  label: string;
  tone?: "neutral" | "info" | "success" | "warning" | "danger";
}) {
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-full border px-2 py-0.5 text-[10.5px] font-medium tracking-wide",
        tone === "neutral" && "border-border/55 bg-background/80 text-foreground/75",
        tone === "info" && "border-sky-200/70 bg-sky-50 text-sky-700 dark:border-sky-500/25 dark:bg-sky-500/10 dark:text-sky-200",
        tone === "success" && "border-emerald-200/70 bg-emerald-50 text-emerald-700 dark:border-emerald-500/25 dark:bg-emerald-500/10 dark:text-emerald-200",
        tone === "warning" && "border-amber-200/70 bg-amber-50 text-amber-700 dark:border-amber-500/25 dark:bg-amber-500/10 dark:text-amber-200",
        tone === "danger" && "border-rose-200/70 bg-rose-50 text-rose-700 dark:border-rose-500/25 dark:bg-rose-500/10 dark:text-rose-200",
      )}
    >
      {label}
    </span>
  );
}

export function SessionInfoPopover({
  session,
  token,
  modelTargets = null,
  onClearActionResult,
  onClearProactiveSummary,
}: SessionInfoPopoverProps) {
  const { t } = useTranslation("common");
  const [open, setOpen] = useState(false);
  const { jobs, loading, loadFailed, now } = useSessionAutomationJobs(open, token, session.key);
  const summary = statusTriggerSummary(session, modelTargets);
  const targetLabel = modelTargetLabel(session.activeTarget, modelTargets);
  const linkedSummary = linkedSessionSummary(session);
  const task = getTaskSummary(session);
  const taskStatus = task?.status ? taskStatusLabel(task.status) : null;
  const actionResult = getActionResult(session);
  const actionSummary = localizeActionSummary(actionResult);
  const proactive = getProactiveSummary(session);
  const proactiveSummary = proactive?.summary?.trim() || proactive?.title?.trim() || null;
  const contextWindow = getContextWindowSummary(session);
  const contextLabel = contextWindowLabel(contextWindow);
  const ownerDefaults = ownerDefaultsLabel(session);
  const ownerProfile = getOwnerProfile(session);
  const approvalPreview = approvalSummaryLabel(session);
  const triggerLabel = summary?.label ?? t("thread.header.sessionInfo");

  return (
    <DropdownMenu modal={false} open={open} onOpenChange={setOpen}>
      <DropdownMenuTrigger asChild>
        {summary ? (
          <button
            type="button"
            aria-label={t("thread.header.sessionInfo")}
            className={cn(
              "host-no-drag inline-flex h-8 max-w-[16rem] items-center gap-2 rounded-full border px-2.5 text-[11.5px] font-medium",
              "transition-colors hover:bg-accent/40",
              summary.tone === "neutral" && "border-border/55 bg-card text-foreground/82",
              summary.tone === "info" && "border-sky-200/70 bg-sky-50 text-sky-700 dark:border-sky-500/25 dark:bg-sky-500/10 dark:text-sky-200",
              summary.tone === "success" && "border-emerald-200/70 bg-emerald-50 text-emerald-700 dark:border-emerald-500/25 dark:bg-emerald-500/10 dark:text-emerald-200",
              summary.tone === "warning" && "border-amber-200/70 bg-amber-50 text-amber-700 dark:border-amber-500/25 dark:bg-amber-500/10 dark:text-amber-200",
              summary.tone === "danger" && "border-rose-200/70 bg-rose-50 text-rose-700 dark:border-rose-500/25 dark:bg-rose-500/10 dark:text-rose-200",
            )}
          >
            {summary.tone === "warning" || summary.tone === "danger" ? (
              <CircleAlert className="h-3.5 w-3.5 shrink-0" />
            ) : (
              <ListTodo className="h-3.5 w-3.5 shrink-0" />
            )}
            <span className="truncate">{triggerLabel}</span>
          </button>
        ) : (
          <Button
            variant="ghost"
            size="icon"
            aria-label={t("thread.header.sessionInfo")}
            className={cn(
              "host-no-drag h-8 w-8 rounded-full text-muted-foreground/85",
              "hover:bg-accent/40 hover:text-foreground",
            )}
          >
            <ListTodo className="h-4 w-4 stroke-[1.75]" />
          </Button>
        )}
      </DropdownMenuTrigger>
      <DropdownMenuContent
        align="end"
        sideOffset={8}
        className="w-[min(27rem,calc(100vw-1rem))] rounded-[24px] p-0"
      >
        <div className="space-y-3 px-4 py-4">
          <div className="min-w-0">
            <div className="text-[12px] font-normal text-muted-foreground/75">
              {t("thread.sessionInfo.title")}
            </div>
            <div className="mt-0.5 truncate text-[14px] font-medium text-foreground">
              {session.title?.trim() || t("thread.sessionInfo.untitled")}
            </div>
          </div>

          <div className="flex flex-wrap gap-1.5">
            {targetLabel ? <InfoChip label={targetLabel} tone="info" /> : null}
            {taskStatus ? <InfoChip label={taskStatus} tone={taskStatusTone(task?.status)} /> : null}
            {hasPendingApproval(session) ? <InfoChip label="Approval pending" tone="warning" /> : null}
            {contextWindow?.status === "critical"
              ? <InfoChip label="Context low" tone="danger" />
              : contextWindow?.status === "warning"
                ? <InfoChip label="Context warning" tone="warning" />
                : null}
          </div>

          {(targetLabel || linkedSummary || approvalPreview || proactiveSummary) ? (
            <Section
              title="Session status"
              action={proactiveSummary && onClearProactiveSummary ? (
                <button
                  type="button"
                  aria-label="Dismiss proactive summary"
                  className="inline-flex h-7 w-7 items-center justify-center rounded-full text-muted-foreground transition-colors hover:bg-background hover:text-foreground"
                  onClick={() => void onClearProactiveSummary()}
                >
                  <Trash2 className="h-3.5 w-3.5" />
                </button>
              ) : undefined}
            >
              <div className="space-y-1.5">
                {targetLabel ? (
                  <p><span className="font-medium text-foreground/82">Target</span> {targetLabel}</p>
                ) : null}
                {linkedSummary ? (
                  <p><span className="font-medium text-foreground/82">Linked session</span> {linkedSummary}</p>
                ) : null}
                {approvalPreview ? (
                  <p><span className="font-medium text-foreground/82">Approval</span> {approvalPreview}</p>
                ) : null}
                {proactiveSummary ? (
                  <p><span className="font-medium text-foreground/82">Proactive</span> {proactiveSummary}</p>
                ) : null}
              </div>
            </Section>
          ) : null}

          {task ? (
            <Section title="Current task">
              <div className="space-y-1.5">
                {task.title ? <p className="text-foreground/88">{task.title}</p> : null}
                {task.next_step_hint ? <p>{task.next_step_hint}</p> : null}
                {task.origin_channel ? (
                  <p><span className="font-medium text-foreground/82">Origin</span> {channelLabel(task.origin_channel) || task.origin_channel}</p>
                ) : null}
              </div>
            </Section>
          ) : null}

          {actionResult && actionSummary ? (
            <Section
              title="Latest action"
              action={onClearActionResult ? (
                <button
                  type="button"
                  aria-label="Dismiss latest action"
                  className="inline-flex h-7 w-7 items-center justify-center rounded-full text-muted-foreground transition-colors hover:bg-background hover:text-foreground"
                  onClick={() => void onClearActionResult()}
                >
                  <Trash2 className="h-3.5 w-3.5" />
                </button>
              ) : undefined}
            >
              <div className="space-y-1.5">
                <p className="text-foreground/88">{actionSummary}</p>
                {actionResult.next_step ? <p>{actionResult.next_step}</p> : null}
                {actionResult.details?.preview?.to_recipients?.length ? (
                  <p><span className="font-medium text-foreground/82">To</span> {actionResult.details.preview.to_recipients.join(", ")}</p>
                ) : null}
                {actionResult.details?.preview?.title ? (
                  <p><span className="font-medium text-foreground/82">Title</span> {actionResult.details.preview.title}</p>
                ) : null}
                {actionResult.details?.preview?.subject ? (
                  <p><span className="font-medium text-foreground/82">Subject</span> {actionResult.details.preview.subject}</p>
                ) : null}
                {actionResult.details?.reason ? (
                  <p><span className="font-medium text-foreground/82">Reason</span> {actionResultReasonLabel(actionResult.details.reason)}</p>
                ) : null}
              </div>
            </Section>
          ) : null}

          {contextLabel ? (
            <Section title="Context window">
              <div className="space-y-1.5">
                <p>{contextLabel}</p>
                {typeof contextWindow?.available_tokens === "number" ? (
                  <p><span className="font-medium text-foreground/82">Available</span> {contextWindow.available_tokens.toLocaleString()}</p>
                ) : null}
                {typeof contextWindow?.max_tokens === "number" ? (
                  <p><span className="font-medium text-foreground/82">Budget</span> {contextWindow.max_tokens.toLocaleString()}</p>
                ) : null}
                {contextWindow?.resolved_model ? (
                  <p><span className="font-medium text-foreground/82">Resolved model</span> {contextWindow.resolved_model}</p>
                ) : null}
              </div>
            </Section>
          ) : null}

          {(ownerDefaults || ownerProfile?.canonical_owner_id) ? (
            <Section title="Owner defaults">
              <div className="space-y-1.5">
                {ownerDefaults ? <p>{ownerDefaults}</p> : null}
                {ownerProfile?.canonical_owner_id ? (
                  <p><span className="font-medium text-foreground/82">Owner</span> {ownerProfile.canonical_owner_id}</p>
                ) : null}
              </div>
            </Section>
          ) : null}

          <Section title={t("thread.sessionInfo.automations")}>
              {loading ? (
                <div className="flex items-center gap-2 rounded-[16px] bg-muted/45 px-3 py-3 text-[12.5px] text-muted-foreground">
                  <RefreshCcw className="h-3.5 w-3.5 animate-spin" />
                  {t("thread.sessionInfo.loading")}
                </div>
              ) : loadFailed ? (
                <div className="flex items-center gap-2 rounded-[16px] bg-destructive/10 px-3 py-3 text-[12.5px] text-destructive">
                  <CircleAlert className="h-3.5 w-3.5" />
                  {t("thread.sessionInfo.loadFailed")}
                </div>
              ) : jobs.length ? (
                <div className="space-y-1.5">
                  {jobs.map((job) => (
                    <AutomationRow key={job.id} job={job} now={now} />
                  ))}
                </div>
              ) : (
                <div className="rounded-[16px] bg-muted/35 px-3 py-3 text-[12.5px] leading-relaxed text-muted-foreground">
                  {t("thread.sessionInfo.empty")}
                </div>
              )}
          </Section>
        </div>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

function AutomationRow({ job, now }: { job: SessionAutomationJob; now: number }) {
  const { t } = useTranslation("common");
  const schedule = formatSchedule(job, t);
  const nextRun = formatNextRun(job, t, now);
  const statusClass = job.enabled
    ? job.state.last_status === "error"
      ? "bg-destructive"
      : "bg-emerald-500"
    : "bg-muted-foreground/35";

  return (
    <div className="rounded-[16px] px-3 py-2.5 transition-colors hover:bg-muted/40">
      <div className="flex items-start gap-2.5">
        <span className={cn("mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full", statusClass)} />
        <div className="min-w-0 flex-1">
          <div className="flex min-w-0 items-center gap-2">
            <span className="truncate text-[13px] font-medium text-foreground">{job.name}</span>
            {!job.enabled ? (
              <span className="shrink-0 rounded-full bg-muted px-1.5 py-0.5 text-[10.5px] text-muted-foreground">
                {t("thread.sessionInfo.disabled")}
              </span>
            ) : null}
          </div>
          <div className="mt-1 line-clamp-2 text-[12px] leading-snug text-muted-foreground">
            {job.payload.message}
          </div>
          <div className="mt-2 flex flex-wrap items-center gap-x-2 gap-y-1 text-[11.5px] text-muted-foreground/80">
            <CalendarClock className="h-3.5 w-3.5 shrink-0" />
            <span>{schedule}</span>
            <span aria-hidden>·</span>
            <span title={nextRun.title}>{nextRun.label}</span>
          </div>
        </div>
      </div>
    </div>
  );
}

function formatSchedule(job: SessionAutomationJob, t: (key: string, options?: Record<string, unknown>) => string) {
  const locale = currentLocale();
  if (job.schedule.kind === "at" && job.schedule.at_ms) {
    return t("thread.sessionInfo.schedule.at", { time: fmtDateTime(job.schedule.at_ms, locale) });
  }
  if (job.schedule.kind === "every" && job.schedule.every_ms) {
    return t("thread.sessionInfo.schedule.every", {
      duration: formatDuration(job.schedule.every_ms, locale),
    });
  }
  if (job.schedule.kind === "cron" && job.schedule.expr) {
    return job.schedule.tz
      ? t("thread.sessionInfo.schedule.cronWithTz", {
          expr: job.schedule.expr,
          tz: job.schedule.tz,
        })
      : t("thread.sessionInfo.schedule.cron", { expr: job.schedule.expr });
  }
  return t("thread.sessionInfo.schedule.unknown");
}

function formatNextRun(
  job: SessionAutomationJob,
  t: (key: string, options?: Record<string, unknown>) => string,
  now: number,
) {
  const locale = currentLocale();
  if (!job.enabled) {
    return { label: t("thread.sessionInfo.next.disabled"), title: "" };
  }
  if (job.state.pending) {
    return { label: t("thread.sessionInfo.next.pending"), title: "" };
  }
  const next = job.state.next_run_at_ms;
  if (!next) {
    return { label: t("thread.sessionInfo.next.none"), title: "" };
  }
  return {
    label: t("thread.sessionInfo.next.label", { time: relativeTimeFrom(next, now, locale) }),
    title: fmtDateTime(next, locale),
  };
}

function relativeTimeFrom(value: number, now: number, locale: string): string {
  let delta = (value - now) / 1000;
  const formatter = new Intl.RelativeTimeFormat(locale, { numeric: "auto" });
  for (const [step, unit] of RELATIVE_THRESHOLDS) {
    if (Math.abs(delta) < step) {
      return formatter.format(Math.round(delta), unit);
    }
    delta /= step;
  }
  return formatter.format(Math.round(delta), "year");
}

function formatDuration(ms: number, locale: string): string {
  const units: Array<[Intl.NumberFormatOptions["unit"], number]> = [
    ["day", 86_400_000],
    ["hour", 3_600_000],
    ["minute", 60_000],
    ["second", 1000],
  ];
  for (const [unit, size] of units) {
    if (ms >= size && ms % size === 0) {
      return new Intl.NumberFormat(locale, {
        style: "unit",
        unit,
        unitDisplay: "long",
        maximumFractionDigits: 0,
      }).format(ms / size);
    }
  }
  return new Intl.NumberFormat(locale, {
    style: "unit",
    unit: "minute",
    unitDisplay: "long",
    maximumFractionDigits: 1,
  }).format(ms / 60_000);
}
