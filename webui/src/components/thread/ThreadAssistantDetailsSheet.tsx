import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { taskStatusLabel } from "@/lib/sessionMetadata";
import type {
  DerivedMemoryCorrectionAction,
  DerivedOwnerProfile,
  DerivedTaskSummary,
} from "@/lib/sessionMetadata";
import { useTranslation } from "react-i18next";

interface ThreadAssistantDetailsSheetProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  ownerSummaryBody?: string | null;
  continuityTitle?: string | null;
  continuityBody?: string | null;
  currentTask?: DerivedTaskSummary | null;
  ownerProfile?: DerivedOwnerProfile | null;
  memoryActions?: DerivedMemoryCorrectionAction[];
  onMemoryAction?: (phrase: string) => void;
}

function Section({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <section className="rounded-[14px] border border-border/45 bg-muted/10 px-2.5 py-2.5">
      <h3 className="text-[12px] font-semibold text-foreground/88">{title}</h3>
      <div className="mt-1.5 text-[11px] leading-4.5 text-muted-foreground">{children}</div>
    </section>
  );
}

export function ThreadAssistantDetailsSheet({
  open,
  onOpenChange,
  ownerSummaryBody = null,
  continuityTitle = null,
  continuityBody = null,
  currentTask,
  ownerProfile,
  memoryActions = [],
  onMemoryAction,
}: ThreadAssistantDetailsSheetProps) {
  const { t } = useTranslation();
  const hasContent = Boolean(
    ownerSummaryBody
      || continuityBody
      || currentTask?.title
      || currentTask?.nextStepHint
      || ownerProfile?.preferredLanguage
      || memoryActions.length,
  );

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent side="right" className="w-full max-w-[24rem] p-0 sm:max-w-[24rem]">
        <div className="flex h-full flex-col">
          <SheetHeader className="border-b border-border/50 px-4 py-3">
            <SheetTitle>{t("thread.details.title")}</SheetTitle>
            <SheetDescription className="text-[12px] leading-5">
              {t("thread.details.description")}
            </SheetDescription>
          </SheetHeader>
          <div className="flex-1 space-y-2 overflow-y-auto px-3 py-3">
            {!hasContent ? (
              <Section title={t("thread.details.noExtra.title")}>
                {t("thread.details.noExtra.body")}
              </Section>
            ) : null}

            {currentTask ? (
              <Section title={t("thread.details.currentTask.title")}>
                <div className="flex flex-wrap items-center gap-1">
                  {currentTask.status ? (
                    <span className="inline-flex items-center rounded-full border border-border/50 bg-background/85 px-2 py-0.5 text-[10px] font-medium tracking-wide text-foreground/80">
                      {taskStatusLabel(currentTask.status)}
                    </span>
                  ) : null}
                  {currentTask.originChannel ? (
                    <span className="inline-flex items-center rounded-full border border-border/50 bg-background/85 px-2 py-0.5 text-[10px] font-medium tracking-wide text-foreground/80">
                      {t("thread.details.currentTask.origin", { channel: currentTask.originChannel })}
                    </span>
                  ) : null}
                </div>
                {currentTask.title ? <p className="mt-1.5 text-[12px] leading-5 text-foreground/88">{currentTask.title}</p> : null}
                {currentTask.nextStepHint ? <p className="mt-1">{t("thread.details.currentTask.nextStep", { hint: currentTask.nextStepHint })}</p> : null}
              </Section>
            ) : null}

            {ownerSummaryBody ? (
              <Section title={t("thread.details.assistantOverview.title")}>
                <p>{ownerSummaryBody}</p>
              </Section>
            ) : null}

            {(ownerProfile?.preferredLanguage || ownerProfile?.timezone || ownerProfile?.responseTone || ownerProfile?.responseLength) ? (
              <Section title={t("thread.details.ownerDefaults.title")}>
                <p>
                  {(ownerProfile?.preferredLanguage || t("thread.details.ownerDefaults.unknownLanguage"))}
                  {" · "}
                  {(ownerProfile?.timezone || t("thread.details.ownerDefaults.unknownTimezone"))}
                  {" · "}
                  {(ownerProfile?.responseTone || t("thread.details.ownerDefaults.defaultTone"))}
                  {" · "}
                  {(ownerProfile?.responseLength || t("thread.details.ownerDefaults.defaultLength"))}
                </p>
              </Section>
            ) : null}

            {continuityBody ? (
              <Section title={continuityTitle || t("thread.details.linkedExternalSession.title")}>
                <p>{continuityBody}</p>
              </Section>
            ) : null}

            {memoryActions.length ? (
              <Section title={t("thread.details.memoryTools.title")}>
                <p className="mb-1.5">{t("thread.details.memoryTools.description")}</p>
                <div className="flex flex-wrap gap-1.5">
                  {memoryActions.map((action) => (
                    <button
                      type="button"
                      key={action.code || action.phrase}
                      onClick={() => action.phrase && onMemoryAction?.(action.phrase)}
                      className="inline-flex items-center rounded-full border border-border/50 bg-background px-2.5 py-1 text-[10px] font-medium text-foreground/82 transition-colors hover:bg-muted/60 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
                    >
                      {action.phrase}
                    </button>
                  ))}
                </div>
              </Section>
            ) : null}
          </div>
        </div>
      </SheetContent>
    </Sheet>
  );
}