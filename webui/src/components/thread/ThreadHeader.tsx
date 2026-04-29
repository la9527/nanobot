import { PanelLeftOpen } from "lucide-react";
import { useTranslation } from "react-i18next";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

interface ThreadHeaderProps {
  title: string;
  onToggleSidebar: () => void;
  onGoHome: () => void;
  hideSidebarToggleOnDesktop?: boolean;
  statusBadges?: Array<{
    label: string;
    tone?: "default" | "muted" | "warning" | "active";
  }>;
}

export function ThreadHeader({
  title,
  onToggleSidebar,
  onGoHome,
  hideSidebarToggleOnDesktop = false,
  statusBadges = [],
}: ThreadHeaderProps) {
  const { t } = useTranslation();
  return (
    <div className="relative z-10 flex items-start justify-between gap-3 px-3 py-2">
      <div className="relative flex min-w-0 flex-1 items-start gap-2">
        <Button
          variant="ghost"
          size="icon"
          aria-label={t("thread.header.toggleSidebar")}
          onClick={onToggleSidebar}
          className={cn(
            "h-7 w-7 rounded-md text-muted-foreground hover:bg-accent/35 hover:text-foreground",
            hideSidebarToggleOnDesktop && "lg:pointer-events-none lg:opacity-0",
          )}
        >
          <PanelLeftOpen className="h-3.5 w-3.5" />
        </Button>
        <div className="min-w-0 flex-1">
          <button
            type="button"
            onClick={onGoHome}
            className="flex min-w-0 items-center gap-2 rounded-md px-1.5 py-1 text-[12px] font-medium text-muted-foreground transition-colors hover:bg-accent/35 hover:text-foreground"
          >
            <img
              src="/brand/nanobot_icon.png"
              alt=""
              className="h-4 w-4 rounded-[5px] opacity-85"
              aria-hidden
            />
            <span className="max-w-[min(60vw,32rem)] truncate">{title}</span>
          </button>

          {statusBadges.length > 0 ? (
            <div className="mt-1.5 flex flex-wrap items-center gap-1.5 px-1.5">
              {statusBadges.map((badge) => (
                <span
                  key={`${badge.label}-${badge.tone ?? "default"}`}
                  className={cn(
                    "inline-flex items-center rounded-full border px-2 py-0.5 text-[10px] font-medium tracking-wide",
                    badge.tone === "warning" && "border-amber-300/60 bg-amber-50 text-amber-800 dark:border-amber-700/50 dark:bg-amber-950/30 dark:text-amber-200",
                    badge.tone === "active" && "border-emerald-300/60 bg-emerald-50 text-emerald-800 dark:border-emerald-700/50 dark:bg-emerald-950/30 dark:text-emerald-200",
                    badge.tone === "muted" && "border-border/60 bg-muted/50 text-muted-foreground",
                    (!badge.tone || badge.tone === "default") && "border-border/60 bg-background text-foreground/80",
                  )}
                >
                  {badge.label}
                </span>
              ))}
            </div>
          ) : null}
        </div>
      </div>

      <div aria-hidden className="pointer-events-none absolute inset-x-0 top-full h-4" />
    </div>
  );
}
