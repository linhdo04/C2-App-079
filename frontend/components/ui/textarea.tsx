import type { ComponentProps } from "react";
import { cn } from "@/lib/utils";

function Textarea({ className, ...props }: ComponentProps<"textarea">) {
  return (
    <textarea
      data-slot="textarea"
      className={cn(
        "min-h-44 w-full resize-y rounded-xl border border-input bg-background/60 px-4 py-4 text-base leading-7 text-foreground outline-none transition-all placeholder:text-muted-foreground/70 disabled:cursor-not-allowed disabled:opacity-55",
        "focus-visible:border-ring/70 focus-visible:bg-background focus-visible:ring-2 focus-visible:ring-ring/15",
        "aria-invalid:border-destructive aria-invalid:ring-2 aria-invalid:ring-destructive/20",
        className,
      )}
      {...props}
    />
  );
}

export { Textarea };
