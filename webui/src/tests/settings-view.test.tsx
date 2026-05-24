import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { SettingsView } from "@/components/settings/SettingsView";
import { fetchLocalLlmStatus, fetchSettings, runLocalLlmAction } from "@/lib/api";

vi.mock("@/providers/ClientProvider", () => ({
  useClient: () => ({ token: "tok" }),
}));

vi.mock("@/lib/api", () => ({
  fetchSettings: vi.fn(),
  updateSettings: vi.fn(),
  fetchLocalLlmStatus: vi.fn(),
  runLocalLlmAction: vi.fn(),
}));

describe("SettingsView local LLM settings", () => {
  beforeEach(() => {
    vi.mocked(fetchSettings).mockResolvedValue({
      agent: {
        model: "mlx-community/Qwen3.6-35B-A3B-4bit",
        configured_model: "${LOCAL_LLM_MODEL}",
        provider: "vllm",
        resolved_provider: "vllm",
        has_api_key: false,
        model_locked: true,
        provider_locked: true,
      },
      providers: [{ name: "vllm", label: "vLLM" }],
      runtime: { config_path: "/tmp/config.json" },
      requires_restart: false,
    });
    vi.mocked(fetchLocalLlmStatus).mockResolvedValue({
      default_target: "qwen36",
      default_model: "mlx-community/Qwen3.6-35B-A3B-4bit",
      default_api_base: "http://127.0.0.1:1246/v1",
      targets: [
        {
          name: "qwen36",
          label: "Qwen3.6",
          provider: "vllm",
          runtime: "mlx_vlm.server",
          model: "mlx-community/Qwen3.6-35B-A3B-4bit",
          api_base: "http://127.0.0.1:1246/v1",
          launchd_label: "com.nanobot.local-model-qwen36",
          running: true,
          endpoint_ok: true,
          supports_vision: false,
          vision_check_ok: true,
          vision_check_message: "Only 'text' content type is supported.",
          is_default: true,
        },
        {
          name: "lfm2",
          label: "LFM2",
          provider: "llama.cpp",
          runtime: "llama.cpp",
          model: "LiquidAI/LFM2-24B-A2B-GGUF:Q4_0",
          api_base: "http://127.0.0.1:1242/v1",
          launchd_label: "com.nanobot.local-model-lfm2",
          running: false,
          endpoint_ok: false,
          supports_vision: false,
          vision_check_ok: false,
          vision_check_message: "endpoint unavailable",
          is_default: false,
        },
      ],
    });
    vi.mocked(runLocalLlmAction).mockResolvedValue({
      ok: true,
      action: "start",
      target: "lfm2",
      message: "start lfm2 completed",
      requires_restart: false,
    });
  });

  it("shows selected qwen36 local LLM status in a compact control panel", async () => {
    render(
      <SettingsView
        theme="light"
        onToggleTheme={vi.fn()}
        onBackToChat={vi.fn()}
        reasoningVisibility="off"
        onReasoningVisibilityChange={vi.fn()}
        onModelNameChange={vi.fn()}
        chatFontSize="md"
        chatFontValue={15}
        onDecreaseChatFont={vi.fn()}
        onIncreaseChatFont={vi.fn()}
      />,
    );

    await waitFor(() => expect(fetchLocalLlmStatus).toHaveBeenCalledWith("tok"));
    expect(await screen.findByText("Local LLM")).toBeInTheDocument();
    expect(screen.getByLabelText("Select local LLM model")).toHaveValue("qwen36");
    expect(screen.getByText("Default local route: qwen36")).toBeInTheDocument();
    expect(screen.getByText("Qwen3.6")).toBeInTheDocument();
    expect(screen.getByLabelText("Running")).toBeInTheDocument();
    expect(screen.getByLabelText("Endpoint OK")).toBeInTheDocument();
    expect(screen.getByLabelText("Vision unsupported")).toBeInTheDocument();
    expect(screen.getByText("Only 'text' content type is supported.")).toBeInTheDocument();
    expect(screen.getByText("Current default")).toBeDisabled();
    expect(screen.getByRole("button", { name: "Stop" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Check response" })).toBeInTheDocument();
  });

  it("switches the local LLM panel through the model selector", async () => {
    const user = userEvent.setup();
    render(
      <SettingsView
        theme="light"
        onToggleTheme={vi.fn()}
        onBackToChat={vi.fn()}
        reasoningVisibility="off"
        onReasoningVisibilityChange={vi.fn()}
        onModelNameChange={vi.fn()}
        chatFontSize="md"
        chatFontValue={15}
        onDecreaseChatFont={vi.fn()}
        onIncreaseChatFont={vi.fn()}
      />,
    );

    await user.selectOptions(await screen.findByLabelText("Select local LLM model"), "lfm2");

    expect(screen.getByText("LFM2")).toBeInTheDocument();
    expect(screen.getByLabelText("Stopped")).toBeInTheDocument();
    expect(screen.getByLabelText("Endpoint unavailable")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Use as default" })).toBeEnabled();
    expect(screen.getByRole("button", { name: "Start" })).toBeInTheDocument();
  });

  it("shows a yellow starting state while a model start action is pending", async () => {
    const user = userEvent.setup();
    vi.mocked(runLocalLlmAction).mockReturnValue(new Promise(() => undefined));
    render(
      <SettingsView
        theme="light"
        onToggleTheme={vi.fn()}
        onBackToChat={vi.fn()}
        reasoningVisibility="off"
        onReasoningVisibilityChange={vi.fn()}
        onModelNameChange={vi.fn()}
        chatFontSize="md"
        chatFontValue={15}
        onDecreaseChatFont={vi.fn()}
        onIncreaseChatFont={vi.fn()}
      />,
    );

    await user.selectOptions(await screen.findByLabelText("Select local LLM model"), "lfm2");
    await user.click(screen.getByRole("button", { name: "Start" }));

    expect(screen.getByLabelText("Starting")).toBeInTheDocument();
  });
});
