import type { UIMessage } from "@/lib/types";

const STATUS_FOOTER_BLOCK_RE = /\n{2,}Status:\s[\s\S]*$/;

export function normalizeAssistantDuplicateText(value: string): string {
  return stripAssistantStatusFooter(value).replace(/\s+/g, " ").trim();
}

export function stripAssistantStatusFooter(value: string): string {
  return value.replace(STATUS_FOOTER_BLOCK_RE, "").trimEnd();
}

export function hasAssistantStatusFooter(value: string): boolean {
  return STATUS_FOOTER_BLOCK_RE.test(value);
}

export function areEquivalentAssistantMessages(
  left: Pick<UIMessage, "role" | "content" | "buttons" | "media">,
  right: Pick<UIMessage, "role" | "content" | "buttons" | "media">,
): boolean {
  return (
    left.role === "assistant"
    && right.role === "assistant"
    && normalizeAssistantDuplicateText(left.content) === normalizeAssistantDuplicateText(right.content)
    && JSON.stringify(left.buttons ?? []) === JSON.stringify(right.buttons ?? [])
    && JSON.stringify(left.media ?? []) === JSON.stringify(right.media ?? [])
  );
}

export function pickPreferredAssistantMessage<T extends Pick<UIMessage, "role" | "content" | "buttons" | "media">>(
  left: T,
  right: T,
): T {
  return assistantMessageRichness(right) > assistantMessageRichness(left) ? right : left;
}

function assistantMessageRichness(message: Pick<UIMessage, "content" | "buttons" | "media">): number {
  let score = 0;
  if (hasAssistantStatusFooter(message.content)) score += 4;
  if (Array.isArray(message.buttons) && message.buttons.some((row) => row.length > 0)) score += 2;
  if (Array.isArray(message.media) && message.media.length > 0) score += 2;
  score += message.content.length;
  return score;
}
