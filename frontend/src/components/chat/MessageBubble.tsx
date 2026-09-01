import { ArtifactBlock, type Artifact } from "@/components/blocks/ArtifactBlock";
import { cn } from "@/lib/cn";

export interface BubbleMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  streaming?: boolean;
  artifacts?: Artifact[];
}

export function MessageBubble({ message }: { message: BubbleMessage }) {
  const isUser = message.role === "user";
  return (
    <div className={cn("flex flex-col gap-2", isUser ? "items-end" : "items-start")}>
      <div
        className={cn(
          "max-w-[80%] whitespace-pre-wrap rounded-lg px-4 py-2 text-sm",
          isUser ? "bg-primary/15 text-foreground" : "glass text-foreground",
        )}
        data-role={message.role}
      >
        {message.content}
        {message.streaming && (
          <span className="ml-0.5 inline-block h-4 w-1.5 animate-pulse bg-primary align-middle" />
        )}
      </div>
      {message.artifacts && message.artifacts.length > 0 && (
        <div className="w-full max-w-[92%] space-y-2">
          {message.artifacts.map((a) => (
            <ArtifactBlock key={a.id} artifact={a} />
          ))}
        </div>
      )}
    </div>
  );
}
