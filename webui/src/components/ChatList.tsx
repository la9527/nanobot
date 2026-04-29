import { useState } from "react";

import { MoreHorizontal, Trash2 } from "lucide-react";
import { useTranslation } from "react-i18next";

import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { ScrollArea } from "@/components/ui/scroll-area";
import { relativeTime } from "@/lib/format";
import { cn } from "@/lib/utils";
import type { ChatSummary } from "@/lib/types";

interface ChatListProps {
  sessions: ChatSummary[];
  activeKey: string | null;
  onSelect: (key: string) => void;
  onRequestDelete: (key: string, label: string) => void;
  loading?: boolean;
}

function titleFor(s: ChatSummary, fallbackTitle: string): string {
  const p = s.preview?.trim();
  if (p) return p.length > 48 ? `${p.slice(0, 45)}…` : p;
  return fallbackTitle;
}

function targetBadgeLabel(activeTarget: string | null | undefined): string | null {
  if (!activeTarget) return null;
  const trimmed = activeTarget.trim();
  if (!trimmed || trimmed === "default") return null;
  if (trimmed === "smart_router") return "smart-router";
  return trimmed;
}

function channelBadgeLabel(channel: string): string | null {
  if (!channel || channel === "websocket") return null;
  return channel;
}

function hasPendingApproval(session: ChatSummary): boolean {
  return session.metadata?.approval_summary?.status === "pending";
}

function approvalSummaryLabel(session: ChatSummary): string | null {
  const summary = session.metadata?.approval_summary;
  if (!summary || summary.status !== "pending") return null;
  const toolName = summary.tool_name?.trim() || "tool";
  const promptPreview = summary.prompt_preview?.trim();
  return promptPreview ? `${toolName}: ${promptPreview}` : `${toolName} approval pending`;
}

export function ChatList({
  sessions,
  activeKey,
  onSelect,
  onRequestDelete,
  loading,
}: ChatListProps) {
  const { t } = useTranslation();
  const [expandedApprovalKey, setExpandedApprovalKey] = useState<string | null>(null);

  if (loading && sessions.length === 0) {
    return (
      <div className="px-3 py-6 text-[12px] text-muted-foreground">
        {t("chat.loading")}
      </div>
    );
  }

  if (sessions.length === 0) {
    return (
      <div className="px-3 py-6 text-xs text-muted-foreground">
        {t("chat.noSessions")}
      </div>
    );
  }

  return (
    <ScrollArea className="h-full">
      <ul className="space-y-0.5 px-2 py-1">
        {sessions.map((s) => {
          const active = s.key === activeKey;
          const title = titleFor(
            s,
            t("chat.fallbackTitle", { id: s.chatId.slice(0, 6) }),
          );
          const badge = targetBadgeLabel(s.activeTarget);
          const channelBadge = channelBadgeLabel(s.channel);
          const approvalBadge = hasPendingApproval(s);
          const approvalSummary = approvalSummaryLabel(s);
          const approvalExpanded = expandedApprovalKey === s.key;
          const approvalDetailId = `approval-summary-${s.key.replace(/[^a-zA-Z0-9_-]/g, "-")}`;
          const canDelete = s.channel === "websocket";
          return (
            <li key={s.key}>
              <div
                className={cn(
                  "group flex items-start gap-2 rounded-md px-2 py-1.5 text-[12.5px] transition-colors",
                  active
                    ? "bg-sidebar-accent/80 text-sidebar-accent-foreground shadow-[inset_0_0_0_1px_hsl(var(--border)/0.4)]"
                    : "text-sidebar-foreground/88 hover:bg-sidebar-accent/45",
                )}
              >
                <div className="min-w-0 flex-1">
                  <button
                    type="button"
                    onClick={() => onSelect(s.key)}
                    className="flex min-w-0 w-full flex-col items-start text-left"
                  >
                    <span className="w-full truncate font-medium leading-5">{title}</span>
                    <span className="mt-0.5 flex min-w-0 items-center gap-1.5 text-[10.5px] text-muted-foreground/80">
                      <span>{relativeTime(s.updatedAt ?? s.createdAt) || "—"}</span>
                      {channelBadge ? (
                        <span className="inline-flex max-w-[7rem] truncate rounded-full border border-sidebar-border/80 bg-sidebar-accent/35 px-1.5 py-[1px] text-[9.5px] font-medium uppercase tracking-[0.08em] text-sidebar-foreground/78">
                          {channelBadge}
                        </span>
                      ) : null}
                      {badge ? (
                        <span className="inline-flex max-w-[8rem] truncate rounded-full border border-sidebar-border/80 bg-card/30 px-1.5 py-[1px] text-[9.5px] font-medium text-sidebar-foreground/80">
                          {badge}
                        </span>
                      ) : null}
                    </span>
                  </button>
                  {approvalBadge ? (
                    <div className="mt-1.5 flex flex-col items-start gap-1">
                      <button
                        type="button"
                        onClick={() => {
                          setExpandedApprovalKey((current) => (current === s.key ? null : s.key));
                        }}
                        className="inline-flex max-w-full items-center truncate rounded-full border border-amber-300/60 bg-amber-100/70 px-1.5 py-[1px] text-[9.5px] font-medium text-amber-900 transition-colors hover:bg-amber-100 dark:border-amber-700/50 dark:bg-amber-950/30 dark:text-amber-200 dark:hover:bg-amber-950/50"
                        aria-expanded={approvalExpanded}
                        aria-controls={approvalDetailId}
                      >
                        Approval pending
                      </button>
                      {approvalExpanded && approvalSummary ? (
                        <div
                          id={approvalDetailId}
                          className="max-w-full rounded-md border border-amber-300/40 bg-amber-50/80 px-2 py-1.5 text-[10.5px] leading-4 text-amber-950 shadow-sm dark:border-amber-700/40 dark:bg-amber-950/25 dark:text-amber-100"
                        >
                          {approvalSummary}
                        </div>
                      ) : null}
                    </div>
                  ) : null}
                </div>
                <DropdownMenu modal={false}>
                  <DropdownMenuTrigger
                    className={cn(
                      "inline-flex h-6 w-6 items-center justify-center rounded-md text-muted-foreground opacity-0 transition-opacity",
                      "hover:bg-sidebar-accent hover:text-sidebar-foreground group-hover:opacity-100",
                      "focus-visible:opacity-100",
                      active && "opacity-100",
                    )}
                    aria-label={t("chat.actions", { title })}
                  >
                    <MoreHorizontal className="h-4 w-4" />
                  </DropdownMenuTrigger>
                  <DropdownMenuContent
                    align="end"
                    onCloseAutoFocus={(event) => event.preventDefault()}
                  >
                    {canDelete ? (
                      <DropdownMenuItem
                        onSelect={() => {
                          window.setTimeout(() => onRequestDelete(s.key, title), 0);
                        }}
                        className="text-destructive focus:text-destructive"
                      >
                        <Trash2 className="mr-2 h-4 w-4" />
                        {t("chat.delete")}
                      </DropdownMenuItem>
                    ) : null}
                  </DropdownMenuContent>
                </DropdownMenu>
              </div>
            </li>
          );
        })}
      </ul>
    </ScrollArea>
  );
}
