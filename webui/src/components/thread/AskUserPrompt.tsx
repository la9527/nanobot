import { useCallback, useEffect, useRef, useState } from "react";
import { MessageSquareText } from "lucide-react";
import { useTranslation } from "react-i18next";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

interface AskUserPromptProps {
  question: string;
  buttons: string[][];
  onAnswer: (answer: string) => void;
}

export function AskUserPrompt({
  question,
  buttons,
  onAnswer,
}: AskUserPromptProps) {
  const { t } = useTranslation();
  const [customOpen, setCustomOpen] = useState(false);
  const [custom, setCustom] = useState("");
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const options = buttons.flat().filter(Boolean);

  useEffect(() => {
    if (customOpen) {
      inputRef.current?.focus();
    }
  }, [customOpen]);

  const submitCustom = useCallback(() => {
    const answer = custom.trim();
    if (!answer) return;
    onAnswer(answer);
    setCustom("");
    setCustomOpen(false);
  }, [custom, onAnswer]);

  if (options.length === 0) return null;

  const normalizedOptions = options.map((option) => option.trim().toLowerCase());
  const approvalAffirmative = [
    "yes",
    "approve",
    t("thread.askUser.approvalOptions.yes"),
    t("thread.askUser.approvalOptions.approve"),
  ].map((option) => option.trim().toLowerCase());
  const approvalNegative = [
    "no",
    "cancel",
    t("thread.askUser.approvalOptions.no"),
    t("thread.askUser.approvalOptions.cancel"),
  ].map((option) => option.trim().toLowerCase());
  const looksLikeApproval =
    normalizedOptions.some((option) => approvalAffirmative.includes(option))
    && normalizedOptions.some((option) => approvalNegative.includes(option));

  return (
    <div
      className={cn(
        "mx-auto mb-2 w-full max-w-[49.5rem] rounded-[16px] border p-3 shadow-sm backdrop-blur",
        looksLikeApproval
          ? "border-amber-300/50 bg-amber-50/90 dark:border-amber-700/50 dark:bg-amber-950/20"
          : "border-primary/30 bg-card/95",
      )}
      role="group"
      aria-label={looksLikeApproval ? t("thread.askUser.aria.approvalRequest") : t("thread.askUser.aria.question")}
    >
      <div className="mb-2 flex items-start gap-2">
        <div
          className={cn(
            "mt-0.5 rounded-full p-1.5",
            looksLikeApproval
              ? "bg-amber-500/10 text-amber-700 dark:text-amber-300"
              : "bg-primary/10 text-primary",
          )}
        >
          <MessageSquareText className="h-3.5 w-3.5" aria-hidden />
        </div>
        <div className="min-w-0 flex-1">
          <div className="mb-1 flex flex-wrap items-center gap-2">
            <span
              className={cn(
                "inline-flex rounded-full px-2 py-0.5 text-[10px] font-semibold uppercase tracking-[0.08em]",
                looksLikeApproval
                  ? "bg-amber-500/10 text-amber-800 dark:text-amber-200"
                  : "bg-primary/10 text-primary",
              )}
            >
              {looksLikeApproval ? t("thread.askUser.status.waitingApproval") : t("thread.askUser.status.actionPrompt")}
            </span>
            <span className="text-[11px] text-muted-foreground">
              {looksLikeApproval
                ? t("thread.askUser.hint.reviewAndChoose")
                : t("thread.askUser.hint.chooseAnswer")}
            </span>
          </div>
          <p className="min-w-0 flex-1 text-sm font-medium leading-5 text-foreground">
            {question}
          </p>
        </div>
      </div>

      <div className="grid gap-1.5 sm:grid-cols-2">
        {options.map((option) => (
          <Button
            key={option}
            type="button"
            variant="outline"
            size="sm"
            onClick={() => onAnswer(option)}
            className="justify-start rounded-[10px] px-3 text-left"
          >
            <span className="truncate">{option}</span>
          </Button>
        ))}
        <Button
          type="button"
          variant="ghost"
          size="sm"
          onClick={() => setCustomOpen((open) => !open)}
          className="justify-start rounded-[10px] px-3 text-muted-foreground"
        >
          {t("thread.askUser.actions.other")}
        </Button>
      </div>

      {customOpen ? (
        <div className="mt-2 flex gap-2">
          <textarea
            ref={inputRef}
            value={custom}
            onChange={(event) => setCustom(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
                event.preventDefault();
                submitCustom();
              }
            }}
            rows={1}
            placeholder={t("thread.askUser.placeholder.customAnswer")}
            className={cn(
              "min-h-9 flex-1 resize-none rounded-[10px] border border-border/70 bg-background",
              "px-3 py-2 text-sm leading-5 outline-none placeholder:text-muted-foreground",
              "focus-visible:ring-1 focus-visible:ring-primary/40",
            )}
          />
          <Button type="button" size="sm" onClick={submitCustom} disabled={!custom.trim()}>
            {t("thread.askUser.actions.send")}
          </Button>
        </div>
      ) : null}
    </div>
  );
}
