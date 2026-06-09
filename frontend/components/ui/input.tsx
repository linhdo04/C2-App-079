import type { ComponentProps } from "react";
import { cn } from "@/lib/utils";

function Input({ className, type, ...props }: ComponentProps<"input">) {
  return (
    <input
      data-slot="input"
      type={type}
      className={cn(
        "min-h-12 w-full rounded-xl border border-input bg-background/60 px-4 text-base text-foreground outline-none transition-all placeholder:text-muted-foreground/70 disabled:cursor-not-allowed disabled:opacity-55 md:text-sm",
        "focus-visible:border-ring/70 focus-visible:bg-background focus-visible:ring-2 focus-visible:ring-ring/15",
        "aria-invalid:border-destructive aria-invalid:ring-2 aria-invalid:ring-destructive/20",
        className,
      )}
      {...props}
    />
  );
}

export { Input };
