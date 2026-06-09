"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { ArrowUp, Bot, CloudSun, Lightbulb, LineChart } from "lucide-react";
import { useForm } from "react-hook-form";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Field, FieldError, FieldLabel } from "@/components/ui/field";
import { Spinner } from "@/components/ui/spinner";
import { Textarea } from "@/components/ui/textarea";
import { agentQuestionSchema, type AgentQuestionFormValues } from "@/lib/validation";

type AgentQuestionPanelProps = {
  answer: string;
  isLoading: boolean;
  onSubmit: (values: AgentQuestionFormValues) => void;
};

export function AgentQuestionPanel({ answer, isLoading, onSubmit }: AgentQuestionPanelProps) {
  const {
    formState: { errors },
    handleSubmit,
    register,
    setValue,
  } = useForm<AgentQuestionFormValues>({
    defaultValues: {
      question: "",
    },
    resolver: zodResolver(agentQuestionSchema),
  });

  return (
    <section className="min-w-0">
      <Card className="overflow-hidden">
        <CardHeader className="border-b border-border/70 pb-5">
          <div className="flex items-start gap-4">
            <span className="grid size-11 shrink-0 place-items-center rounded-xl bg-primary text-primary-foreground">
              <Bot className="size-5" />
            </span>
            <div>
              <p className="eyebrow text-primary">Agricultural intelligence</p>
              <CardTitle className="mt-1 text-2xl">Hỏi AeroField Agent</CardTitle>
              <p className="mt-1 text-sm leading-6 text-muted-foreground">
                Mô tả bối cảnh cụ thể để nhận phân tích sát với tình hình vận hành.
              </p>
            </div>
          </div>
        </CardHeader>
        <CardContent className="pt-5 sm:pt-6">
          <form
            className="grid gap-4"
            onSubmit={handleSubmit(onSubmit)}
            noValidate
          >
            <Field>
              <FieldLabel htmlFor="question">Câu hỏi vận hành</FieldLabel>
              <Textarea
                id="question"
                {...register("question")}
                placeholder="Ví dụ: Với dự báo mưa tại Hà Nội tuần này, tôi nên điều chỉnh lịch phun thuốc cho lúa như thế nào?"
                aria-invalid={errors.question !== undefined}
                aria-describedby={errors.question !== undefined ? "question-error" : undefined}
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

            <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
              <p className="text-xs text-muted-foreground">Agent có thể mất vài giây để tổng hợp dữ liệu.</p>
              <Button
                className="sm:w-fit"
                type="submit"
                disabled={isLoading}
              >
                {isLoading && <Spinner data-icon="inline-start" />}
                {isLoading ? "Đang phân tích..." : "Phân tích"}
                {!isLoading && <ArrowUp />}
              </Button>
            </div>
          </form>

          <div
            className="mt-6 min-h-52 rounded-2xl border border-border/70 bg-background/60 p-5 sm:p-6"
            aria-live="polite"
          >
            {isLoading ? (
              <div className="flex min-h-40 flex-col items-center justify-center text-center">
                <span className="grid size-11 place-items-center rounded-full bg-primary/10 text-primary">
                  <Spinner />
                </span>
                <p className="mt-4 text-sm font-bold">Đang tổng hợp tín hiệu</p>
                <p className="mt-1 text-xs text-muted-foreground">Phân tích dữ liệu và xây dựng khuyến nghị...</p>
              </div>
            ) : answer.length > 0 ? (
              <div>
                <p className="eyebrow mb-4 text-primary">Agent response</p>
                <p className="whitespace-pre-wrap text-base leading-7 text-foreground">{answer}</p>
              </div>
            ) : (
              <div>
                <div className="flex items-center gap-2">
                  <Lightbulb className="size-4 text-primary" />
                  <p className="text-sm font-bold text-foreground">Gợi ý bắt đầu</p>
                </div>
                <div className="mt-4 grid gap-2 sm:grid-cols-2">
                  <Suggestion
                    icon={CloudSun}
                    text="Thời tiết tuần này ảnh hưởng thế nào đến lịch canh tác?"
                    onSelect={(text) => setValue("question", text, { shouldValidate: true })}
                  />
                  <Suggestion
                    icon={LineChart}
                    text="Phân tích xu hướng thị trường cho vụ mùa hiện tại."
                    onSelect={(text) => setValue("question", text, { shouldValidate: true })}
                  />
                </div>
              </div>
            )}
          </div>
        </CardContent>
      </Card>
    </section>
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
