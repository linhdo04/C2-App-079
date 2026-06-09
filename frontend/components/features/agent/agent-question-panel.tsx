"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { ArrowUp, Bot, CloudSun, Lightbulb, LineChart, UserRound } from "lucide-react";
import { useForm } from "react-hook-form";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Field, FieldError, FieldLabel } from "@/components/ui/field";
import { Spinner } from "@/components/ui/spinner";
import { Textarea } from "@/components/ui/textarea";
import { agentQuestionSchema, type AgentQuestionFormValues } from "@/lib/validation";
import { cn } from "@/lib/utils";
import type { ChatMessage } from "@/types/agent";

type AgentQuestionPanelProps = {
  isLoading: boolean;
  messages: ChatMessage[];
  title: string | null;
  onSubmit: (values: AgentQuestionFormValues) => Promise<boolean>;
};

export function AgentQuestionPanel({ isLoading, messages, title, onSubmit }: AgentQuestionPanelProps) {
  const {
    formState: { errors },
    handleSubmit,
    register,
    reset,
    setValue,
  } = useForm<AgentQuestionFormValues>({
    defaultValues: {
      question: "",
    },
    resolver: zodResolver(agentQuestionSchema),
  });

  async function submit(values: AgentQuestionFormValues) {
    if (await onSubmit(values)) {
      reset();
    }
  }

  return (
    <section className="min-w-0">
      <Card className="flex min-h-[680px] flex-col overflow-hidden">
        <CardHeader className="border-b border-border/70 pb-5">
          <div className="flex items-start gap-4">
            <span className="grid size-11 shrink-0 place-items-center rounded-xl bg-primary text-primary-foreground">
              <Bot className="size-5" />
            </span>
            <div className="min-w-0">
              <p className="eyebrow text-primary">Agricultural intelligence</p>
              <CardTitle className="mt-1 truncate text-xl sm:text-2xl">{title ?? "Cuộc trò chuyện mới"}</CardTitle>
              <p className="mt-1 text-sm leading-6 text-muted-foreground">
                Hỏi tiếp trong cùng cuộc trò chuyện để giữ lại toàn bộ lịch sử.
              </p>
            </div>
          </div>
        </CardHeader>

        <CardContent className="flex min-h-0 flex-1 flex-col pt-5 sm:pt-6">
          <div
            className="min-h-0 flex-1 space-y-4 overflow-y-auto pr-1"
            aria-live="polite"
          >
            {messages.length === 0 && !isLoading ? (
              <EmptyConversation onSelect={(text) => setValue("question", text, { shouldValidate: true })} />
            ) : (
              messages.map((message) => (
                <MessageBubble
                  key={message.id}
                  message={message}
                />
              ))
            )}

            {isLoading && (
              <div className="flex items-start gap-3">
                <span className="grid size-9 shrink-0 place-items-center rounded-full bg-primary text-primary-foreground">
                  <Bot className="size-4" />
                </span>
                <div className="rounded-2xl rounded-tl-sm border border-border bg-background/60 px-4 py-3">
                  <p className="flex items-center gap-2 text-sm text-muted-foreground">
                    <Spinner />
                    Đang phân tích dữ liệu...
                  </p>
                </div>
              </div>
            )}
          </div>

          <form
            className="mt-5 border-t border-border/70 pt-5"
            onSubmit={handleSubmit(submit)}
            noValidate
          >
            <Field>
              <FieldLabel htmlFor="question">Tin nhắn</FieldLabel>
              <Textarea
                id="question"
                {...register("question")}
                className="min-h-24"
                placeholder="Nhập câu hỏi về thời tiết, mùa vụ hoặc dữ liệu vận hành..."
                aria-invalid={errors.question !== undefined}
                aria-describedby={errors.question !== undefined ? "question-error" : undefined}
                disabled={isLoading}
              />
              {errors.question !== undefined && (
                <FieldError
                  id="question-error"
                  role="alert"
                >
                  {errors.question.message}
                </FieldError>
              )}
            </Field>
            <div className="mt-3 flex justify-end">
              <Button
                className="w-full sm:w-fit"
                type="submit"
                disabled={isLoading}
              >
                {isLoading ? <Spinner data-icon="inline-start" /> : <ArrowUp />}
                {isLoading ? "Đang trả lời..." : "Gửi tin nhắn"}
              </Button>
            </div>
          </form>
        </CardContent>
      </Card>
    </section>
  );
}

function MessageBubble({ message }: { message: ChatMessage }) {
  const isUser = message.role === "user";

  return (
    <div className={cn("flex items-start gap-3", isUser && "flex-row-reverse")}>
      <span
        className={cn(
          "grid size-9 shrink-0 place-items-center rounded-full",
          isUser ? "bg-secondary text-secondary-foreground" : "bg-primary text-primary-foreground",
        )}
      >
        {isUser ? <UserRound className="size-4" /> : <Bot className="size-4" />}
      </span>
      <div
        className={cn(
          "max-w-[86%] rounded-2xl border px-4 py-3 sm:max-w-[78%]",
          isUser ? "rounded-tr-sm border-primary/20 bg-primary/10" : "rounded-tl-sm border-border bg-background/60",
        )}
      >
        <p className="whitespace-pre-wrap text-sm leading-6 text-foreground">{message.message}</p>
      </div>
    </div>
  );
}

function EmptyConversation({ onSelect }: { onSelect: (text: string) => void }) {
  return (
    <div className="flex min-h-80 flex-col items-center justify-center text-center">
      <span className="grid size-12 place-items-center rounded-full bg-primary/10 text-primary">
        <Lightbulb className="size-5" />
      </span>
      <p className="mt-4 text-sm font-bold">Bắt đầu một phân tích mới</p>
      <p className="mt-1 max-w-md text-xs leading-5 text-muted-foreground">
        Cuộc trò chuyện sẽ tự động được đặt tên theo câu hỏi đầu tiên.
      </p>
      <div className="mt-5 grid w-full max-w-xl gap-2 sm:grid-cols-2">
        <Suggestion
          icon={CloudSun}
          text="Thời tiết tuần này ảnh hưởng thế nào đến lịch canh tác?"
          onSelect={onSelect}
        />
        <Suggestion
          icon={LineChart}
          text="Phân tích xu hướng thị trường cho vụ mùa hiện tại."
          onSelect={onSelect}
        />
      </div>
    </div>
  );
}

type SuggestionProps = {
  icon: typeof CloudSun;
  text: string;
  onSelect: (text: string) => void;
};

function Suggestion({ icon: Icon, onSelect, text }: SuggestionProps) {
  return (
    <button
      className="flex min-h-20 items-start gap-3 rounded-xl border border-border/70 bg-card/50 p-3 text-left text-xs leading-5 text-muted-foreground transition-colors hover:border-primary/30 hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring/50 focus-visible:outline-none"
      type="button"
      onClick={() => onSelect(text)}
    >
      <Icon className="mt-0.5 size-4 shrink-0 text-primary" />
      {text}
    </button>
  );
}
