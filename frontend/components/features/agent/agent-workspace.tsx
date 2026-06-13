"use client";

import { useQueryClient } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { useCallback, useDeferredValue, useEffect, useMemo, useRef, useState } from "react";
import { AgentQuestionPanel } from "@/components/features/agent/agent-question-panel";
import { ChatHistoryPanel } from "@/components/features/agent/chat-history-panel";
import { Spinner } from "@/components/ui/spinner";
import {
  useChatQuery,
  useChatsQuery,
  useCreateChatMutation,
  useDeleteChatMutation,
  useLogoutMutation,
} from "@/lib/api-hooks";
import { requestProtectedEventStream } from "@/lib/api-client";
import type { AgentQuestionFormValues } from "@/lib/validation";
import type { ChatMessage, ChatMessageResponse } from "@/types/agent";
import { toast } from "sonner";
import { PublicRouter } from "@/enums/public-routers";
import { useAuthStore } from "@/lib/auth-store";

type AgentWorkspaceProps = {
  chatId?: number | null;
};

export function AgentWorkspace({ chatId = null }: AgentWorkspaceProps) {
  const router = useRouter();
  const queryClient = useQueryClient();
  const [isHistoryOpen, setIsHistoryOpen] = useState(false);
  const [pendingQuestion, setPendingQuestion] = useState("");
  const [search, setSearch] = useState("");
  const [streamingAnswer, setStreamingAnswer] = useState("");
  const [streamingStatus, setStreamingStatus] = useState("");
  const [isStreaming, setIsStreaming] = useState(false);
  const tokenBufferRef = useRef("");
  const animationFrameRef = useRef<number | null>(null);
  const deferredSearch = useDeferredValue(search);
  const chatsQuery = useChatsQuery(deferredSearch);
  const chats = useMemo(() => chatsQuery.data?.pages.flatMap((page) => page.data) ?? [], [chatsQuery.data]);
  const chatQuery = useChatQuery(chatId);
  const createChatMutation = useCreateChatMutation();
  const deleteChatMutation = useDeleteChatMutation();
  const logoutMutation = useLogoutMutation();
  const { clearAuth } = useAuthStore();

  const activeChat = chatQuery.data;
  const messages = useMemo(() => activeChat?.messages ?? [], [activeChat?.messages]);
  const displayMessages = useMemo(() => {
    const pendingMessages: ChatMessage[] = [];
    const timestamp = new Date().toISOString();
    if (pendingQuestion.length > 0) {
      pendingMessages.push({
        id: -1,
        role: "user",
        message: pendingQuestion,
        timestamp,
      });
    }
    if (streamingAnswer.length > 0) {
      pendingMessages.push({
        id: -2,
        role: "assistant",
        message: streamingAnswer,
        timestamp,
      });
    }
    return [...messages, ...pendingMessages];
  }, [messages, pendingQuestion, streamingAnswer]);
  const isSending = createChatMutation.isPending || isStreaming;

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
      }

      await requestProtectedEventStream(
        `/agent/chats/${currentChatId}/messages/stream`,
        {
          method: "POST",
          body: JSON.stringify({ question: values.question }),
        },
        (event) => {
          if (event.event === "token") {
            const payload = event.data as { data?: { content?: unknown } };
            const token = payload.data;
            if (typeof token?.content === "string") {
              setStreamingStatus("");
              queueToken(token.content);
            }
          } else if (event.event === "status") {
            const payload = event.data as { data?: { message?: unknown } };
            const status = payload.data;
            if (typeof status?.message === "string") {
              setStreamingStatus(status.message);
            }
          } else if (event.event === "done") {
            flushTokenBuffer();
            const payload = event.data as { data?: ChatMessageResponse };
            completedResponse = payload.data ?? null;
          } else if (event.event === "error") {
            const streamErrorData = event.data as { message?: unknown };
            streamError =
              typeof streamErrorData.message === "string" ? streamErrorData.message : "Luồng phản hồi bị gián đoạn.";
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
      queryClient.setQueryData(["agent", "chats", currentChatId], {
        ...result.chat,
        messages: [...messages, result.user_message, result.assistant_message],
      });
      await queryClient.invalidateQueries({ queryKey: ["agent", "chats"], exact: false });
      if (chatId === null) {
        router.replace(`/agent/${currentChatId}`);
      }
      return true;
    } catch (apiError) {
      toast.error(apiError instanceof Error ? apiError.message : "Không thể gửi câu hỏi. Vui lòng thử lại.");
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
    setIsHistoryOpen(false);
    router.push("/agent");
  }

  async function handleDelete(chatIdToDelete: number) {
    try {
      await deleteChatMutation.mutateAsync(chatIdToDelete);
      queryClient.removeQueries({ queryKey: ["agent", "chats", chatIdToDelete] });
      if (chatId === chatIdToDelete) {
        router.replace("/agent");
      }
      await queryClient.invalidateQueries({ queryKey: ["agent", "chats"], exact: false });
    } catch (apiError) {
      toast.error(apiError instanceof Error ? apiError.message : "Không thể xoá cuộc trò chuyện.");
    }
  }

  async function handleLogout() {
    try {
      await logoutMutation.mutateAsync();
      router.push(PublicRouter.Home);
      clearAuth();
      toast.success("Bạn đã đăng xuất thành công.");
    } catch {
      toast.error("Cố lỗi xảy ra, vui lòng thử lại sau.");
    }
  }

  return (
    <main className="app-shell relative flex h-dvh overflow-hidden text-foreground">
      <div className="grid-surface pointer-events-none absolute inset-0" />
      <ChatHistoryPanel
        activeChatId={chatId}
        chats={chats}
        isDeleting={deleteChatMutation.isPending}
        hasMore={chatsQuery.hasNextPage === true}
        isLoading={chatsQuery.isLoading}
        isLoadingMore={chatsQuery.isFetchingNextPage}
        isOpen={isHistoryOpen}
        search={search}
        onClose={() => setIsHistoryOpen(false)}
        onDelete={handleDelete}
        onLogout={handleLogout}
        onLoadMore={() => chatsQuery.fetchNextPage()}
        onNewChat={handleNewChat}
        onOpen={() => setIsHistoryOpen(true)}
        onSearchChange={setSearch}
        onSelect={(selectedChatId) => {
          setIsHistoryOpen(false);
          router.push(`/agent/${selectedChatId}`);
        }}
      />

      {chatQuery.isLoading && chatId !== null ? (
        <div className="relative flex min-w-0 flex-1 items-center justify-center bg-background/55">
          <p className="flex items-center gap-2 text-sm text-muted-foreground">
            <Spinner />
            Đang tải cuộc trò chuyện...
          </p>
        </div>
      ) : (
        <AgentQuestionPanel
          key={chatId ?? "new"}
          isLoading={isSending}
          messages={displayMessages}
          streamingStatus={streamingAnswer.length === 0 ? streamingStatus : ""}
          title={activeChat?.title ?? null}
          onSubmit={handleAsk}
        />
      )}
    </main>
  );
}
