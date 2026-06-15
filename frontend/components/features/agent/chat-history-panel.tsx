import { MessageSquare, Plus, Search, Trash2 } from "lucide-react";
import { useEffect, useRef } from "react";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";
import type { ChatSession } from "@/types/agent";

type ChatHistoryPanelProps = {
  activeChatId: number | null;
  chats: ChatSession[];
  disabled: boolean;
  hasMore: boolean;
  isDeleting: boolean;
  isLoading: boolean;
  isLoadingMore: boolean;
  isOpen: boolean;
  search: string;
  onClose: () => void;
  onDelete: (chatId: number) => void;
  onLoadMore: () => void;
  onNewChat: () => void;
  onSearchChange: (value: string) => void;
  onSelect: (chatId: number) => void;
};

export function ChatHistoryPanel({
  activeChatId,
  chats,
  disabled,
  hasMore,
  isDeleting,
  isLoading,
  isLoadingMore,
  isOpen,
  search,
  onClose,
  onDelete,
  onLoadMore,
  onNewChat,
  onSearchChange,
  onSelect,
}: ChatHistoryPanelProps) {
  const closeButtonRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (!isOpen) {
      return;
    }
    const frame = window.requestAnimationFrame(() => closeButtonRef.current?.focus());
    return () => window.cancelAnimationFrame(frame);
  }, [isOpen]);

  return (
    <>
      {isOpen && (
        <button
          className="absolute inset-0 z-20 bg-black/55 backdrop-blur-[2px]"
          type="button"
          aria-label="Đóng lịch sử trò chuyện"
          onClick={onClose}
        />
      )}

      <aside
        className={cn(
          "absolute inset-y-0 left-0 z-30 flex w-[min(86%,280px)] flex-col border-r border-border bg-card/98 p-2 text-foreground shadow-2xl backdrop-blur-xl transition-transform duration-200",
          isOpen ? "translate-x-0" : "-translate-x-full",
        )}
        aria-label="Lịch sử trò chuyện"
        aria-hidden={!isOpen}
      >
        <button
          className="mt-1 flex min-h-11 w-full items-center gap-3 rounded-lg px-3 text-sm font-bold hover:bg-secondary focus-visible:ring-2 focus-visible:ring-ring/40 focus-visible:outline-none"
          type="button"
          disabled={disabled}
          onClick={onNewChat}
        >
          <Plus className="size-4" />
          Cuộc trò chuyện mới
        </button>

        <label className="relative mt-2 block">
          <span className="sr-only">Tìm kiếm cuộc trò chuyện</span>
          <Search className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            className="min-h-11 border-transparent bg-transparent pl-9 text-sm text-foreground hover:bg-secondary/60 focus-visible:border-border focus-visible:bg-background/60 focus-visible:ring-0"
            type="search"
            value={search}
            placeholder="Tìm kiếm đoạn chat"
            disabled={disabled}
            onChange={(event) => onSearchChange(event.target.value)}
          />
        </label>

        <p className="eyebrow mt-5 px-3 text-muted-foreground">Đoạn chat</p>

        <div className="mt-2 min-h-0 flex-1 touch-pan-y space-y-0.5 overflow-y-auto overscroll-contain">
          {isLoading ? (
            <p className="px-3 py-6 text-center text-xs text-muted-foreground">Đang tải lịch sử...</p>
          ) : chats.length === 0 ? (
            <div className="px-3 py-8 text-center">
              <MessageSquare className="mx-auto size-5 text-muted-foreground" />
              <p className="mt-2 text-xs leading-5 text-muted-foreground">
                {search.length > 0 ? "Không tìm thấy cuộc trò chuyện." : "Chưa có cuộc trò chuyện nào."}
              </p>
            </div>
          ) : (
            <>
              {chats.map((chat) => (
                <div
                  className={cn(
                    "group flex min-h-11 items-center rounded-lg",
                    activeChatId === chat.id ? "bg-secondary text-foreground" : "hover:bg-secondary/65",
                  )}
                  key={chat.id}
                >
                  <button
                    className="min-w-0 flex-1 px-3 py-2.5 text-left"
                    type="button"
                    disabled={disabled}
                    onClick={() => onSelect(chat.id)}
                  >
                    <span className="block truncate text-sm text-secondary-foreground">{chat.title}</span>
                  </button>
                  <button
                    className="mr-1 grid size-11 shrink-0 place-items-center rounded-lg text-muted-foreground opacity-100 hover:bg-destructive-muted hover:text-destructive-text focus-visible:opacity-100 focus-visible:ring-2 focus-visible:ring-ring/40 focus-visible:outline-none lg:opacity-0 lg:group-hover:opacity-100"
                    type="button"
                    disabled={disabled || isDeleting}
                    aria-label={`Xoá ${chat.title}`}
                    onClick={() => onDelete(chat.id)}
                  >
                    <Trash2 className="size-4" />
                  </button>
                </div>
              ))}
              {hasMore && (
                <button
                  className="mt-2 min-h-11 w-full rounded-lg px-3 text-xs font-bold text-muted-foreground hover:bg-secondary hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring/40 focus-visible:outline-none disabled:opacity-50"
                  type="button"
                  disabled={disabled || isLoadingMore}
                  onClick={onLoadMore}
                >
                  {isLoadingMore ? "Đang tải thêm..." : "Tải thêm"}
                </button>
              )}
            </>
          )}
        </div>
      </aside>
    </>
  );
}
