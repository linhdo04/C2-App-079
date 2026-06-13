"use client";

import { LogOut, Menu, MessageSquare, PanelLeftClose, Plus, Radar, Search, Trash2 } from "lucide-react";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";
import type { ChatSession } from "@/types/agent";
import { useAuthStore } from "@/lib/auth-store";

type ChatHistoryPanelProps = {
  activeChatId: number | null;
  chats: ChatSession[];
  hasMore: boolean;
  isDeleting: boolean;
  isLoading: boolean;
  isLoadingMore: boolean;
  isOpen: boolean;
  search: string;
  onClose: () => void;
  onDelete: (chatId: number) => void;
  onLogout: () => void;
  onLoadMore: () => void;
  onNewChat: () => void;
  onOpen: () => void;
  onSearchChange: (value: string) => void;
  onSelect: (chatId: number) => void;
};

export function ChatHistoryPanel({
  activeChatId,
  chats,
  hasMore,
  isDeleting,
  isLoading,
  isLoadingMore,
  isOpen,
  search,
  onClose,
  onDelete,
  onLogout,
  onLoadMore,
  onNewChat,
  onOpen,
  onSearchChange,
  onSelect,
}: ChatHistoryPanelProps) {
  const { user } = useAuthStore();

  return (
    <>
      <button
        className="fixed top-2.5 left-2.5 z-20 grid size-9 place-items-center rounded-lg text-muted-foreground hover:bg-secondary hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring/40 focus-visible:outline-none lg:hidden"
        type="button"
        aria-label="Mở lịch sử trò chuyện"
        onClick={onOpen}
      >
        <Menu className="size-5" />
      </button>

      {isOpen && (
        <button
          className="fixed inset-0 z-30 bg-black/55 backdrop-blur-[2px] lg:hidden"
          type="button"
          aria-label="Đóng lịch sử trò chuyện"
          onClick={onClose}
        />
      )}

      <aside
        className={cn(
          "fixed inset-y-0 left-0 z-40 flex w-[min(86vw,280px)] flex-col border-r border-border bg-card/95 p-2 text-foreground shadow-2xl backdrop-blur-xl transition-transform duration-200 lg:static lg:z-auto lg:w-[260px] lg:shrink-0 lg:translate-x-0 lg:shadow-none",
          isOpen ? "translate-x-0" : "-translate-x-full",
        )}
        aria-label="Lịch sử trò chuyện"
      >
        <div className="flex h-12 items-center justify-between px-2">
          <button
            className="flex min-h-11 items-center gap-2 rounded-lg px-2 text-left hover:bg-secondary focus-visible:ring-2 focus-visible:ring-ring/40 focus-visible:outline-none"
            type="button"
            onClick={onNewChat}
          >
            <span className="grid size-8 place-items-center rounded-xl bg-primary text-primary-foreground">
              <Radar className="size-4" />
            </span>
            <span className="text-sm font-semibold">AeroField</span>
          </button>
          <button
            className="grid size-11 place-items-center rounded-lg text-muted-foreground hover:bg-secondary hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring/40 focus-visible:outline-none lg:hidden"
            type="button"
            aria-label="Đóng thanh bên"
            onClick={onClose}
          >
            <PanelLeftClose className="size-5" />
          </button>
        </div>

        <button
          className="mt-1 flex min-h-11 w-full items-center gap-3 rounded-lg px-3 text-sm font-bold hover:bg-secondary focus-visible:ring-2 focus-visible:ring-ring/40 focus-visible:outline-none"
          type="button"
          onClick={onNewChat}
        >
          <Plus className="size-4" />
          Cuộc trò chuyện mới
        </button>

        <label className="relative mt-2 block">
          <span className="sr-only">Tìm kiếm cuộc trò chuyện</span>
          <Search className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            className="min-h-10 border-transparent bg-transparent pl-9 text-sm text-foreground hover:bg-secondary/60 focus-visible:border-border focus-visible:bg-background/60 focus-visible:ring-0"
            type="search"
            value={search}
            placeholder="Tìm kiếm đoạn chat"
            onChange={(event) => onSearchChange(event.target.value)}
          />
        </label>

        <p className="eyebrow mt-5 px-3 text-muted-foreground">Đoạn chat</p>

        <div className="mt-2 min-h-0 flex-1 space-y-0.5 overflow-y-auto">
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
                    onClick={() => onSelect(chat.id)}
                  >
                    <span className="block truncate text-sm text-secondary-foreground">{chat.title}</span>
                  </button>
                  <button
                    className="mr-1 grid size-9 shrink-0 place-items-center rounded-lg text-muted-foreground opacity-100 hover:bg-destructive-muted hover:text-destructive-text focus-visible:opacity-100 focus-visible:ring-2 focus-visible:ring-ring/40 focus-visible:outline-none lg:opacity-0 lg:group-hover:opacity-100"
                    type="button"
                    disabled={isDeleting}
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
                  disabled={isLoadingMore}
                  onClick={onLoadMore}
                >
                  {isLoadingMore ? "Đang tải thêm..." : "Tải thêm"}
                </button>
              )}
            </>
          )}
        </div>

        <div className="border-t border-border pt-2">
          <div className="group flex min-h-14 items-center gap-3 rounded-lg px-2 hover:bg-secondary/65">
            <span className="grid size-9 shrink-0 place-items-center rounded-xl bg-secondary text-sm font-bold text-primary">
              {user && user.name.trim().charAt(0).toUpperCase()}
            </span>
            <div className="min-w-0 flex-1">
              <p className="truncate text-sm font-bold text-foreground">{user && user.name}</p>
              <p className="truncate text-xs text-muted-foreground">{user && user.email}</p>
            </div>
            <button
              className="grid size-10 place-items-center rounded-lg text-muted-foreground hover:bg-secondary hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring/40 focus-visible:outline-none"
              type="button"
              aria-label="Đăng xuất"
              onClick={onLogout}
            >
              <LogOut className="size-4" />
            </button>
          </div>
        </div>
      </aside>
    </>
  );
}
