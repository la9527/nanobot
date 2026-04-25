import { MessageBubble } from "@/components/MessageBubble";
import type { UIMessage } from "@/lib/types";

interface ThreadMessagesProps {
  messages: UIMessage[];
  onApprovalResponse?: (messageId: string, decision: "yes" | "no") => void | Promise<void>;
}

export function ThreadMessages({ messages, onApprovalResponse }: ThreadMessagesProps) {
  return (
    <div className="flex w-full flex-col gap-5">
      {messages.map((message) => (
        <MessageBubble key={message.id} message={message} onApprovalResponse={onApprovalResponse} />
      ))}
    </div>
  );
}
