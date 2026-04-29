import {
  AlertTriangle,
  CheckCircle2,
  Clock3,
  LoaderCircle,
  X,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

export type ThreadStatusTone = "running" | "waiting-approval" | "completed" | "failed";

interface ThreadStatusBlockProps {
  tone: ThreadStatusTone;
  title: string;
  body: string;
  onDismiss?: () => void;
}

export function ThreadStatusBlock({ tone, title, body, onDismiss }: ThreadStatusBlockProps) {
  const Icon =
    tone === "running"
      ? LoaderCircle
      : tone === "waiting-approval"
        ? Clock3
        : tone === "completed"
          ? CheckCircle2
          : AlertTriangle;

  return (
    <div
      role={tone === "failed" ? "alert" : "status"}
      aria-live={tone === "failed" ? "assertive" : "polite"}
      className={cn(
        "mb-2 flex items-start gap-3 rounded-[16px] border px-3 py-2.5 shadow-sm",
        tone === "running" && "border-sky-300/45 bg-sky-50/85 text-sky-900 dark:border-sky-700/40 dark:bg-sky-950/20 dark:text-sky-100",
        tone === "waiting-approval" && "border-amber-300/50 bg-amber-50/90 text-amber-950 dark:border-amber-700/50 dark:bg-amber-950/20 dark:text-amber-100",
        tone === "completed" && "border-emerald-300/45 bg-emerald-50/85 text-emerald-950 dark:border-emerald-700/40 dark:bg-emerald-950/20 dark:text-emerald-100",
        tone === "failed" && "border-destructive/30 bg-destructive/10 text-destructive",
      )}
    >
      <div
        className={cn(
          "mt-0.5 rounded-full p-1.5",
          tone === "running" && "bg-sky-500/10 text-sky-700 dark:text-sky-200",
          tone === "waiting-approval" && "bg-amber-500/10 text-amber-700 dark:text-amber-200",
          tone === "completed" && "bg-emerald-500/10 text-emerald-700 dark:text-emerald-200",
          tone === "failed" && "bg-destructive/10 text-destructive",
        )}
      >
        <Icon className={cn("h-4 w-4", tone === "running" && "animate-spin")} aria-hidden />
      </div>
      <div className="min-w-0 flex-1">
        <div className="mb-1 flex flex-wrap items-center gap-2">
          <span className="text-[11px] font-semibold uppercase tracking-[0.08em]">
            {tone === "running"
              ? "Running"
              : tone === "waiting-approval"
                ? "Waiting approval"
                : tone === "completed"
                  ? "Completed"
                  : "Failed"}
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
          aria-label="Dismiss"
          className="h-6 w-6 shrink-0"
        >
          <X className="h-3.5 w-3.5" />
        </Button>
      ) : null}
    </div>
  );
}