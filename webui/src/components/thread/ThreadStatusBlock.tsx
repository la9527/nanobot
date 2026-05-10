import { useEffect, useState } from "react";
import {
  AlertTriangle,
  CheckCircle2,
  ChevronRight,
  Clock3,
  LoaderCircle,
  X,
} from "lucide-react";
import { useTranslation } from "react-i18next";

import { Button } from "@/components/ui/button";
import type { ReasoningVisibility } from "@/lib/types";
import { cn } from "@/lib/utils";

export type ThreadStatusTone = "running" | "waiting-approval" | "completed" | "failed";

interface ThreadStatusBlockProps {
  tone: ThreadStatusTone;
  title: string;
  body: string;
  reasoningVisibility?: ReasoningVisibility;
  onDismiss?: () => void;
}

export function ThreadStatusBlock({
  tone,
  title,
  body,
  reasoningVisibility = "summary",
  onDismiss,
}: ThreadStatusBlockProps) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  const isReasoningTone = tone === "running" || tone === "completed";
  const allowsExpansion = isReasoningTone
    && (reasoningVisibility === "summary" || reasoningVisibility === "debug_trace");

  useEffect(() => {
    if (!allowsExpansion) {
      setOpen(false);
      return;
    }
    setOpen(tone === "running");
  }, [allowsExpansion, tone, title, body]);

  if (isReasoningTone && reasoningVisibility === "off") {
    return null;
  }

  if (isReasoningTone) {
    return (
      <div role="status" aria-live="polite" className="mb-2">
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
              onClick={() => setOpen((value) => !value)}
              className={cn(
                "flex w-full items-start gap-3 px-3 py-2.5 text-left",
                "transition-colors hover:bg-slate-100/80 dark:hover:bg-slate-900/40",
              )}
              aria-expanded={open}
            >
              <ReasoningStatusLeadingIcon tone={tone} />
              <div className="min-w-0 flex-1">
                <div className="mb-1 flex flex-wrap items-center gap-2">
                  <span className="text-[11px] font-semibold uppercase tracking-[0.08em] text-slate-500 dark:text-slate-400">
                    {tone === "running"
                      ? t("thread.statusTone.running")
                      : t("thread.statusTone.completed")}
                  </span>
                  <span className="text-sm font-medium leading-5 text-slate-800 dark:text-slate-100">
                    {title}
                  </span>
                </div>
                {!open ? (
                  <p className="line-clamp-2 whitespace-pre-wrap break-words text-[12px] leading-5 text-slate-600 dark:text-slate-300">
                    {body}
                  </p>
                ) : null}
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
              <ReasoningStatusLeadingIcon tone={tone} />
              <div className="min-w-0 flex-1">
                <div className="mb-1 flex flex-wrap items-center gap-2">
                  <span className="text-[11px] font-semibold uppercase tracking-[0.08em] text-slate-500 dark:text-slate-400">
                    {tone === "running"
                      ? t("thread.statusTone.running")
                      : t("thread.statusTone.completed")}
                  </span>
                  <span className="text-sm font-medium leading-5 text-slate-800 dark:text-slate-100">
                    {title}
                  </span>
                </div>
                <p className="line-clamp-2 whitespace-pre-wrap break-words text-[12px] leading-5 text-slate-600 dark:text-slate-300">
                  {body}
                </p>
              </div>
            </div>
          )}
          {allowsExpansion && open ? (
            <div className="border-t border-slate-200/80 px-3 pb-3 pt-2 dark:border-slate-800/80">
              <p className="whitespace-pre-wrap break-words text-[12px] leading-6 text-slate-600 dark:text-slate-300">
                {body}
              </p>
            </div>
          ) : null}
        </div>
      </div>
    );
  }

  const Icon = tone === "waiting-approval" ? Clock3 : AlertTriangle;

  return (
    <div
      role={tone === "failed" ? "alert" : "status"}
      aria-live={tone === "failed" ? "assertive" : "polite"}
      className={cn(
        "mb-2 flex items-start gap-3 rounded-[16px] border px-3 py-2.5 shadow-sm",
        tone === "waiting-approval" && "border-amber-300/50 bg-amber-50/90 text-amber-950 dark:border-amber-700/50 dark:bg-amber-950/20 dark:text-amber-100",
        tone === "failed" && "border-destructive/30 bg-destructive/10 text-destructive",
      )}
    >
      <div
        className={cn(
          "mt-0.5 rounded-full p-1.5",
          tone === "waiting-approval" && "bg-amber-500/10 text-amber-700 dark:text-amber-200",
          tone === "failed" && "bg-destructive/10 text-destructive",
        )}
      >
        <Icon className="h-4 w-4" aria-hidden />
      </div>
      <div className="min-w-0 flex-1">
        <div className="mb-1 flex flex-wrap items-center gap-2">
          <span className="text-[11px] font-semibold uppercase tracking-[0.08em]">
            {tone === "waiting-approval"
              ? t("thread.statusTone.waitingApproval")
              : t("thread.statusTone.failed")}
          </span>
          <span className="text-sm font-medium leading-5">{title}</span>
        </div>
        <p className="text-[12px] leading-5 opacity-85">{body}</p>
      </div>
      {onDismiss ? (
        <Button
          variant="ghost"
          size="icon"
          onClick={onDismiss}
          aria-label={t("common.dismiss")}
          className="h-6 w-6 shrink-0"
        >
          <X className="h-3.5 w-3.5" />
        </Button>
      ) : null}
    </div>
  );
}

function ReasoningStatusLeadingIcon({ tone }: { tone: Extract<ThreadStatusTone, "running" | "completed"> }) {
  return (
    <div
      className={cn(
        "mt-0.5 rounded-full p-1.5",
        "bg-slate-200/80 text-slate-600 dark:bg-slate-800/80 dark:text-slate-300",
      )}
    >
      {tone === "running" ? (
        <LoaderCircle className="h-4 w-4 animate-spin" aria-hidden />
      ) : (
        <CheckCircle2 className="h-4 w-4" aria-hidden />
      )}
    </div>
  );
}