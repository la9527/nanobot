import { Button } from "@/components/ui/button";
import { useTranslation } from "react-i18next";

interface ThreadStatusRailProps {
  items: string[];
  caption?: string | null;
  onOpenDetails?: () => void;
}

export function ThreadStatusRail({ items, caption = null, onOpenDetails }: ThreadStatusRailProps) {
  const { t } = useTranslation();
  const summary = [...items, ...(caption ? [caption] : [])].join(" · ");

  if (!summary && !onOpenDetails) return null;

  return (
    <div className="px-2.5 pb-1.5">
      <div className="rounded-[12px] border border-border/50 bg-muted/10 px-2.5 py-2">
        <div className="flex items-center gap-2">
          {summary ? (
            <p
              className="min-w-0 flex-1 truncate text-[11px] leading-5 text-muted-foreground"
              title={summary}
            >
              {summary}
            </p>
          ) : <div className="flex-1" />}
          {onOpenDetails ? (
            <Button
              type="button"
              variant="ghost"
              size="sm"
              onClick={onOpenDetails}
              className="ml-auto h-6 rounded-full px-2 text-[11px] text-muted-foreground"
            >
              {t("thread.statusRail.detailsButton")}
            </Button>
          ) : null}
        </div>
      </div>
    </div>
  );
}