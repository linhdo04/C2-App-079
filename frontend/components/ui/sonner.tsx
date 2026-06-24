"use client";

import { CircleCheckIcon, InfoIcon, Loader2Icon, OctagonXIcon, TriangleAlertIcon } from "lucide-react";
import { useTheme } from "next-themes";
import type { CSSProperties } from "react";
import { Toaster as Sonner, type ToasterProps } from "sonner";

const TOAST_CLASS_NAMES = {
  toast:
    "group/toast relative overflow-visible rounded-2xl border border-border/80 bg-card/95 px-4 py-3 pr-12 text-foreground shadow-[0_24px_80px_rgb(0_0_0/0.42)] backdrop-blur-xl before:absolute before:inset-y-3 before:left-0 before:w-1 before:rounded-r-full before:bg-primary data-[swiping=true]:shadow-[0_18px_48px_rgb(0_0_0/0.34)]",
  title: "text-sm font-bold tracking-[-0.02em] text-foreground",
  description: "mt-1 text-xs leading-5 text-muted-foreground",
  content: "min-w-0 gap-1",
  icon: "mr-3 grid size-9 shrink-0 place-items-center rounded-xl bg-primary/12 text-primary",
  closeButton:
    "!top-3 !right-3 !left-auto !z-20 !size-7 !translate-x-0 !translate-y-0 !transform-none border-border/80 bg-background/95 text-muted-foreground shadow-lg transition hover:border-primary/50 hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring/50",
  actionButton:
    "rounded-lg bg-primary px-3 py-2 text-xs font-bold text-primary-foreground shadow-[0_10px_24px_rgb(185_243_74/0.18)] transition hover:bg-primary/90",
  cancelButton: "rounded-lg border border-border bg-secondary px-3 py-2 text-xs font-bold text-secondary-foreground",
  success: "border-success/40 before:bg-success [&_[data-icon]]:text-success",
  info: "border-primary/40 before:bg-primary",
  warning: "border-[#ffd166]/45 before:bg-[#ffd166] [&_[data-icon]]:text-[#ffd166]",
  error: "border-destructive/55 before:bg-destructive [&_[data-icon]]:text-destructive-text",
  loading: "border-primary/35 before:bg-primary",
} satisfies NonNullable<ToasterProps["toastOptions"]>["classNames"];

const Toaster = ({ ...props }: ToasterProps) => {
  const { theme = "system" } = useTheme();

  return (
    <Sonner
      theme={theme as ToasterProps["theme"]}
      className="toaster group"
      closeButton
      expand
      gap={12}
      visibleToasts={4}
      duration={4500}
      containerAriaLabel="Thông báo hệ thống"
      icons={{
        success: <CircleCheckIcon className="size-5" />,
        info: <InfoIcon className="size-5" />,
        warning: <TriangleAlertIcon className="size-5" />,
        error: <OctagonXIcon className="size-5" />,
        loading: <Loader2Icon className="size-5 animate-spin" />,
      }}
      mobileOffset={{
        top: 16,
        right: 12,
        left: 12,
      }}
      offset={{
        top: 20,
      }}
      style={
        {
          "--normal-bg": "var(--card)",
          "--normal-text": "var(--foreground)",
          "--normal-border": "var(--border)",
          "--border-radius": "1rem",
        } as CSSProperties
      }
      toastOptions={{
        closeButton: true,
        closeButtonAriaLabel: "Đóng thông báo",
        classNames: TOAST_CLASS_NAMES,
      }}
      {...props}
    />
  );
};

export { Toaster };
