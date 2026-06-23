import { Leaf } from "lucide-react";

export default function StreamingStatus({ message }: { message: string }) {
  return (
    <div className="flex items-start gap-3">
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
