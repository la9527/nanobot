import { useEffect } from "react";
import { useTranslation } from "react-i18next";

import { Button } from "@/components/ui/button";
import type { DerivedContextWindowSummary } from "@/lib/sessionMetadata";
import { cn } from "@/lib/utils";

interface ThreadContextWindowIndicatorProps {
  summary: DerivedContextWindowSummary | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

function compactTokenCount(value: number): string {
  if (value >= 1000) {
    const scaled = value >= 100_000 ? Math.round(value / 1000) : Math.round(value / 100) / 10;
    return `${scaled}`.replace(/\.0$/, "") + "k";
  }
  return `${value}`;
}

function ratioPercent(value: number): number {
  return Math.max(0, Math.min(100, Math.round(value * 1000) / 10));
}

function circleArc(value: number, radius: number): { dasharray: string; dashoffset: number } {
  const circumference = 2 * Math.PI * radius;
  const clamped = Math.max(0, Math.min(1, value));
  return {
    dasharray: `${circumference.toFixed(3)} ${circumference.toFixed(3)}`,
    dashoffset: circumference * (1 - clamped),
  };
}

function formatLocalDateTime(value: string | null | undefined): string | null {
  if (!value) return null;
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;

  const year = parsed.getFullYear();
  const month = `${parsed.getMonth() + 1}`.padStart(2, "0");
  const day = `${parsed.getDate()}`.padStart(2, "0");
  const hours = `${parsed.getHours()}`.padStart(2, "0");
  const minutes = `${parsed.getMinutes()}`.padStart(2, "0");
  const seconds = `${parsed.getSeconds()}`.padStart(2, "0");
  return `${year}-${month}-${day} ${hours}:${minutes}:${seconds}`;
}

export function ThreadContextWindowIndicator({
  summary,
  open,
  onOpenChange,
}: ThreadContextWindowIndicatorProps) {
  const { t } = useTranslation();

  useEffect(() => {
    if (!open) return undefined;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") onOpenChange(false);
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [onOpenChange, open]);

  const usedTokens = summary?.usedInputTokens ?? 0;
  const reservedTokens = summary?.reservedOutputTokens ?? 0;
  const maxTokens = summary?.maxTokens ?? 0;
  const availableTokens = summary?.availableTokens ?? 0;
  const occupiedRatio = summary?.usageRatio ?? 0;
  const usedRatio = maxTokens > 0 ? Math.min(usedTokens / maxTokens, 1) : 0;
  const reservedRatio = maxTokens > 0 ? Math.min(reservedTokens / maxTokens, Math.max(0, 1 - usedRatio)) : 0;
  const status = summary?.status ?? "stale";

  const toneClass =
    status === "critical"
      ? "border-rose-300/70 bg-rose-50 text-rose-900 dark:border-rose-700/60 dark:bg-rose-950/30 dark:text-rose-100"
      : status === "warning"
        ? "border-amber-300/70 bg-amber-50 text-amber-900 dark:border-amber-700/60 dark:bg-amber-950/30 dark:text-amber-100"
        : summary
          ? "border-emerald-300/70 bg-emerald-50 text-emerald-900 dark:border-emerald-700/60 dark:bg-emerald-950/30 dark:text-emerald-100"
          : "border-border/60 bg-background/90 text-muted-foreground";

  const statusLabel = summary
    ? t(`thread.contextWindow.status.${status}`)
    : t("thread.contextWindow.status.unavailable");
  const sourceLabel = summary?.source
    ? t(`thread.contextWindow.source.${summary.source}`, { defaultValue: summary.source })
    : null;
  const formattedUpdatedAt = formatLocalDateTime(summary?.updatedAt);
  const usedArc = circleArc(usedRatio, 15);
  const reservedArc = circleArc(Math.min(usedRatio + reservedRatio, 1), 15);
  const topUsedArc = circleArc(usedRatio, 14);
  const topReservedArc = circleArc(Math.min(usedRatio + reservedRatio, 1), 14);
  const ringStroke =
    status === "critical"
      ? "stroke-rose-500"
      : status === "warning"
        ? "stroke-amber-500"
        : summary
          ? "stroke-emerald-500"
          : "stroke-slate-400 dark:stroke-slate-500";
  return (
    <div className="relative">
      <Button
        type="button"
        variant="ghost"
        onClick={() => onOpenChange(!open)}
        aria-expanded={open}
        aria-label={t("thread.contextWindow.buttonLabel")}
        className={cn(
          "relative h-8 w-8 rounded-full border p-0 shadow-sm transition-colors",
          "hover:bg-accent/40 focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2",
          toneClass,
        )}
      >
        <span className="sr-only">
          {summary
            ? t("thread.contextWindow.compact", {
                used: compactTokenCount(usedTokens),
                max: compactTokenCount(maxTokens),
              })
            : t("thread.contextWindow.unavailable.compact")}
        </span>
        <svg viewBox="0 0 36 36" className="h-[1.35rem] w-[1.35rem] -rotate-90" aria-hidden>
          <circle cx="18" cy="18" r="14" className="fill-none stroke-black/8 stroke-[2.6] dark:stroke-white/10" />
          <circle
            cx="18"
            cy="18"
            r="14"
            className={cn("fill-none stroke-[2.6] transition-all", ringStroke)}
            strokeLinecap="round"
            strokeDasharray={topUsedArc.dasharray}
            strokeDashoffset={topUsedArc.dashoffset}
          />
          <circle
            cx="18"
            cy="18"
            r="14"
            className="fill-none stroke-slate-400/40 stroke-[2.6] transition-all dark:stroke-slate-300/35"
            strokeLinecap="round"
            strokeDasharray={topReservedArc.dasharray}
            strokeDashoffset={topReservedArc.dashoffset}
          />
        </svg>
      </Button>

      {open ? (
        <>
          <button
            type="button"
            aria-label={t("thread.contextWindow.closeOverlay")}
            onClick={() => onOpenChange(false)}
            className="fixed inset-0 z-20 bg-transparent"
          />
          <div
            role="dialog"
            aria-label={t("thread.contextWindow.title")}
            className={cn(
              "fixed inset-x-3 bottom-3 z-30 rounded-[20px] border border-border/70 bg-background/98 p-3.5 shadow-[0_24px_80px_rgba(15,23,42,0.22)] backdrop-blur sm:absolute sm:inset-x-auto sm:bottom-auto sm:right-0 sm:top-full sm:mt-2 sm:w-[18rem]",
              "dark:bg-slate-950/96",
            )}
          >
            {summary ? (
              <>
                <div className="rounded-[18px] border border-border/60 bg-muted/10 p-3">
                  <div className="flex items-center gap-3">
                    <div className="relative flex h-14 w-14 shrink-0 items-center justify-center rounded-full bg-background/70 dark:bg-black/20">
                      <svg viewBox="0 0 36 36" className="h-12 w-12 -rotate-90" aria-hidden>
                        <circle cx="18" cy="18" r="15" className="fill-none stroke-muted/55 stroke-[3]" />
                        <circle
                          cx="18"
                          cy="18"
                          r="15"
                          className={cn("fill-none stroke-[3]", ringStroke)}
                          strokeLinecap="round"
                          strokeDasharray={usedArc.dasharray}
                          strokeDashoffset={usedArc.dashoffset}
                        />
                        <circle
                          cx="18"
                          cy="18"
                          r="15"
                          className="fill-none stroke-slate-400/40 stroke-[3] dark:stroke-slate-300/35"
                          strokeLinecap="round"
                          strokeDasharray={reservedArc.dasharray}
                          strokeDashoffset={reservedArc.dashoffset}
                        />
                      </svg>
                      <span className="absolute text-[11px] font-semibold text-foreground">{ratioPercent(occupiedRatio)}%</span>
                    </div>
                    <div className="min-w-0 flex-1">
                      <div className="flex flex-wrap items-center gap-1.5">
                        <div className="text-[11px] font-medium uppercase tracking-[0.08em] text-muted-foreground">
                          {t("thread.contextWindow.usageLabel")}
                        </div>
                        <span className={cn(
                          "inline-flex items-center rounded-full border px-2 py-0.5 text-[10px] font-medium tracking-wide",
                          status === "critical"
                            ? "border-rose-300/70 bg-rose-50 text-rose-700 dark:border-rose-700/60 dark:bg-rose-950/30 dark:text-rose-200"
                            : status === "warning"
                              ? "border-amber-300/70 bg-amber-50 text-amber-700 dark:border-amber-700/60 dark:bg-amber-950/30 dark:text-amber-200"
                              : "border-emerald-300/70 bg-emerald-50 text-emerald-700 dark:border-emerald-700/60 dark:bg-emerald-950/30 dark:text-emerald-200",
                        )}>
                          {statusLabel}
                        </span>
                      </div>
                      <div className="mt-1 text-base font-semibold text-foreground">
                        {t("thread.contextWindow.compact", {
                          used: compactTokenCount(usedTokens),
                          max: compactTokenCount(maxTokens),
                        })}
                      </div>
                      <div className="mt-1 text-[11px] leading-4 text-muted-foreground">
                        {t("thread.contextWindow.fields.reserve")}: {compactTokenCount(reservedTokens)}
                      </div>
                    </div>
                  </div>
                  {status === "warning" || status === "critical" ? (
                    <p className="mt-3 rounded-[14px] border border-rose-300/65 bg-rose-50/90 px-3 py-2 text-[11px] leading-4.5 text-rose-700 dark:border-rose-800/70 dark:bg-rose-950/35 dark:text-rose-200">
                      {t(`thread.contextWindow.guidance.${status}`)}
                    </p>
                  ) : null}
                </div>

                <dl className="mt-3.5 grid grid-cols-2 gap-2 text-[12px] leading-5">
                  <ContextRow label={t("thread.contextWindow.fields.used")} value={compactTokenCount(usedTokens)} />
                  <ContextRow label={t("thread.contextWindow.fields.reserve")} value={compactTokenCount(reservedTokens)} />
                  <ContextRow label={t("thread.contextWindow.fields.available")} value={compactTokenCount(availableTokens)} />
                  <ContextRow label={t("thread.contextWindow.fields.target")} value={summary.activeTarget || t("thread.contextWindow.unavailable.short")} />
                </dl>

                <div className="mt-3 grid gap-1.5 text-[11px] leading-4 text-muted-foreground">
                  <div>
                    <span className="font-medium text-foreground/85">{t("thread.contextWindow.fields.model")}</span>{" "}
                    {summary.resolvedModel || t("thread.contextWindow.unavailable.short")}
                  </div>
                  <div>
                    <span className="font-medium text-foreground/85">{t("thread.contextWindow.fields.source")}</span>{" "}
                    {sourceLabel || t("thread.contextWindow.unavailable.short")}
                  </div>
                  <div>
                    <span className="font-medium text-foreground/85">{t("thread.contextWindow.fields.updated")}</span>{" "}
                    {formattedUpdatedAt || t("thread.contextWindow.unavailable.short")}
                  </div>
                </div>
              </>
            ) : (
              <div className="rounded-[18px] border border-border/60 bg-muted/10 p-3 text-[11px] leading-4.5 text-muted-foreground">
                {t("thread.contextWindow.unavailable.body")}
              </div>
            )}
          </div>
        </>
      ) : null}
    </div>
  );
}

function ContextRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-[14px] border border-border/50 bg-muted/10 px-2.5 py-2">
      <dt className="text-[10px] font-medium uppercase tracking-[0.08em] text-muted-foreground">{label}</dt>
      <dd className="mt-1 break-words text-[12px] font-medium text-foreground/88">{value}</dd>
    </div>
  );
}