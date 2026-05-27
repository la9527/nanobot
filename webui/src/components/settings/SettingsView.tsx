import { useCallback, useEffect, useMemo, useState } from "react";
import { Activity, CheckCircle2, ChevronLeft, Circle, Loader2, Minus, Moon, Play, Plus, RotateCw, Square, Star, Sun, Zap } from "lucide-react";
import { useTranslation } from "react-i18next";

import { LanguageSwitcher } from "@/components/LanguageSwitcher";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";
import { fetchLocalLlmStatus, fetchSettings, runLocalLlmAction, updateSettings } from "@/lib/api";
import { cn } from "@/lib/utils";
import { useClient } from "@/providers/ClientProvider";
import type { LocalLlmStatusPayload, LocalLlmTargetStatus, ReasoningVisibility, SettingsPayload } from "@/lib/types";

interface SettingsViewProps {
  theme: "light" | "dark";
  onToggleTheme: () => void;
  onBackToChat: () => void;
  reasoningVisibility: ReasoningVisibility;
  onReasoningVisibilityChange: (next: ReasoningVisibility) => void;
  onModelNameChange: (modelName: string | null) => void;
  chatFontSize: "sm" | "md" | "lg";
  chatFontValue: number;
  onDecreaseChatFont: () => void;
  onIncreaseChatFont: () => void;
  onLogout?: () => void;
  onRestart?: () => void;
}

export function SettingsView({
  theme,
  onToggleTheme,
  onBackToChat,
  reasoningVisibility,
  onReasoningVisibilityChange,
  onModelNameChange,
  chatFontSize,
  chatFontValue,
  onDecreaseChatFont,
  onIncreaseChatFont,
  onLogout,
  onRestart,
}: SettingsViewProps) {
  const { t } = useTranslation();
  const { token } = useClient();
  const [settings, setSettings] = useState<SettingsPayload | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [localLlm, setLocalLlm] = useState<LocalLlmStatusPayload | null>(null);
  const [localLlmError, setLocalLlmError] = useState<string | null>(null);
  const [localLlmBusy, setLocalLlmBusy] = useState<string | null>(null);
  const [localLlmMessage, setLocalLlmMessage] = useState<string | null>(null);
  const [form, setForm] = useState({
    model: "",
    provider: "auto",
  });

  const applyPayload = useCallback((payload: SettingsPayload) => {
    setSettings(payload);
    setForm({
      model: payload.agent.model,
      provider: payload.agent.provider,
    });
  }, []);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    Promise.all([
      fetchSettings(token),
      fetchLocalLlmStatus(token).catch((err) => {
        if (!cancelled) setLocalLlmError((err as Error).message);
        return null;
      }),
    ])
      .then(([payload, localPayload]) => {
        if (!cancelled) {
          applyPayload(payload);
          setLocalLlm(localPayload);
          setError(null);
        }
      })
      .catch((err) => {
        if (!cancelled) setError((err as Error).message);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [applyPayload, token]);

  const refreshLocalLlm = useCallback(async () => {
    const payload = await fetchLocalLlmStatus(token);
    setLocalLlm(payload);
    setLocalLlmError(null);
  }, [token]);

  const runLocalAction = useCallback(async (action: string, target: string) => {
    const confirmActions = new Set(["stop", "restart", "use"]);
    if (confirmActions.has(action) && !window.confirm(t(`settings.localLlm.confirm.${action}`, { target }))) {
      return;
    }
    const key = `${action}:${target}`;
    setLocalLlmBusy(key);
    try {
      const result = await runLocalLlmAction(token, action, target);
      setLocalLlmMessage(result.message);
      await refreshLocalLlm();
    } catch (err) {
      setLocalLlmError((err as Error).message);
    } finally {
      setLocalLlmBusy(null);
    }
  }, [refreshLocalLlm, t, token]);

  const dirty = useMemo(() => {
    if (!settings) return false;
    return (
      (!settings.agent.model_locked && form.model !== settings.agent.model) ||
      (!settings.agent.provider_locked &&
        form.provider !== settings.agent.provider)
    );
  }, [form, settings]);

  const save = async () => {
    if (!settings || !dirty || saving) return;
    const update = {
      ...(settings.agent.model_locked || form.model === settings.agent.model
        ? {}
        : { model: form.model }),
      ...(settings.agent.provider_locked ||
      form.provider === settings.agent.provider
        ? {}
        : { provider: form.provider }),
    };
    if (Object.keys(update).length === 0) return;
    setSaving(true);
    try {
      const payload = await updateSettings(token, update);
      applyPayload(payload);
      onModelNameChange(payload.agent.model || null);
      setError(null);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="min-h-0 flex-1 overflow-y-auto bg-background">
      <main className="mx-auto w-full max-w-[1000px] px-6 py-6">
        <button
          type="button"
          onClick={onBackToChat}
          className="mb-4 inline-flex items-center gap-1.5 text-xs font-medium text-muted-foreground hover:text-foreground"
        >
          <ChevronLeft className="h-3.5 w-3.5" />
          {t("settings.backToChat")}
        </button>

        <h1 className="mb-2 text-base font-semibold tracking-tight">{t("settings.title")}</h1>
        <p className="mb-6 max-w-[38rem] text-sm text-muted-foreground">
          {t("settings.description")}
        </p>

        {loading ? (
          <div className="flex h-48 items-center justify-center text-sm text-muted-foreground">
            <Loader2 className="mr-2 h-4 w-4 animate-spin" />
            {t("settings.loading")}
          </div>
        ) : error ? (
          <SettingsGroup>
            <SettingsRow title={t("settings.loadErrorTitle")}>
              <span className="max-w-[520px] text-sm text-muted-foreground">{error}</span>
            </SettingsRow>
          </SettingsGroup>
        ) : settings ? (
          <SettingsSection
            form={form}
            setForm={setForm}
            settings={settings}
            dirty={dirty}
            saving={saving}
            onSave={save}
            theme={theme}
            onToggleTheme={onToggleTheme}
            reasoningVisibility={reasoningVisibility}
            onReasoningVisibilityChange={onReasoningVisibilityChange}
            chatFontSize={chatFontSize}
            chatFontValue={chatFontValue}
            onDecreaseChatFont={onDecreaseChatFont}
            onIncreaseChatFont={onIncreaseChatFont}
            onLogout={onLogout}
            onRestart={onRestart}
            localLlm={localLlm}
            localLlmError={localLlmError}
            localLlmBusy={localLlmBusy}
            localLlmMessage={localLlmMessage}
            onLocalLlmAction={runLocalAction}
          />
        ) : null}
      </main>
    </div>
  );
}

function SettingsSection({
  form,
  setForm,
  settings,
  dirty,
  saving,
  onSave,
  theme,
  onToggleTheme,
  reasoningVisibility,
  onReasoningVisibilityChange,
  chatFontSize,
  chatFontValue,
  onDecreaseChatFont,
  onIncreaseChatFont,
  onLogout,
  onRestart,
  localLlm,
  localLlmError,
  localLlmBusy,
  localLlmMessage,
  onLocalLlmAction,
}: {
  form: {
    model: string;
    provider: string;
  };
  setForm: React.Dispatch<React.SetStateAction<{
    model: string;
    provider: string;
  }>>;
  settings: SettingsPayload;
  dirty: boolean;
  saving: boolean;
  onSave: () => void;
  theme: "light" | "dark";
  onToggleTheme: () => void;
  reasoningVisibility: ReasoningVisibility;
  onReasoningVisibilityChange: (next: ReasoningVisibility) => void;
  chatFontSize: "sm" | "md" | "lg";
  chatFontValue: number;
  onDecreaseChatFont: () => void;
  onIncreaseChatFont: () => void;
  onLogout?: () => void;
  onRestart?: () => void;
  localLlm: LocalLlmStatusPayload | null;
  localLlmError: string | null;
  localLlmBusy: string | null;
  localLlmMessage: string | null;
  onLocalLlmAction: (action: string, target: string) => void;
}) {
  const { t } = useTranslation();
  const canDecreaseFont = chatFontSize !== "sm";
  const canIncreaseFont = chatFontSize !== "lg";
  const modelLocked = settings.agent.model_locked === true;
  const providerLocked = settings.agent.provider_locked === true;
  return (
    <div className="space-y-7">
      <section>
        <h2 className="mb-2 px-2 text-xs font-medium text-muted-foreground">{t("settings.sections.assistant")}</h2>
        <SettingsGroup>
          <SettingsRow title={t("settings.rows.defaultProvider")}>
            <select
              value={form.provider}
              onChange={(event) => setForm((prev) => ({ ...prev, provider: event.target.value }))}
              disabled={providerLocked}
              className={cn(
                "h-8 w-[210px] rounded-md border border-input bg-background px-2 text-sm",
                "outline-none transition-colors hover:bg-accent focus-visible:ring-2 focus-visible:ring-ring",
              )}
            >
              {settings.providers.map((provider) => (
                <option key={provider.name} value={provider.name}>
                  {provider.label}
                </option>
              ))}
            </select>
          </SettingsRow>

          <SettingsRow title={t("settings.rows.defaultModel")}>
            <Input
              value={form.model}
              onChange={(event) => setForm((prev) => ({ ...prev, model: event.target.value }))}
              disabled={modelLocked}
              className="h-8 w-[280px]"
            />
          </SettingsRow>

          {providerLocked || modelLocked ? (
            <SettingsRow title={t("settings.rows.managedByRuntime")}>
              <span className="max-w-[280px] text-sm text-muted-foreground">
                {t("settings.managedByRuntimeBody")}
              </span>
            </SettingsRow>
          ) : null}

          {(dirty || saving || settings.requires_restart) ? (
            <SettingsFooter
              dirty={dirty}
              saving={saving}
              saved={settings.requires_restart && !dirty}
              onSave={onSave}
            />
          ) : null}
        </SettingsGroup>
      </section>

      <LocalLlmSection
        payload={localLlm}
        error={localLlmError}
        busy={localLlmBusy}
        message={localLlmMessage}
        onAction={onLocalLlmAction}
      />

      <section>
        <h2 className="mb-2 px-2 text-xs font-medium text-muted-foreground">{t("settings.sections.themes")}</h2>
        <SettingsGroup>
          <SettingsRow title={t("settings.rows.theme")}>
            <Button
              type="button"
              size="sm"
              variant="outline"
              onClick={onToggleTheme}
              className="h-8 min-w-[7.5rem] justify-between px-3"
              aria-label={t("settings.toggleTheme")}
            >
              <span>{theme === "dark" ? t("settings.theme.dark") : t("settings.theme.light")}</span>
              {theme === "dark" ? (
                <Moon className="h-3.5 w-3.5" aria-hidden />
              ) : (
                <Sun className="h-3.5 w-3.5" aria-hidden />
              )}
            </Button>
          </SettingsRow>

          <SettingsRow title={t("settings.rows.chatFontSize")}>
            <div className="flex items-center gap-2">
              <Button
                type="button"
                size="icon"
                variant="outline"
                onClick={onDecreaseChatFont}
                disabled={!canDecreaseFont}
                aria-label={t("settings.decreaseChatFontSize")}
                className="h-8 w-8"
              >
                <Minus className="h-3.5 w-3.5" aria-hidden />
              </Button>
              <div className="flex h-8 min-w-[4.5rem] items-center justify-center rounded-md border border-input bg-background px-3 text-sm font-medium tabular-nums">
                {chatFontValue}
              </div>
              <Button
                type="button"
                size="icon"
                variant="outline"
                onClick={onIncreaseChatFont}
                disabled={!canIncreaseFont}
                aria-label={t("settings.increaseChatFontSize")}
                className="h-8 w-8"
              >
                <Plus className="h-3.5 w-3.5" aria-hidden />
              </Button>
            </div>
          </SettingsRow>
        </SettingsGroup>
      </section>

      <section>
        <h2 className="mb-2 px-2 text-xs font-medium text-muted-foreground">{t("settings.sections.interface")}</h2>
        <SettingsGroup>
          <SettingsRow title={t("settings.rows.language")}>
            <LanguageSwitcher />
          </SettingsRow>

          <SettingsRow title={t("settings.rows.reasoningVisibility")}>
            <select
              value={reasoningVisibility}
              onChange={(event) => onReasoningVisibilityChange(event.target.value as ReasoningVisibility)}
              className={cn(
                "h-8 w-[210px] rounded-md border border-input bg-background px-2 text-sm",
                "outline-none transition-colors hover:bg-accent focus-visible:ring-2 focus-visible:ring-ring",
              )}
            >
              <option value="off">{t("settings.reasoningVisibility.off")}</option>
              <option value="status_only">{t("settings.reasoningVisibility.statusOnly")}</option>
              <option value="summary">{t("settings.reasoningVisibility.summary")}</option>
              <option value="debug_trace">{t("settings.reasoningVisibility.debugTrace")}</option>
            </select>
          </SettingsRow>
        </SettingsGroup>
      </section>

      {onRestart && (
        <section>
          <h2 className="mb-2 px-2 text-xs font-medium text-muted-foreground">{t("app.system.section")}</h2>
          <SettingsGroup>
            <SettingsRow title={t("app.system.restartHint")}>
              <Button size="sm" variant="outline" onClick={onRestart}>
                {t("app.system.restart")}
              </Button>
            </SettingsRow>
          </SettingsGroup>
        </section>
      )}

      {onLogout && (
        <section>
          <h2 className="mb-2 px-2 text-xs font-medium text-muted-foreground">{t("app.account.section")}</h2>
          <SettingsGroup>
            <SettingsRow title={t("app.account.logoutHint")}>
              <Button size="sm" variant="outline" onClick={onLogout}>
                {t("app.account.logout")}
              </Button>
            </SettingsRow>
          </SettingsGroup>
        </section>
      )}
    </div>
  );
}

function LocalLlmSection({
  payload,
  error,
  busy,
  message,
  onAction,
}: {
  payload: LocalLlmStatusPayload | null;
  error: string | null;
  busy: string | null;
  message: string | null;
  onAction: (action: string, target: string) => void;
}) {
  const { t } = useTranslation();
  const [selectedName, setSelectedName] = useState<string>(payload?.default_target ?? "qwen36");

  useEffect(() => {
    if (!payload?.targets.length) return;
    const selectedExists = payload.targets.some((target) => target.name === selectedName);
    if (!selectedExists) {
      setSelectedName(payload.default_target || payload.targets[0].name);
    }
  }, [payload, selectedName]);

  const selectedTarget = payload?.targets.find((target) => target.name === selectedName)
    ?? payload?.targets.find((target) => target.name === payload.default_target)
    ?? payload?.targets[0]
    ?? null;

  return (
    <section>
      <h2 className="mb-2 px-2 text-xs font-medium text-muted-foreground">{t("settings.sections.localLlm")}</h2>
      <SettingsGroup>
        <div className="space-y-4 px-3 py-3.5">
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <div className="min-w-0">
              <div className="text-sm font-medium leading-5">{t("settings.localLlm.modelSelector")}</div>
              <div className="mt-1 truncate text-xs text-muted-foreground">
                {payload ? t("settings.localLlm.defaultRoute", { target: payload.default_target }) : t("settings.localLlm.loading")}
              </div>
            </div>
            <select
              aria-label={t("settings.localLlm.modelSelectAria")}
              value={selectedTarget?.name ?? ""}
              onChange={(event) => setSelectedName(event.target.value)}
              disabled={!payload?.targets.length}
              className={cn(
                "h-9 w-full rounded-md border border-input bg-background px-3 text-sm sm:w-[280px]",
                "outline-none transition-colors hover:bg-accent focus-visible:ring-2 focus-visible:ring-ring",
              )}
            >
              {payload?.targets.map((target) => (
                <option key={target.name} value={target.name}>
                  {target.label} · {target.is_default ? t("settings.localLlm.defaultBadge") : target.running ? t("settings.localLlm.running") : t("settings.localLlm.stopped")}
                </option>
              )) ?? (
                <option value="">{t("settings.localLlm.loading")}</option>
              )}
            </select>
          </div>

          {selectedTarget ? (
            <LocalLlmTargetPanel
              target={selectedTarget}
              defaultModel={payload?.default_model ?? ""}
              busy={busy}
              onAction={onAction}
            />
          ) : null}
        </div>
        {error ? (
          <SettingsRow title={t("settings.localLlm.statusUnavailable")}>
            <span className="max-w-[360px] text-sm text-muted-foreground">{error}</span>
          </SettingsRow>
        ) : null}
        {message ? (
          <SettingsRow title={t("settings.localLlm.lastAction")}>
            <span className="max-w-[360px] text-sm text-muted-foreground">{message}</span>
          </SettingsRow>
        ) : null}
      </SettingsGroup>
    </section>
  );
}

function LocalLlmTargetPanel({
  target,
  defaultModel,
  busy,
  onAction,
}: {
  target: LocalLlmTargetStatus;
  defaultModel: string;
  busy: string | null;
  onAction: (action: string, target: string) => void;
}) {
  const { t } = useTranslation();
  const targetBusy = (action: string) => busy === `${action}:${target.name}`;
  const state = getLocalLlmState(target, busy);
  const stateLabel = t(`settings.localLlm.state.${state}`);
  const visionState = getLocalLlmVisionState(target);
  const visionLabel = t(`settings.localLlm.vision.${visionState}`);
  const visionMessage = target.hybrid_vision_target
    ? (target.hybrid_vision_check_message || "")
    : (target.vision_check_message || "");
  const toggleAction = target.running ? "stop" : "start";
  const toggleBusy = targetBusy("start") || targetBusy("stop");
  const toggleTone = state === "starting" ? "starting" : target.running ? "stopped" : "running";
  const toggleLabel = t(`settings.localLlm.actions.${toggleAction}`);

  return (
    <TooltipProvider delayDuration={0}>
      <div className="rounded-lg border border-border/50 bg-background/45 p-3">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              <div className="truncate text-base font-semibold leading-6">{target.label}</div>
              {target.is_default ? (
                <StatusIcon label={t("settings.localLlm.defaultBadge")} tone="default" icon={<Star className="size-3.5 fill-current" />} />
              ) : null}
            </div>
            <div className="mt-1 truncate text-xs text-muted-foreground" title={target.model}>
              {target.model}
            </div>
          </div>
          <div className="flex items-center gap-2">
            <StatusIcon
              label={stateLabel}
              tone={state}
              icon={state === "starting" ? <Loader2 className="size-3.5 animate-spin" /> : state === "running" ? <CheckCircle2 className="size-3.5" /> : <Circle className="size-3.5 fill-current" />}
            />
            <StatusIcon
              label={target.endpoint_ok ? t("settings.localLlm.endpointOk") : t("settings.localLlm.endpointUnavailable")}
              tone={target.endpoint_ok ? "running" : "stopped"}
              icon={<Zap className="size-3.5" />}
            />
            <StatusIcon
              label={visionLabel}
              tone={visionState === "supported" || visionState === "hybrid" ? "running" : visionState === "unknown" ? "checking" : "stopped"}
              icon={<Activity className="size-3.5" />}
            />
          </div>
        </div>

        <div className="mt-3 grid gap-2 text-xs text-muted-foreground sm:grid-cols-2">
          <LocalLlmDetail label={t("settings.localLlm.details.runtime")} value={target.runtime} />
          <LocalLlmDetail label={t("settings.localLlm.details.endpoint")} value={target.api_base} />
          <LocalLlmDetail label={t("settings.localLlm.details.launchd")} value={target.launchd_label} />
          <LocalLlmDetail label={t("settings.localLlm.details.activeModel")} value={target.is_default ? defaultModel : target.model} />
          <LocalLlmDetail
            label={t("settings.localLlm.details.management")}
            value={t(`settings.localLlm.management.${target.management_mode === "broker" ? "broker" : target.management_mode === "on_demand" ? "on_demand" : "manual"}`)}
          />
          {target.management_mode === "broker" ? (
            <LocalLlmDetail
              label={t("settings.localLlm.details.holders")}
              value={t("settings.localLlm.management.brokerSummary", { count: target.holder_count ?? 0 })}
              helper={(target.holders ?? []).join(", ")}
            />
          ) : null}
        </div>

        {visionMessage ? (
          <p className="mt-3 text-xs text-muted-foreground">{visionMessage}</p>
        ) : null}

        <div className="mt-3 flex flex-wrap items-center justify-between gap-3">
          <Button
            type="button"
            size="sm"
            variant={target.is_default ? "secondary" : "outline"}
            onClick={() => onAction("use", target.name)}
            disabled={target.is_default || targetBusy("use")}
            className="gap-2"
          >
            {targetBusy("use") ? <Loader2 className="size-4 animate-spin" aria-hidden /> : <Star className={cn("size-4", target.is_default ? "fill-current" : undefined)} aria-hidden />}
            {target.is_default ? t("settings.localLlm.currentDefault") : t("settings.localLlm.actions.use")}
          </Button>
          <div className="flex items-center gap-2">
            <LocalLlmIconButton label={toggleLabel} onClick={() => onAction(toggleAction, target.name)} disabled={toggleBusy} busy={toggleBusy} tone={toggleTone}>
              {target.running ? <Square className="size-4" aria-hidden /> : <Play className="size-4" aria-hidden />}
            </LocalLlmIconButton>
            <LocalLlmIconButton label={t("settings.localLlm.actions.restart")} onClick={() => onAction("restart", target.name)} disabled={targetBusy("restart")} busy={targetBusy("restart")} tone="starting">
              <RotateCw className="size-4" aria-hidden />
            </LocalLlmIconButton>
            <LocalLlmIconButton label={t("settings.localLlm.actions.smoke")} onClick={() => onAction("smoke", target.name)} disabled={targetBusy("smoke")} busy={targetBusy("smoke")} tone="checking">
              <Activity className="size-4" aria-hidden />
            </LocalLlmIconButton>
          </div>
        </div>
      </div>
    </TooltipProvider>
  );
}

function getLocalLlmState(target: LocalLlmTargetStatus, busy: string | null): "running" | "starting" | "stopped" {
  const isMutating = ["start", "restart", "use"].some((action) => busy === `${action}:${target.name}`);
  if (isMutating) return "starting";
  return target.running ? "running" : "stopped";
}

function getLocalLlmVisionState(target: LocalLlmTargetStatus): "supported" | "unsupported" | "unknown" | "hybrid" | "hybrid_unavailable" {
  if (target.supports_vision) return "supported";
  if (target.hybrid_vision_target) return target.hybrid_vision_ready ? "hybrid" : "hybrid_unavailable";
  if (target.vision_check_ok) return "unsupported";
  return "unknown";
}

function StatusIcon({
  label,
  tone,
  icon,
}: {
  label: string;
  tone: "running" | "starting" | "stopped" | "checking" | "default";
  icon: React.ReactNode;
}) {
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <span
          aria-label={label}
          className={cn(
            "inline-flex size-8 items-center justify-center rounded-full border",
            tone === "running" ? "border-emerald-500/35 bg-emerald-500/10 text-emerald-400" : undefined,
            tone === "starting" ? "border-amber-500/35 bg-amber-500/10 text-amber-300" : undefined,
            tone === "stopped" ? "border-red-500/35 bg-red-500/10 text-red-400" : undefined,
            tone === "checking" ? "border-sky-500/35 bg-sky-500/10 text-sky-300" : undefined,
            tone === "default" ? "border-yellow-500/35 bg-yellow-500/10 text-yellow-300" : undefined,
          )}
        >
          {icon}
        </span>
      </TooltipTrigger>
      <TooltipContent side="bottom">{label}</TooltipContent>
    </Tooltip>
  );
}

function LocalLlmDetail({ label, value, helper }: { label: string; value: string; helper?: string }) {
  return (
    <div className="min-w-0 rounded-md border border-border/40 bg-card/40 px-2.5 py-2">
      <div className="text-[11px] font-medium uppercase text-muted-foreground/75">{label}</div>
      <div className="mt-1 truncate font-mono text-[12px] text-foreground/80" title={value}>{value}</div>
      {helper ? <div className="mt-1 break-words text-[11px] text-muted-foreground/80">{helper}</div> : null}
    </div>
  );
}

function LocalLlmIconButton({
  label,
  onClick,
  disabled,
  busy,
  tone,
  children,
}: {
  label: string;
  onClick: () => void;
  disabled: boolean;
  busy: boolean;
  tone: "running" | "starting" | "stopped" | "checking";
  children: React.ReactNode;
}) {
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <Button
          type="button"
          size="icon"
          variant="outline"
          aria-label={label}
          onClick={onClick}
          disabled={disabled}
          className={cn(
            "h-9 w-9 rounded-full",
            tone === "running" ? "text-emerald-400 hover:text-emerald-300" : undefined,
            tone === "starting" ? "text-amber-300 hover:text-amber-200" : undefined,
            tone === "stopped" ? "text-red-400 hover:text-red-300" : undefined,
            tone === "checking" ? "text-sky-300 hover:text-sky-200" : undefined,
          )}
        >
          {busy ? <Loader2 className="size-4 animate-spin" aria-hidden /> : children}
        </Button>
      </TooltipTrigger>
      <TooltipContent side="bottom">{label}</TooltipContent>
    </Tooltip>
  );
}

function SettingsGroup({ children }: { children: React.ReactNode }) {
  return (
    <div className="overflow-hidden rounded-xl border border-border/60 bg-card/80">
      <div className="divide-y divide-border/50">{children}</div>
    </div>
  );
}

function SettingsRow({
  title,
  children,
}: {
  title: string;
  children?: React.ReactNode;
}) {
  return (
    <div className="flex min-h-[52px] flex-col gap-3 px-3 py-2.5 sm:flex-row sm:items-center sm:justify-between">
      <div className="min-w-0">
        <div className="text-sm font-medium leading-5">{title}</div>
      </div>
      {children ? <div className="shrink-0 sm:ml-6">{children}</div> : null}
    </div>
  );
}

function SettingsFooter({
  dirty,
  saving,
  saved,
  onSave,
}: {
  dirty: boolean;
  saving: boolean;
  saved: boolean;
  onSave: () => void;
}) {
  const { t } = useTranslation();

  return (
    <div className="flex min-h-[52px] items-center justify-between gap-4 px-3 py-2.5">
      <div className="text-sm text-muted-foreground">
        {saved ? t("settings.footer.saved") : t("settings.footer.unsaved")}
      </div>
      <Button size="sm" variant="outline" onClick={onSave} disabled={!dirty || saving}>
        {saving ? t("settings.footer.saving") : t("settings.footer.save")}
      </Button>
    </div>
  );
}
