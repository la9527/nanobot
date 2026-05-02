import { Button } from "@/components/ui/button";

interface ThreadStatusRailProps {
  items: string[];
  caption?: string | null;
  onOpenDetails?: () => void;
}

export function ThreadStatusRail({ items, caption = null, onOpenDetails }: ThreadStatusRailProps) {
  if (items.length === 0 && !caption && !onOpenDetails) return null;

  return (
    <div className="px-2.5 pb-1.5">
      <div className="rounded-[12px] border border-border/50 bg-muted/10 px-2.5 py-2">
        <div className="flex flex-wrap items-center gap-1">
          {items.map((item) => (
            <span
              key={item}
              className="inline-flex items-center rounded-full border border-border/50 bg-background/85 px-2 py-0.5 text-[10px] font-medium tracking-wide text-foreground/82"
            >
              {item}
            </span>
          ))}
          {onOpenDetails ? (
            <Button
              type="button"
              variant="ghost"
              size="sm"
              onClick={onOpenDetails}
              className="ml-auto h-6 rounded-full px-2 text-[11px] text-muted-foreground"
            >
              Assistant details
            </Button>
          ) : null}
        </div>
        {caption ? (
          <p className="mt-1.5 text-[11px] leading-4.5 text-muted-foreground">{caption}</p>
        ) : null}
      </div>
    </div>
  );
}