"use client";

import { History, LogOut, Menu, MessageSquare, Plus, Search, Trash2, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";
import type { ChatSession } from "@/types/agent";
import type { User } from "@/types/auth";

type ChatHistoryPanelProps = {
  activeChatId: number | null;
  chats: ChatSession[];
  isDeleting: boolean;
  isLoading: boolean;
  isOpen: boolean;
  search: string;
  user: User;
  onClose: () => void;
  onDelete: (chatId: number) => void;
  onLogout: () => void;
  onNewChat: () => void;
  onOpen: () => void;
  onSearchChange: (value: string) => void;
  onSelect: (chatId: number) => void;
};

export function ChatHistoryPanel({
  activeChatId,
  chats,
  isDeleting,
  isLoading,
  isOpen,
  search,
  user,
  onClose,
  onDelete,
  onLogout,
  onNewChat,
  onOpen,
  onSearchChange,
  onSelect,
}: ChatHistoryPanelProps) {
  return (
    <>
      <Button
        className="w-full justify-start lg:hidden"
        type="button"
        variant="outline"
        onClick={onOpen}
      >
        <Menu />
        Lịch sử trò chuyện
      </Button>

      {isOpen && (
        <button
          className="fixed inset-0 z-30 bg-black/60 lg:hidden"
          type="button"
          aria-label="Đóng lịch sử trò chuyện"
          onClick={onClose}
        />
      )}

      <aside
        className={cn(
          "fixed inset-y-0 left-0 z-40 flex w-[min(88vw,340px)] flex-col border-r border-border bg-card p-4 shadow-2xl transition-transform duration-200 lg:static lg:z-auto lg:w-auto lg:translate-x-0 lg:rounded-2xl lg:border lg:shadow-[0_24px_80px_rgb(0_0_0/0.18)]",
          isOpen ? "translate-x-0" : "-translate-x-full",
        )}
        aria-label="Lịch sử trò chuyện"
      >
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <History className="size-4 text-primary" />
            <h2 className="text-sm font-bold">Lịch sử chat</h2>
          </div>
          <Button
            className="lg:hidden"
            type="button"
            size="icon"
            variant="ghost"
            aria-label="Đóng lịch sử"
            onClick={onClose}
          >
            <X />
          </Button>
        </div>

        <Button
          className="mt-4 w-full"
          type="button"
          onClick={onNewChat}
        >
          <Plus />
          Tạo chat mới
        </Button>

        <label className="relative mt-4 block">
          <span className="sr-only">Tìm kiếm cuộc trò chuyện</span>
          <Search className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            className="pl-10"
            type="search"
            value={search}
            placeholder="Tìm tiêu đề hoặc nội dung..."
            onChange={(event) => onSearchChange(event.target.value)}
          />
        </label>

        <div className="mt-4 min-h-0 flex-1 space-y-1 overflow-y-auto">
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
            chats.map((chat) => (
              <div
                className={cn(
                  "group flex min-h-12 items-center rounded-xl border transition-colors",
                  activeChatId === chat.id
                    ? "border-primary/30 bg-primary/10"
                    : "border-transparent hover:bg-secondary",
                )}
                key={chat.id}
              >
                <button
                  className="min-w-0 flex-1 px-3 py-3 text-left"
                  type="button"
                  onClick={() => onSelect(chat.id)}
                >
                  <span className="block truncate text-sm font-semibold">{chat.title}</span>
                  <span className="mt-1 block text-[11px] text-muted-foreground">
                    {formatChatDate(chat.updated_at)}
                  </span>
                </button>
                <button
                  className="grid size-11 shrink-0 place-items-center rounded-xl text-muted-foreground hover:bg-destructive-muted hover:text-destructive-text focus-visible:ring-2 focus-visible:ring-ring/50 focus-visible:outline-none"
                  type="button"
                  disabled={isDeleting}
                  aria-label={`Xoá ${chat.title}`}
                  onClick={() => onDelete(chat.id)}
                >
                  <Trash2 className="size-4" />
                </button>
              </div>
            ))
          )}
        </div>

        <div className="mt-4 border-t border-border pt-4">
          <p className="truncate text-sm font-bold">{user.name}</p>
          <p className="truncate text-xs text-muted-foreground">{user.email}</p>
          <Button
            className="mt-3 w-full justify-start"
            type="button"
            variant="ghost"
            onClick={onLogout}
          >
            <LogOut />
            Đăng xuất
          </Button>
        </div>
      </aside>
    </>
  );
}

function formatChatDate(value: string) {
  return new Intl.DateTimeFormat("vi-VN", {
    day: "2-digit",
    month: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(value));
}
