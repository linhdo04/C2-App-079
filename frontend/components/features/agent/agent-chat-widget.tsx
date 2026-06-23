"use client";

import { useQueryClient } from "@tanstack/react-query";
import { Bot, History, Maximize2, Minimize2, PanelLeft, RotateCcw, X } from "lucide-react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useCallback, useDeferredValue, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { toast } from "sonner";
import { AgentQuestionPanel } from "@/components/features/agent/agent-question-panel";
import { ChatHistoryPanel } from "@/components/features/agent/chat-history-panel";
import { Button } from "@/components/ui/button";
import { Spinner } from "@/components/ui/spinner";
import { ApiError, requestProtectedEventStream } from "@/lib/api-client";
import { useChatQuery, useChatsQuery, useCreateChatMutation, useDeleteChatMutation } from "@/lib/api-hooks";
import { cn } from "@/lib/utils";
import type { AgentQuestionFormValues } from "@/lib/validation";
import type { ChatDetail, ChatMessage, ChatMessageResponse } from "@/types/agent";

export function AgentChatWidget() {
  const pathname = usePathname();
  const router = useRouter();
  const searchParams = useSearchParams();
  const queryClient = useQueryClient();
  const launcherRef = useRef<HTMLButtonElement>(null);
  const closeButtonRef = useRef<HTMLButtonElement>(null);
  const widgetRef = useRef<HTMLDivElement>(null);
  const tokenBufferRef = useRef("");
  const animationFrameRef = useRef<number | null>(null);
  const searchParamsString = searchParams.toString();
  const rawChatId = searchParams.get("chat");
  const parsedChatId = rawChatId === null ? null : Number(rawChatId);
  const chatId = parsedChatId !== null && Number.isSafeInteger(parsedChatId) && parsedChatId > 0 ? parsedChatId : null;
  const [isOpen, setIsOpen] = useState(rawChatId !== null && chatId !== null);
  const [isHistoryOpen, setIsHistoryOpen] = useState(false);
  const [isExpanded, setIsExpanded] = useState(false);
  const [createdChatId, setCreatedChatId] = useState<number | null>(null);
  const [pendingQuestion, setPendingQuestion] = useState("");
  const [search, setSearch] = useState("");
  const [streamingAnswer, setStreamingAnswer] = useState("");
  const [streamingStatus, setStreamingStatus] = useState("");
  const [isStreaming, setIsStreaming] = useState(false);
  const deferredSearch = useDeferredValue(search);
  const chatsQuery = useChatsQuery(deferredSearch);
  const chats = useMemo(() => chatsQuery.data?.pages.flatMap((page) => page.data) ?? [], [chatsQuery.data]);
  const activeChatId = chatId ?? createdChatId;
  const chatQuery = useChatQuery(activeChatId);
  const createChatMutation = useCreateChatMutation();
  const deleteChatMutation = useDeleteChatMutation();
  const activeChat = chatQuery.data;
  const messages = useMemo(() => activeChat?.messages ?? [], [activeChat?.messages]);
  const isSending = createChatMutation.isPending || isStreaming;

  const replaceChatQuery = useCallback(
    (nextChatId: number | null) => {
      const nextParams = new URLSearchParams(searchParamsString);
      if (nextChatId === null) {
        nextParams.delete("chat");
      } else {
        nextParams.set("chat", String(nextChatId));
      }
      const query = nextParams.toString();
      if (query === searchParamsString) {
        return;
      }
      router.replace(query.length > 0 ? `${pathname}?${query}` : pathname, { scroll: false });
    },
    [pathname, router, searchParamsString],
  );

  useEffect(() => {
    if (rawChatId !== null && chatId === null) {
      replaceChatQuery(null);
      return;
    }
    if (chatId !== null) {
      if (createdChatId === chatId) {
        const frame = window.requestAnimationFrame(() => setCreatedChatId(null));
        return () => window.cancelAnimationFrame(frame);
      }
      const frame = window.requestAnimationFrame(() => setIsOpen(true));
      return () => window.cancelAnimationFrame(frame);
    }
  }, [chatId, createdChatId, rawChatId, replaceChatQuery]);

  useEffect(() => {
    if (!isOpen) {
      return;
    }
    const frame = window.requestAnimationFrame(() => closeButtonRef.current?.focus());
    return () => window.cancelAnimationFrame(frame);
  }, [isOpen]);

  useEffect(() => {
    if (!isOpen) {
      return;
    }
    document.documentElement.classList.add("agent-chat-mobile-open");
    return () => document.documentElement.classList.remove("agent-chat-mobile-open");
  }, [isOpen]);

  useEffect(() => {
    function handleEscape(event: KeyboardEvent) {
      if (event.key !== "Escape" || !isOpen) {
        return;
      }
      if (isHistoryOpen) {
        setIsHistoryOpen(false);
        return;
      }
      setIsOpen(false);
      window.requestAnimationFrame(() => launcherRef.current?.focus());
    }
    window.addEventListener("keydown", handleEscape);
    return () => window.removeEventListener("keydown", handleEscape);
  }, [isHistoryOpen, isOpen]);

  const flushTokenBuffer = useCallback(() => {
    animationFrameRef.current = null;
    if (tokenBufferRef.current.length === 0) {
      return;
    }
    const bufferedTokens = tokenBufferRef.current;
    tokenBufferRef.current = "";
    setStreamingAnswer((answer) => answer + bufferedTokens);
  }, []);

  const queueToken = useCallback(
    (token: string) => {
      tokenBufferRef.current += token;
      if (animationFrameRef.current === null) {
        animationFrameRef.current = window.requestAnimationFrame(flushTokenBuffer);
      }
    },
    [flushTokenBuffer],
  );

  useEffect(
    () => () => {
      if (animationFrameRef.current !== null) {
        window.cancelAnimationFrame(animationFrameRef.current);
      }
    },
    [],
  );

  const displayMessages = useMemo(() => {
    const pendingMessages: ChatMessage[] = [];
    const timestamp = new Date().toISOString();
    const hasPersistedPendingQuestion = messages.some(
      (message) => message.role === "user" && message.message === pendingQuestion,
    );
    const hasPersistedStreamingAnswer = messages.some(
      (message) => message.role === "assistant" && message.message === streamingAnswer,
    );
    if (pendingQuestion.length > 0 && !hasPersistedPendingQuestion) {
      pendingMessages.push({ id: -1, role: "user", message: pendingQuestion, timestamp });
    }
    if (streamingAnswer.length > 0 && !hasPersistedStreamingAnswer) {
      pendingMessages.push({ id: -2, role: "assistant", message: streamingAnswer, timestamp });
    }
    return [...messages, ...pendingMessages];
  }, [messages, pendingQuestion, streamingAnswer]);

  async function handleAsk(values: AgentQuestionFormValues) {
    setPendingQuestion(values.question);
    setStreamingAnswer("");
    setStreamingStatus("Đang kết nối...");
    setIsStreaming(true);
    tokenBufferRef.current = "";

    try {
      let currentChatId = chatId;
      let completedResponse: ChatMessageResponse | null = null;
      let streamError = "";

      if (currentChatId === null) {
        const created = await createChatMutation.mutateAsync();
        currentChatId = created.id;
        setCreatedChatId(created.id);
      }

      await requestProtectedEventStream(
        `/agent/chats/${currentChatId}/messages/stream`,
        { method: "POST", body: JSON.stringify({ question: values.question }) },
        (event) => {
          if (event.event === "token") {
            const payload = event.data as { data?: { content?: unknown } };
            if (typeof payload.data?.content === "string") {
              setStreamingStatus("");
              queueToken(payload.data.content);
            }
          } else if (event.event === "status") {
            const payload = event.data as { data?: { message?: unknown } };
            if (typeof payload.data?.message === "string") {
              setStreamingStatus(payload.data.message);
            }
          } else if (event.event === "done") {
            flushTokenBuffer();
            completedResponse = (event.data as { data?: ChatMessageResponse }).data ?? null;
          } else if (event.event === "error") {
            const errorData = event.data as { message?: unknown };
            streamError = typeof errorData.message === "string" ? errorData.message : "Luồng phản hồi bị gián đoạn.";
          }
        },
      );

      if (streamError.length > 0) {
        throw new Error(streamError);
      }
      if (completedResponse === null) {
        throw new Error("Luồng phản hồi kết thúc nhưng chưa lưu được câu trả lời.");
      }

      const result = completedResponse as ChatMessageResponse;
      const chatQueryKey = ["agent", "chats", currentChatId] as const;
      const cachedChat = queryClient.getQueryData<ChatDetail>(chatQueryKey);
      setPendingQuestion("");
      setStreamingAnswer("");
      setStreamingStatus("");
      tokenBufferRef.current = "";
      queryClient.setQueryData<ChatDetail>(chatQueryKey, {
        ...(cachedChat ?? result.chat),
        ...result.chat,
        messages: appendUniqueMessages(cachedChat?.messages ?? messages, result.user_message, result.assistant_message),
      });
      void queryClient.invalidateQueries({ predicate: isAgentChatListQuery });
      return true;
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Không thể gửi câu hỏi. Vui lòng thử lại.");
      return false;
    } finally {
      setPendingQuestion("");
      setStreamingAnswer("");
      setStreamingStatus("");
      setIsStreaming(false);
      tokenBufferRef.current = "";
      if (animationFrameRef.current !== null) {
        window.cancelAnimationFrame(animationFrameRef.current);
        animationFrameRef.current = null;
      }
    }
  }

  function handleNewChat() {
    if (isSending) {
      return;
    }
    setIsHistoryOpen(false);
    setCreatedChatId(null);
    replaceChatQuery(null);
  }

  async function handleDelete(chatIdToDelete: number) {
    if (isSending) {
      return;
    }
    try {
      await deleteChatMutation.mutateAsync(chatIdToDelete);
      queryClient.removeQueries({ queryKey: ["agent", "chats", chatIdToDelete] });
      if (chatId === chatIdToDelete) {
        replaceChatQuery(null);
      }
      await queryClient.invalidateQueries({ queryKey: ["agent", "chats"], exact: false });
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Không thể xoá cuộc trò chuyện.");
    }
  }

  function closeWidget() {
    setIsHistoryOpen(false);
    setIsOpen(false);
    window.requestAnimationFrame(() => launcherRef.current?.focus());
  }

  function toggleExpanded() {
    if (widgetRef.current !== null) {
      widgetRef.current.style.width = "";
      widgetRef.current.style.height = "";
    }
    setIsExpanded((value) => !value);
  }

  const isNotFound = chatQuery.error instanceof ApiError && chatQuery.error.status === 404;

  return (
    <>
      <button
        ref={launcherRef}
        className={cn(
          "fixed right-4 bottom-4 z-40 grid size-14 place-items-center rounded-2xl bg-primary text-primary-foreground shadow-[0_18px_55px_rgb(0_0_0/0.45)] transition hover:-translate-y-0.5 hover:bg-primary/90 focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background focus-visible:outline-none sm:right-6 sm:bottom-6",
          isOpen && "pointer-events-none scale-90 opacity-0",
        )}
        type="button"
        aria-label="Mở trợ lý AI AeroField"
        aria-expanded={isOpen}
        onClick={() => setIsOpen(true)}
      >
        <Bot className="size-6" />
      </button>

      <div
        ref={widgetRef}
        className={cn(
          "agent-chat-widget fixed z-50 overflow-hidden overscroll-contain border border-border bg-card text-foreground shadow-[0_28px_90px_rgb(0_0_0/0.58)]",
          isExpanded && "agent-chat-widget-expanded",
          !isOpen && "pointer-events-none invisible opacity-0",
        )}
        role="dialog"
        aria-label="Trợ lý AI AeroField"
        aria-hidden={!isOpen}
      >
        <header className="flex h-14 shrink-0 items-center gap-1 border-b border-border/70 bg-card/95 px-2 backdrop-blur-xl">
          <Button
            size="icon"
            variant="ghost"
            aria-label="Mở lịch sử trò chuyện"
            disabled={isSending}
            onClick={() => setIsHistoryOpen(!isHistoryOpen)}
          >
            <PanelLeft />
          </Button>
          <div className="min-w-0 flex-1 px-1">
            <p className="truncate text-sm font-bold">{activeChat?.title ?? "Cuộc trò chuyện mới"}</p>
            <p className="text-[10px] font-bold uppercase tracking-[0.14em] text-primary">AeroField intelligence</p>
          </div>
          <Button
            className="hidden sm:inline-flex"
            size="icon"
            variant="ghost"
            aria-label={isExpanded ? "Thu nhỏ cửa sổ chat" : "Mở rộng cửa sổ chat"}
            onClick={toggleExpanded}
          >
            {isExpanded ? <Minimize2 /> : <Maximize2 />}
          </Button>
          <Button
            ref={closeButtonRef}
            size="icon"
            variant="ghost"
            aria-label="Đóng trợ lý AI"
            onClick={closeWidget}
          >
            <X />
          </Button>
        </header>

        <div className="relative flex min-h-0 flex-1 overflow-hidden">
          <ChatHistoryPanel
            activeChatId={activeChatId}
            chats={chats}
            disabled={isSending}
            hasMore={chatsQuery.hasNextPage === true}
            isDeleting={deleteChatMutation.isPending}
            isLoading={chatsQuery.isLoading}
            isLoadingMore={chatsQuery.isFetchingNextPage}
            isOpen={isHistoryOpen}
            search={search}
            onClose={() => setIsHistoryOpen(false)}
            onDelete={handleDelete}
            onLoadMore={() => chatsQuery.fetchNextPage()}
            onNewChat={handleNewChat}
            onSearchChange={setSearch}
            onSelect={(selectedChatId) => {
              if (isSending) {
                return;
              }
              setIsHistoryOpen(false);
              setCreatedChatId(null);
              replaceChatQuery(selectedChatId);
            }}
          />

          {chatQuery.isLoading && chatId !== null ? (
            <WidgetState
              icon={<Spinner />}
              message="Đang tải cuộc trò chuyện..."
            />
          ) : chatQuery.isError && chatId !== null ? (
            <WidgetState
              icon={isNotFound ? <History className="size-5" /> : <RotateCcw className="size-5" />}
              message={
                isNotFound
                  ? "Không tìm thấy cuộc trò chuyện này."
                  : chatQuery.error instanceof Error
                    ? chatQuery.error.message
                    : "Không thể tải cuộc trò chuyện."
              }
              action={
                isNotFound ? (
                  <Button onClick={handleNewChat}>Tạo chat mới</Button>
                ) : (
                  <Button onClick={() => chatQuery.refetch()}>
                    <RotateCcw />
                    Thử lại
                  </Button>
                )
              }
            />
          ) : (
            <AgentQuestionPanel
              isLoading={isSending}
              messages={displayMessages}
              streamingStatus={streamingAnswer.length === 0 ? streamingStatus : ""}
              onSubmit={handleAsk}
            />
          )}
        </div>
      </div>
    </>
  );
}

function appendUniqueMessages(messages: ChatMessage[], ...nextMessages: ChatMessage[]) {
  const seenIds = new Set(messages.map((message) => message.id));
  const merged = [...messages];
  for (const message of nextMessages) {
    if (seenIds.has(message.id)) {
      continue;
    }
    seenIds.add(message.id);
    merged.push(message);
  }
  return merged;
}

function isAgentChatListQuery(query: { queryKey: readonly unknown[] }) {
  const [scope, resource, filter] = query.queryKey;
  return scope === "agent" && resource === "chats" && typeof filter === "string";
}

function WidgetState({ action, icon, message }: { action?: ReactNode; icon: ReactNode; message: string }) {
  return (
    <div className="flex min-w-0 flex-1 flex-col items-center justify-center gap-4 p-6 text-center">
      <span className="grid size-11 place-items-center rounded-xl bg-secondary text-primary">{icon}</span>
      <p className="max-w-xs text-sm leading-6 text-muted-foreground">{message}</p>
      {action}
    </div>
  );
}
