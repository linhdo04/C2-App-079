import type { ChatMessage } from "@/types/agent";
import { Leaf } from "lucide-react";
import MarkdownMessage from "./markdown-message";

export default function MessageRow({ message }: { message: ChatMessage }) {
  const isUser = message.role === "user";

  if (isUser) {
    return (
      <div className="flex justify-end">
        <div className="max-w-[88%] rounded-2xl border border-primary/15 bg-primary/10 px-4 py-2.5 text-sm leading-6 text-foreground">
          <p className="whitespace-pre-wrap">{message.message}</p>
        </div>
      </div>
    );
  }

  return (
    <article className="group flex items-start gap-3">
      <span className="mt-0.5 grid size-8 shrink-0 place-items-center rounded-xl bg-primary text-primary-foreground shadow-[0_8px_24px_rgb(185_243_74/0.12)]">
        <Leaf className="size-4" />
      </span>
      <div className="min-w-0 flex-1">
        <p className="mb-2 text-sm font-bold text-foreground">AeroField</p>
        <MarkdownMessage content={message.message} />
      </div>
    </article>
  );
}
