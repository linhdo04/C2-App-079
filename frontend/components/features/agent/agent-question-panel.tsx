"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useForm } from "react-hook-form";
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
  } = useForm<AgentQuestionFormValues>({
    defaultValues: {
      question: "",
    },
    resolver: zodResolver(agentQuestionSchema),
  });

  return (
    <section className="rounded-2xl border border-[#d8d2c7] bg-white p-4 shadow-sm sm:p-6">
      <div className="flex flex-col gap-2 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <p className="text-sm font-semibold text-[#456b58]">AI Agent</p>
          <h2 className="mt-1 text-2xl font-semibold text-[#1d2b24]">Hỏi trợ lý nông nghiệp</h2>
        </div>
      </div>

      <form
        className="mt-5 grid gap-4"
        onSubmit={handleSubmit(onSubmit)}
        noValidate
      >
        <label className="grid gap-2 text-sm font-medium text-[#273a31]">
          Câu hỏi
          <textarea
            className="min-h-36 resize-y rounded-xl border border-[#cfc7ba] px-3 py-3 text-base leading-7 outline-none focus:border-[#47745d] focus:ring-2 focus:ring-[#47745d]/20"
            {...register("question")}
            placeholder="Ví dụ: Dự báo thời tiết ở Hà Nội có ảnh hưởng đến cây lúa không?"
            aria-invalid={errors.question !== undefined}
          />
          {errors.question !== undefined && <span className="text-sm text-[#7e2416]">{errors.question.message}</span>}
        </label>

        <button
          className="min-h-11 rounded-xl bg-[#2f5d48] px-4 text-sm font-semibold text-white transition hover:bg-[#254a39] disabled:cursor-not-allowed disabled:bg-[#93a79b] sm:w-fit"
          type="submit"
          disabled={isLoading}
        >
          {isLoading ? "Đang hỏi Agent..." : "Gửi câu hỏi"}
        </button>
      </form>

      <div className="mt-6 min-h-40 rounded-xl border border-[#d8d2c7] bg-[#fbfaf7] p-4">
        {isLoading ? (
          <p className="text-sm text-[#526158]">Agent đang tổng hợp câu trả lời...</p>
        ) : answer.length > 0 ? (
          <p className="whitespace-pre-wrap text-base leading-7 text-[#273a31]">{answer}</p>
        ) : (
          <p className="text-sm leading-6 text-[#526158]">Câu trả lời sẽ xuất hiện tại đây sau khi bạn gửi câu hỏi.</p>
        )}
      </div>
    </section>
  );
}
