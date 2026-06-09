"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { ArrowUp, Bot, CloudSun, Leaf, LineChart, Search, Sparkles } from "lucide-react";
import { type FormEvent, type KeyboardEvent, useEffect, useRef, useState } from "react";
import { useForm } from "react-hook-form";
import { FieldError } from "@/components/ui/field";
import { Spinner } from "@/components/ui/spinner";
import { agentQuestionSchema, type AgentQuestionFormValues } from "@/lib/validation";
import { cn } from "@/lib/utils";
import type { ChatMessage } from "@/types/agent";

type AgentQuestionPanelProps = {
  isLoading: boolean;
  messages: ChatMessage[];
  streamingStatus?: string;
  title: string | null;
  onSubmit: (values: AgentQuestionFormValues) => Promise<boolean>;
};

export function AgentQuestionPanel({
  isLoading,
  messages,
  streamingStatus = "",
  title,
  onSubmit,
}: AgentQuestionPanelProps) {
  const {
    formState: { errors },
    handleSubmit,
    register,
    reset,
    setValue,
  } = useForm<AgentQuestionFormValues>({
    defaultValues: { question: "" },
    resolver: zodResolver(agentQuestionSchema),
  });
  const conversationRef = useRef<HTMLDivElement>(null);
  const [composerVersion, setComposerVersion] = useState(0);
  const questionField = register("question");

  useEffect(() => {
    const conversation = conversationRef.current;
    if (conversation !== null) {
      conversation.scrollTo({
        top: conversation.scrollHeight,
        behavior: messages.length > 1 ? "smooth" : "auto",
      });
    }
  }, [messages, streamingStatus]);

  async function submit(values: AgentQuestionFormValues) {
    if (await onSubmit(values)) {
      reset();
      setComposerVersion((version) => version + 1);
    }
  }

  function handleComposerKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key !== "Enter" || event.shiftKey || event.nativeEvent.isComposing) {
      return;
    }
    event.preventDefault();
    void handleSubmit(submit)();
  }

  function handleComposerInput(event: FormEvent<HTMLTextAreaElement>) {
    const composer = event.currentTarget;
    composer.style.height = "auto";
    composer.style.height = `${Math.min(composer.scrollHeight, 192)}px`;
  }

  return (
    <section className="relative flex min-h-0 min-w-0 flex-1 flex-col bg-background/55">
      <header className="flex h-14 shrink-0 items-center border-b border-border/70 bg-background/70 pr-4 pl-14 backdrop-blur-xl sm:pr-6 lg:px-6">
        <div className="mx-auto flex w-full max-w-3xl items-center justify-between gap-4">
          <h1 className="min-w-0 truncate text-sm font-bold text-foreground">{title ?? "Cuộc trò chuyện mới"}</h1>
          <span className="eyebrow hidden text-muted-foreground sm:block">Agricultural intelligence</span>
        </div>
      </header>

      <div
        ref={conversationRef}
        className="min-h-0 flex-1 overflow-y-auto overscroll-contain"
        aria-live="polite"
      >
        {messages.length === 0 && !isLoading ? (
          <EmptyConversation onSelect={(text) => setValue("question", text, { shouldValidate: true })} />
        ) : (
          <div className="mx-auto w-full max-w-3xl px-4 pt-8 pb-44 sm:px-6 sm:pt-10">
            <div className="space-y-8 sm:space-y-10">
              {messages.map((message) => (
                <MessageRow
                  key={message.id}
                  message={message}
                />
              ))}

              {streamingStatus.length > 0 && <StreamingStatus message={streamingStatus} />}
            </div>
          </div>
        )}
      </div>

      <div className="pointer-events-none absolute inset-x-0 bottom-0 bg-gradient-to-t from-background via-background/95 to-transparent px-3 pt-12 pb-3 sm:px-6 sm:pb-5">
        <form
          className="pointer-events-auto mx-auto w-full max-w-3xl"
          onSubmit={handleSubmit(submit)}
          noValidate
        >
          <div
            className={cn(
              "relative rounded-[26px] border bg-card/95 shadow-[0_20px_60px_rgb(0_0_0/0.28)] backdrop-blur-xl transition-colors",
              errors.question === undefined ? "border-border focus-within:border-primary/45" : "border-destructive/70",
            )}
          >
            <label
              className="sr-only"
              htmlFor="question"
            >
              Nhắn tin cho AeroField
            </label>
            <textarea
              key={composerVersion}
              id="question"
              {...questionField}
              className="block max-h-48 min-h-14 w-full resize-none bg-transparent px-5 pt-4 pr-16 pb-3 text-base leading-6 text-foreground outline-none placeholder:text-muted-foreground/75 disabled:cursor-not-allowed disabled:opacity-60"
              placeholder="Nhắn tin cho AeroField"
              rows={1}
              aria-invalid={errors.question !== undefined}
              aria-describedby={errors.question !== undefined ? "question-error" : "composer-hint"}
              disabled={isLoading}
              onInput={handleComposerInput}
              onKeyDown={handleComposerKeyDown}
            />
            <button
              className="absolute right-2 bottom-2 grid size-10 place-items-center rounded-full bg-primary text-primary-foreground shadow-[0_8px_24px_rgb(185_243_74/0.18)] transition hover:bg-primary/90 focus-visible:ring-2 focus-visible:ring-ring/50 focus-visible:outline-none disabled:bg-secondary disabled:text-muted-foreground disabled:shadow-none"
              type="submit"
              disabled={isLoading}
              aria-label={isLoading ? "Đang tạo câu trả lời" : "Gửi tin nhắn"}
            >
              {isLoading ? <Spinner className="size-4" /> : <ArrowUp className="size-5" />}
            </button>
          </div>
          {errors.question !== undefined ? (
            <FieldError
              className="mt-2 px-3 text-xs text-destructive-text"
              id="question-error"
              role="alert"
            >
              {errors.question.message}
            </FieldError>
          ) : (
            <p
              className="mt-2 text-center text-[11px] text-muted-foreground"
              id="composer-hint"
            >
              AeroField có thể mắc lỗi. Hãy kiểm tra thông tin quan trọng.
            </p>
          )}
        </form>
      </div>
    </section>
  );
}

function MessageRow({ message }: { message: ChatMessage }) {
  const isUser = message.role === "user";

  if (isUser) {
    return (
      <div className="flex justify-end">
        <div className="max-w-[88%] rounded-3xl border border-primary/15 bg-primary/10 px-5 py-3 text-[15px] leading-7 text-foreground sm:max-w-[78%]">
          <p className="whitespace-pre-wrap">{message.message}</p>
        </div>
      </div>
    );
  }

  return (
    <article className="group flex items-start gap-3 sm:gap-4">
      <span className="mt-0.5 grid size-8 shrink-0 place-items-center rounded-xl bg-primary text-primary-foreground shadow-[0_8px_24px_rgb(185_243_74/0.12)]">
        <Leaf className="size-4" />
      </span>
      <div className="min-w-0 flex-1">
        <p className="mb-2 text-sm font-bold text-foreground">AeroField</p>
        <div className="whitespace-pre-wrap text-[15px] leading-7 text-secondary-foreground">{message.message}</div>
      </div>
    </article>
  );
}

function StreamingStatus({ message }: { message: string }) {
  return (
    <div className="flex items-start gap-3 sm:gap-4">
      <span className="mt-0.5 grid size-8 shrink-0 place-items-center rounded-xl bg-primary text-primary-foreground shadow-[0_8px_24px_rgb(185_243_74/0.12)]">
        <Leaf className="size-4" />
      </span>
      <div className="pt-1">
        <p className="mb-2 text-sm font-bold text-foreground">AeroField</p>
        <p className="flex items-center gap-2 text-sm text-muted-foreground">
          <span className="flex gap-1">
            <span className="size-1.5 animate-pulse rounded-full bg-primary/70" />
            <span className="size-1.5 animate-pulse rounded-full bg-primary/70 [animation-delay:150ms]" />
            <span className="size-1.5 animate-pulse rounded-full bg-primary/70 [animation-delay:300ms]" />
          </span>
          {message}
        </p>
      </div>
    </div>
  );
}

function EmptyConversation({ onSelect }: { onSelect: (text: string) => void }) {
  return (
    <div className="mx-auto flex min-h-full w-full max-w-3xl flex-col justify-center px-4 pt-12 pb-40 sm:px-6">
      <div className="mx-auto w-full">
        <div className="flex items-center justify-center gap-3">
          <span className="grid size-11 place-items-center rounded-xl bg-primary text-primary-foreground shadow-[0_12px_36px_rgb(185_243_74/0.16)]">
            <Leaf className="size-5" />
          </span>
          <Sparkles className="size-5 text-primary/45" />
        </div>
        <p className="eyebrow mt-7 text-center text-primary">AI field assistant</p>
        <h2 className="mt-3 text-center text-2xl font-bold tracking-[-0.035em] text-foreground sm:text-3xl">
          Hôm nay tôi có thể giúp gì?
        </h2>
        <p className="mx-auto mt-3 max-w-lg text-center text-sm leading-6 text-muted-foreground">
          Hỏi về thời tiết, mùa vụ, kỹ thuật canh tác hoặc dữ liệu vận hành nông nghiệp.
        </p>

        <div className="mt-8 grid gap-3 sm:grid-cols-2">
          <Suggestion
            icon={CloudSun}
            title="Kiểm tra thời tiết"
            text="Thời tiết tuần này ảnh hưởng thế nào đến lịch canh tác?"
            onSelect={onSelect}
          />
          <Suggestion
            icon={LineChart}
            title="Phân tích mùa vụ"
            text="Ước tính sản lượng lúa với 10 ha và năng suất 6 tấn/ha."
            onSelect={onSelect}
          />
          <Suggestion
            icon={Search}
            title="Tìm thông tin mới"
            text="Tìm kỹ thuật phòng trừ sâu bệnh mới nhất cho cây lúa."
            onSelect={onSelect}
          />
          <Suggestion
            icon={Bot}
            title="Tư vấn canh tác"
            text="Gợi ý kế hoạch chăm sóc cây trồng phù hợp với điều kiện Việt Nam."
            onSelect={onSelect}
          />
        </div>
      </div>
    </div>
  );
}

type SuggestionProps = {
  icon: typeof CloudSun;
  title: string;
  text: string;
  onSelect: (text: string) => void;
};

function Suggestion({ icon: Icon, onSelect, text, title }: SuggestionProps) {
  return (
    <button
      className="group min-h-24 rounded-2xl border border-border/70 bg-card/55 p-4 text-left transition hover:border-primary/30 hover:bg-secondary/70 focus-visible:ring-2 focus-visible:ring-ring/40 focus-visible:outline-none"
      type="button"
      onClick={() => onSelect(text)}
    >
      <Icon className="size-4 text-primary/80 transition group-hover:text-primary" />
      <span className="mt-3 block text-sm font-bold text-foreground">{title}</span>
      <span className="mt-1 line-clamp-2 block text-xs leading-5 text-muted-foreground">{text}</span>
    </button>
  );
}
