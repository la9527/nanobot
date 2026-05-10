import { describe, expect, it } from "vitest";

import { setAppLanguage } from "@/i18n";
import { getActionResult } from "@/lib/sessionMetadata";
import type { ChatSummary } from "@/lib/types";

describe("sessionMetadata action result localization", () => {
  it("localizes legacy calendar rejection summaries for Korean UI", async () => {
    await setAppLanguage("ko");

    const session = {
      key: "websocket:calendar-demo",
      channel: "websocket",
      chatId: "calendar-demo",
      createdAt: null,
      updatedAt: null,
      preview: "",
      metadata: {
        action_result: {
          action_id: "calendar-create-denied-1",
          domain: "calendar",
          action: "create_event",
          status: "rejected",
          title: "Calendar create cancelled",
          summary: "The pending calendar create request was cancelled.",
          next_step: "Review the proposed event and request approval again when ready.",
          error: {
            code: "approval_rejected",
            message: "The pending calendar create request was cancelled.",
          },
          details: {
            preview: {
              title: "i18n 확인",
              start_at: "2026-05-06T21:00:00+09:00",
              end_at: "2026-05-06T21:30:00+09:00",
            },
          },
        },
      },
    } satisfies ChatSummary;

    const result = getActionResult(session);

    expect(result?.title).toBe("일정 생성 취소됨");
    expect(result?.summary).toBe("보류 중이던 일정 생성 요청을 취소했습니다.");
    expect(result?.nextStep).toBe("필요하면 제안된 일정을 검토한 뒤 다시 승인 요청을 올리세요.");
    expect(result?.errorMessage).toBe("보류 중이던 일정 요청을 취소했습니다.");
  });
});