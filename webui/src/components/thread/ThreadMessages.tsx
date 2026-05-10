import { MessageBubble } from "@/components/MessageBubble";
import type { ReasoningVisibility, UIMessage } from "@/lib/types";

interface ThreadMessagesProps {
  messages: UIMessage[];
  reasoningVisibility?: ReasoningVisibility;
  onApprovalResponse?: (messageId: string, decision: "yes" | "no") => void | Promise<void>;
}

export function ThreadMessages({
  messages,
  reasoningVisibility = "summary",
  onApprovalResponse,
}: ThreadMessagesProps) {
  return (
    <div className="flex w-full flex-col gap-5">
      {messages.map((message) => (
        <MessageBubble
          key={message.id}
          message={message}
          reasoningVisibility={reasoningVisibility}
          onApprovalResponse={onApprovalResponse}
        />
      ))}
    </div>
  );
}
