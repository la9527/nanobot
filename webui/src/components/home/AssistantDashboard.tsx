import { Button } from "@/components/ui/button";
import { relativeTime } from "@/lib/format";
import {
  approvalSummaryLabel,
  getActionResult,
  getProactiveSummary,
  getTaskSummary,
  hasPendingApproval,
  isBlockedSession,
  toChannelBadgeLabel,
} from "@/lib/sessionMetadata";
import type { ChatSummary } from "@/lib/types";

interface AssistantDashboardProps {
  sessions: ChatSummary[];
  onOpenSession?: (key: string) => void;
  onNewChat: () => Promise<string | null>;
}

interface DashboardItem {
  key: string;
  title: string;
  summary: string;
  channelLabel: string;
  updatedLabel: string | null;
  priority: number;
  cta: string;
}

interface DashboardPriorityItem extends DashboardItem {
  updatedAtMs: number;
}

function recentStamp(session: ChatSummary): number {
  return Date.parse(session.updatedAt ?? session.createdAt ?? "") || 0;
}

function sectionCard(
  title: string,
  body: React.ReactNode,
  variant: "strong" | "soft" = "soft",
) {
  return (
    <section className={variant === "strong"
      ? "rounded-[18px] border border-border/60 bg-background/85 p-3 shadow-sm"
      : "rounded-[16px] border border-border/50 bg-muted/10 p-3"
    }>
      <h2 className="text-[12px] font-semibold text-foreground/88">{title}</h2>
      <div className="mt-2 text-[12px] leading-5 text-muted-foreground">{body}</div>
    </section>
  );
}

function compactMetaChip(label: string) {
  return (
    <span className="inline-flex items-center rounded-full border border-border/50 bg-background/85 px-2 py-0.5 text-[10px] font-medium tracking-wide text-foreground/80">
      {label}
    </span>
  );
}

export function AssistantDashboard({ sessions, onOpenSession, onNewChat }: AssistantDashboardProps) {
  const priorityItems: DashboardPriorityItem[] = sessions
    .map<DashboardPriorityItem | null>((session) => {
      const task = getTaskSummary(session);
      const proactive = getProactiveSummary(session);
      const updatedLabel = relativeTime(session.updatedAt ?? session.createdAt);
      const updatedAtMs = recentStamp(session);
      if (hasPendingApproval(session) || task?.status === "waiting-approval") {
        return {
          key: session.key,
          title: task?.title || approvalSummaryLabel(session) || "Approval required",
          summary: task?.nextStepHint || "Review the pending approval request.",
          channelLabel: toChannelBadgeLabel(session.channel),
          updatedLabel,
          updatedAtMs,
          priority: 0,
          cta: "승인 열기",
        };
      }
      if (isBlockedSession(session)) {
        return {
          key: session.key,
          title: task?.title || "Blocked task",
          summary: task?.nextStepHint || "Reopen the blocked thread and continue the interrupted action.",
          channelLabel: toChannelBadgeLabel(session.channel),
          updatedLabel,
          updatedAtMs,
          priority: 1,
          cta: "대화 이어가기",
        };
      }
      if (session.metadata?.pending_user_turn) {
        return {
          key: session.key,
          title: task?.title || "Waiting input",
          summary: task?.nextStepHint || "Open the thread and provide the missing input.",
          channelLabel: toChannelBadgeLabel(session.channel),
          updatedLabel,
          updatedAtMs,
          priority: 2,
          cta: "입력 계속",
        };
      }
      if (proactive?.status === "suppressed") {
        return {
          key: session.key,
          title: proactive.title || "Proactive review needed",
          summary: proactive.summary || "A proactive update is waiting in WebUI because external delivery was held.",
          channelLabel: toChannelBadgeLabel(proactive.targetChannel || session.channel),
          updatedLabel: relativeTime(proactive.updatedAt ?? session.updatedAt ?? session.createdAt),
          updatedAtMs,
          priority: 3,
          cta: "WebUI에서 검토",
        };
      }
      return null;
    })
    .filter((item): item is DashboardPriorityItem => item !== null)
    .sort((left, right) => left.priority - right.priority || right.updatedAtMs - left.updatedAtMs)
    .slice(0, 5);

  const approvalCount = sessions.filter((session) => hasPendingApproval(session)).length;
  const blockedCount = sessions.filter((session) => isBlockedSession(session)).length;
  const heldCount = sessions.filter((session) => getProactiveSummary(session)?.status === "suppressed").length;

  const latestCalendar = [...sessions]
    .filter((session) => getActionResult(session)?.domain === "calendar")
    .sort((left, right) => recentStamp(right) - recentStamp(left))[0];
  const latestMail = [...sessions]
    .filter((session) => getActionResult(session)?.domain === "mail")
    .sort((left, right) => recentStamp(right) - recentStamp(left))[0];

  const recentOutcomes = [...sessions]
    .filter((session) => getActionResult(session)?.status === "completed")
    .sort((left, right) => recentStamp(right) - recentStamp(left))
    .slice(0, 4);

  const linkedChannels = [...sessions]
    .filter((session) => session.channel !== "websocket")
    .sort((left, right) => recentStamp(right) - recentStamp(left))
    .slice(0, 4);

  const heroText = approvalCount > 0 || blockedCount > 0 || heldCount > 0
    ? `오늘 바로 처리할 항목 ${approvalCount + blockedCount + heldCount}개가 있습니다. 승인 ${approvalCount}건, 막힘 ${blockedCount}건, held update ${heldCount}건입니다.`
    : "지금 급한 queue 는 비어 있습니다. 최근 결과를 확인하거나 새 작업을 시작할 수 있습니다.";

  const openFirst = (predicate: (session: ChatSummary) => boolean) => {
    const candidate = sessions.find(predicate);
    if (candidate?.key) {
      onOpenSession?.(candidate.key);
      return;
    }
    void onNewChat();
  };

  return (
    <div className="w-full max-w-[52rem] space-y-3 animate-in fade-in-0 slide-in-from-bottom-2 duration-500">
      <section className="rounded-[18px] border border-border/50 bg-muted/15 p-3.5">
        <p className="text-[11px] font-medium uppercase tracking-[0.14em] text-muted-foreground">Assistant dashboard</p>
        <h1 className="mt-1.5 text-[22px] font-semibold leading-tight text-foreground">오늘 처리할 것과 최근 assistant 상태</h1>
        <p className="mt-2 max-w-[38rem] text-[13px] leading-6 text-muted-foreground">{heroText}</p>
      </section>

      {sectionCard("Priority queue", priorityItems.length ? (
        <div className="space-y-1.5">
          {priorityItems.map((item) => (
            <div key={item.key} className="rounded-[12px] border border-border/40 bg-background/65 px-2.5 py-2">
              <div className="flex items-start justify-between gap-2">
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-1">
                    <p className="text-[12px] font-medium leading-5 text-foreground/88">{item.title}</p>
                    {compactMetaChip(item.channelLabel)}
                    {item.updatedLabel ? compactMetaChip(item.updatedLabel) : null}
                  </div>
                  <p className="mt-0.5 text-[11px] leading-4.5 text-muted-foreground">{item.summary}</p>
                </div>
                <Button
                  type="button"
                  size="sm"
                  variant="outline"
                  className="h-7 shrink-0 rounded-full px-2.5 text-[11px]"
                  onClick={() => onOpenSession?.(item.key)}
                >
                  {item.cta}
                </Button>
              </div>
            </div>
          ))}
        </div>
      ) : (
        <p>지금 바로 triage 할 queue 는 없습니다.</p>
      ), "strong")}

      <div className="grid gap-3 lg:grid-cols-[minmax(0,1.35fr)_minmax(0,1fr)]">
        {sectionCard("Today brief", (
          <div className="space-y-1.5">
            <p className="text-[12px] leading-5">
              {latestCalendar
                ? getActionResult(latestCalendar)?.summary || "최근 일정 요약이 있습니다."
                : "오늘 일정 브리핑 데이터가 아직 없습니다."}
            </p>
            <p className="text-[12px] leading-5">
              {latestMail
                ? getActionResult(latestMail)?.summary || "최근 메일 요약이 있습니다."
                : "중요 메일 요약 데이터가 아직 없습니다."}
            </p>
          </div>
        ))}

        {sectionCard("Quick actions", (
          <div className="flex flex-wrap gap-1.5">
            <Button type="button" size="sm" className="h-8 px-3 text-[12px]" variant="outline" onClick={() => openFirst((session) => hasPendingApproval(session))}>승인 대기 보기</Button>
            <Button type="button" size="sm" className="h-8 px-3 text-[12px]" variant="outline" onClick={() => openFirst((session) => getActionResult(session)?.domain === "calendar")}>오늘 일정 보기</Button>
            <Button type="button" size="sm" className="h-8 px-3 text-[12px]" variant="outline" onClick={() => openFirst((session) => getActionResult(session)?.domain === "mail")}>최근 메일 보기</Button>
            <Button type="button" size="sm" className="h-8 px-3 text-[12px]" onClick={() => void onNewChat()}>새 채팅 시작</Button>
          </div>
        ))}
      </div>

      <div className="grid gap-3 lg:grid-cols-[minmax(0,1.15fr)_minmax(0,1fr)]">
        {sectionCard("Recent outcomes", recentOutcomes.length ? (
          <div className="space-y-2">
            {recentOutcomes.map((session) => {
              const result = getActionResult(session);
              return (
                <div key={session.key} className="rounded-[14px] border border-border/40 bg-background/70 px-2.5 py-2">
                  <div className="flex flex-wrap items-center gap-1.5">
                    <p className="text-[13px] font-medium leading-5 text-foreground/88">{result?.title || "Completed result"}</p>
                    <span className="inline-flex items-center rounded-full border border-border/60 bg-background/85 px-2 py-0.5 text-[10px] font-medium tracking-wide text-foreground/80">
                      {toChannelBadgeLabel(session.channel)}
                    </span>
                  </div>
                  <p className="mt-1 text-[12px] leading-5">{result?.summary || "최근 완료된 작업입니다."}</p>
                  <div className="mt-2">
                    <Button type="button" size="sm" className="h-7 px-2.5 text-[11px]" variant="outline" onClick={() => onOpenSession?.(session.key)}>해당 thread 열기</Button>
                  </div>
                </div>
              );
            })}
          </div>
        ) : (
          <p>최근 완료된 assistant 결과가 아직 없습니다.</p>
        ))}

        {sectionCard("Linked channels", linkedChannels.length ? (
          <div className="space-y-2">
            {linkedChannels.map((session) => {
              const proactive = getProactiveSummary(session);
              return (
                <div key={session.key} className="rounded-[14px] border border-border/40 bg-background/70 px-2.5 py-2">
                  <div className="flex flex-wrap items-center gap-1.5">
                    <p className="text-[13px] font-medium leading-5 text-foreground/88">{toChannelBadgeLabel(session.channel)}</p>
                    <span className="inline-flex items-center rounded-full border border-border/60 bg-background/85 px-2 py-0.5 text-[10px] font-medium tracking-wide text-foreground/80">
                      {relativeTime(session.updatedAt ?? session.createdAt) || "recently updated"}
                    </span>
                  </div>
                  <p className="mt-1 text-[12px] leading-5">
                    {proactive?.status === "suppressed"
                      ? `${proactive.title || "Proactive update"} is being held in WebUI.`
                      : "Connected and available for cross-thread follow-up."}
                  </p>
                </div>
              );
            })}
          </div>
        ) : (
          <p>현재 WebUI 외 연결된 외부 채널 상태가 없습니다.</p>
        ))}
      </div>
    </div>
  );
}