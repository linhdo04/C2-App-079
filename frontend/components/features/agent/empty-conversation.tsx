"use client";

import { CalendarDays, Droplets, Leaf, Sparkles, Thermometer, TrendingDown } from "lucide-react";
import Suggestion from "./suggestion";

export default function EmptyConversation({ onSelect }: { onSelect: (text: string) => void }) {
  return (
    <div className="mx-auto flex min-h-full w-full max-w-3xl flex-col justify-center px-4 pt-8 pb-32">
      <div className="mx-auto w-full">
        <div className="flex items-center justify-center gap-3">
          <span className="grid size-11 place-items-center rounded-xl bg-primary text-primary-foreground shadow-[0_12px_36px_rgb(185_243_74/0.16)]">
            <Leaf className="size-5" />
          </span>
          <Sparkles className="size-5 text-primary/45" />
        </div>
        <p className="eyebrow mt-5 text-center text-primary">AI field assistant</p>
        <h2 className="mt-2 text-center text-xl font-bold tracking-[-0.035em] text-foreground">
          Hôm nay tôi có thể giúp gì?
        </h2>
        <p className="mx-auto mt-2 max-w-sm text-center text-xs leading-5 text-muted-foreground">
          Hỏi về thời tiết, mùa vụ, kỹ thuật canh tác hoặc dữ liệu vận hành nông nghiệp.
        </p>

        <div className="mt-5 grid grid-cols-2 gap-2">
          <Suggestion
            icon={Thermometer}
            title="Nhiệt độ cao nhất"
            text="Nhiệt độ cao nhất hôm nay là bao nhiêu?"
            onSelect={onSelect}
          />
          <Suggestion
            icon={TrendingDown}
            title="Nhiệt độ thấp nhất"
            text="Nhiệt độ thấp nhất tuần trước là bao nhiêu?"
            onSelect={onSelect}
          />
          <Suggestion
            icon={Droplets}
            title="Độ ẩm cao nhất"
            text="Độ ẩm cao nhất hôm nay là bao nhiêu?"
            onSelect={onSelect}
          />
          <Suggestion
            icon={CalendarDays}
            title="Độ ẩm thấp nhất"
            text="Độ ẩm thấp nhất trong 7 ngày qua là bao nhiêu?"
            onSelect={onSelect}
          />
        </div>
      </div>
    </div>
  );
}
