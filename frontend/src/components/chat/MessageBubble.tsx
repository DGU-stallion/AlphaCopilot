import { cn } from "@/lib/cn";

export interface BubbleMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  streaming?: boolean;
}

export function MessageBubble({ message }: { message: BubbleMessage }) {
  const isUser = message.role === "user";
  return (
    <div className={cn("flex", isUser ? "justify-end" : "justify-start")}>
      <div
        className={cn(
          "max-w-[80%] whitespace-pre-wrap rounded-lg px-4 py-2 text-sm",
          isUser
            ? "bg-primary/15 text-foreground"
            : "glass text-foreground",
        )}
        data-role={message.role}
      >
        {message.content}
        {message.streaming && (
          <span className="ml-0.5 inline-block h-4 w-1.5 animate-pulse bg-primary align-middle" />
        )}
      </div>
    </div>
  );
}
