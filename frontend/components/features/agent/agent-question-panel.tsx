"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { ArrowUp } from "lucide-react";
import { type FormEvent, type KeyboardEvent, useEffect, useRef, useState } from "react";
import { useForm } from "react-hook-form";
import { FieldError } from "@/components/ui/field";
import { Spinner } from "@/components/ui/spinner";
import { agentQuestionSchema, type AgentQuestionFormValues } from "@/lib/validation";
import { cn } from "@/lib/utils";
import type { ChatMessage } from "@/types/agent";
import EmptyConversation from "./empty-conversation";
import StreamingStatus from "./streaming-status";
import MessageRow from "./message-row";

type AgentQuestionPanelProps = {
  isLoading: boolean;
  messages: ChatMessage[];
  streamingStatus?: string;
  onSubmit: (values: AgentQuestionFormValues) => Promise<boolean>;
};

export function AgentQuestionPanel({ isLoading, messages, streamingStatus = "", onSubmit }: AgentQuestionPanelProps) {
  const {
    formState: { errors },
    handleSubmit,
    reset,
    setValue,
  } = useForm<AgentQuestionFormValues>({
    defaultValues: { question: "" },
    resolver: zodResolver(agentQuestionSchema),
  });
  const conversationRef = useRef<HTMLDivElement>(null);
  const questionRef = useRef<HTMLDivElement>(null);
  const [composerVersion, setComposerVersion] = useState(0);
  const [isComposerEmpty, setIsComposerEmpty] = useState(true);

  useEffect(() => {
    const conversation = conversationRef.current;
    if (conversation !== null) {
      conversation.scrollTo({
        top: conversation.scrollHeight,
        behavior: messages.length > 1 ? "smooth" : "auto",
      });
    }
  }, [messages, streamingStatus]);

  useEffect(() => {
    if (composerVersion > 0) {
      questionRef.current?.focus();
    }
  }, [composerVersion]);

  async function submit(values: AgentQuestionFormValues) {
    const submission = onSubmit(values);
    reset();
    setIsComposerEmpty(true);
    setComposerVersion((version) => version + 1);
    await submission;
  }

  function handleComposerKeyDown(event: KeyboardEvent<HTMLDivElement>) {
    if (event.key !== "Enter" || event.shiftKey || event.nativeEvent.isComposing) {
      return;
    }
    event.preventDefault();
    if (!isLoading) {
      void handleSubmit(submit)();
    }
  }

  function handleComposerInput(event: FormEvent<HTMLDivElement>) {
    const composer = event.currentTarget;
    const question = composer.innerText;
    setIsComposerEmpty(question.length === 0);
    setValue("question", question, { shouldDirty: true, shouldValidate: errors.question !== undefined });
  }

  function handleSuggestionSelect(text: string) {
    setValue("question", text, { shouldDirty: true, shouldValidate: true });
    setIsComposerEmpty(false);
    if (questionRef.current !== null) {
      const composer = questionRef.current;
      composer.textContent = text;
      composer.focus();

      const range = document.createRange();
      range.selectNodeContents(composer);
      range.collapse(false);
      const selection = window.getSelection();
      selection?.removeAllRanges();
      selection?.addRange(range);
    }
  }

  return (
    <section className="relative flex min-h-0 min-w-0 flex-1 flex-col bg-background/55">
      <div
        ref={conversationRef}
        className="min-h-0 flex-1 touch-pan-y overflow-y-auto overscroll-contain"
        aria-live="polite"
      >
        {messages.length === 0 && !isLoading ? (
          <EmptyConversation onSelect={handleSuggestionSelect} />
        ) : (
          <div className="mx-auto w-full max-w-3xl px-4 pt-5 pb-36">
            <div className="space-y-6">
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

      <div className="pointer-events-none absolute inset-x-0 bottom-0 bg-gradient-to-t from-background via-background/95 to-transparent px-3 pt-10 pb-3">
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
            {isComposerEmpty && (
              <span
                className="pointer-events-none absolute top-3 left-4 text-sm leading-6 text-muted-foreground/75"
                aria-hidden="true"
              >
                Nhắn tin cho AeroField
              </span>
            )}
            <div
              key={composerVersion}
              ref={questionRef}
              id="question"
              className="block max-h-36 min-h-12 w-full overflow-y-auto bg-transparent px-4 pt-3 pr-14 pb-2.5 text-sm leading-6 whitespace-pre-wrap text-foreground outline-none"
              contentEditable
              suppressContentEditableWarning
              inputMode="text"
              autoCorrect="on"
              autoCapitalize="sentences"
              spellCheck
              translate="no"
              role="textbox"
              aria-multiline="true"
              aria-label="Nhắn tin cho AeroField"
              aria-invalid={errors.question !== undefined}
              aria-describedby={errors.question !== undefined ? "question-error" : "composer-hint"}
              data-virtualkeyboard="true"
              onInput={handleComposerInput}
              onKeyDown={handleComposerKeyDown}
            />
            <button
              className="absolute right-1.5 bottom-1.5 grid size-10 place-items-center rounded-full bg-primary text-primary-foreground shadow-[0_8px_24px_rgb(185_243_74/0.18)] transition hover:bg-primary/90 focus-visible:ring-2 focus-visible:ring-ring/50 focus-visible:outline-none disabled:bg-secondary disabled:text-muted-foreground disabled:shadow-none"
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
