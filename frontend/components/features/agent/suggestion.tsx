"use client";

import { Thermometer } from "lucide-react";

type SuggestionProps = {
  icon: typeof Thermometer;
  title: string;
  text: string;
  onSelect: (text: string) => void;
};

export default function Suggestion({ icon: Icon, onSelect, text, title }: SuggestionProps) {
  return (
    <button
      className="group min-h-24 rounded-xl border border-border/70 bg-card/55 p-3 text-left transition hover:border-primary/30 hover:bg-secondary/70 focus-visible:ring-2 focus-visible:ring-ring/40 focus-visible:outline-none"
      type="button"
      onClick={() => onSelect(text)}
    >
      <Icon className="size-4 text-primary/80 transition group-hover:text-primary" />
      <span className="mt-3 block text-sm font-bold text-foreground">{title}</span>
      <span className="mt-1 line-clamp-2 block text-xs leading-5 text-muted-foreground">{text}</span>
    </button>
  );
}
