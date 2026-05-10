import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { AskUserPrompt } from "@/components/thread/AskUserPrompt";
import { setAppLanguage } from "@/i18n";

describe("AskUserPrompt i18n", () => {
  beforeEach(async () => {
    await setAppLanguage("ko");
  });

  it("renders localized approval copy and custom answer controls in Korean", () => {
    render(
      <AskUserPrompt
        question="일정을 생성할까요?"
        buttons={[["승인", "취소"]]}
        onAnswer={vi.fn()}
      />,
    );

    expect(screen.getByRole("group", { name: "승인 요청" })).toBeInTheDocument();
    expect(screen.getByText("승인 대기")).toBeInTheDocument();
    expect(screen.getByText("검토한 뒤 어떻게 진행할지 선택하세요.")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "직접 입력..." }));

    expect(screen.getByPlaceholderText("직접 답변을 입력하세요...")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "보내기" })).toBeInTheDocument();
  });
});