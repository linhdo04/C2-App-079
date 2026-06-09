"use client";

import { useQueryClient } from "@tanstack/react-query";
import { Activity, Radar } from "lucide-react";
import { useRouter } from "next/navigation";
import { useCallback, useDeferredValue, useEffect, useMemo, useState } from "react";
import { AgentQuestionPanel } from "@/components/features/agent/agent-question-panel";
import { ChatHistoryPanel } from "@/components/features/agent/chat-history-panel";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Spinner } from "@/components/ui/spinner";
import {
  useChatQuery,
  useChatsQuery,
  useCreateChatMutation,
  useCurrentUserQuery,
  useDeleteChatMutation,
  useLogoutMutation,
  useSendChatMessageMutation,
} from "@/lib/api-hooks";
import { ApiError } from "@/lib/api-client";
import { readSession } from "@/lib/auth-client";
import { useAuthStore } from "@/lib/auth-store";
import type { AgentQuestionFormValues } from "@/lib/validation";
import type { StoredSession } from "@/types/auth";

export function AgentWorkspace() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const [activeChatId, setActiveChatId] = useState<number | null>(null);
  const [error, setError] = useState("");
  const [isCreatingNew, setIsCreatingNew] = useState(false);
  const [isHistoryOpen, setIsHistoryOpen] = useState(false);
  const [message, setMessage] = useState("");
  const [search, setSearch] = useState("");
  const deferredSearch = useDeferredValue(search);
  const { clearAuth, isBooting, session, setBooting, setSession, setUser, user } = useAuthStore();
  const currentUserQuery = useCurrentUserQuery(session);
  const chatsQuery = useChatsQuery(session, deferredSearch);
  const chats = useMemo(() => chatsQuery.data?.data ?? [], [chatsQuery.data?.data]);
  const selectedChatId = activeChatId ?? (!isCreatingNew ? (chats[0]?.id ?? null) : null);
  const chatQuery = useChatQuery(session, selectedChatId);
  const createChatMutation = useCreateChatMutation();
  const deleteChatMutation = useDeleteChatMutation();
  const logoutMutation = useLogoutMutation();
  const sendMessageMutation = useSendChatMessageMutation();

  const activeChat = chatQuery.data?.data;
  const messages = activeChat?.messages ?? [];
  const isSending = createChatMutation.isPending || sendMessageMutation.isPending;
  const queryError = chatsQuery.error ?? chatQuery.error;

  const resetAuthState = useCallback(
    (notice?: string) => {
      clearAuth();
      queryClient.removeQueries({ queryKey: ["auth"] });
      queryClient.removeQueries({ queryKey: ["agent"] });
      setActiveChatId(null);
      if (notice !== undefined) {
        setMessage(notice);
      }
    },
    [clearAuth, queryClient],
  );

  useEffect(() => {
    const storedSession = readSession();
    if (storedSession === null) {
      clearAuth();
      setBooting(false);
      return;
    }

    setSession(storedSession);
  }, [clearAuth, setBooting, setSession]);

  useEffect(() => {
    if (isBooting || session !== null) {
      return;
    }

    router.replace("/login");
  }, [isBooting, router, session]);

  useEffect(() => {
    if (currentUserQuery.data === undefined) {
      return;
    }

    setSession(currentUserQuery.data.session);
    setUser(currentUserQuery.data.data);
    setBooting(false);
  }, [currentUserQuery.data, setBooting, setSession, setUser]);

  useEffect(() => {
    const refreshedSession = chatQuery.data?.session ?? chatsQuery.data?.session;
    if (refreshedSession !== undefined) {
      setSession(refreshedSession);
    }
  }, [chatQuery.data?.session, chatsQuery.data?.session, setSession]);

  useEffect(() => {
    if (session === null || currentUserQuery.error === null) {
      return;
    }

    const timeoutId = window.setTimeout(() => {
      resetAuthState("Phiên đăng nhập đã hết hạn. Vui lòng đăng nhập lại.");
      setBooting(false);
    }, 0);

    return () => window.clearTimeout(timeoutId);
  }, [currentUserQuery.error, resetAuthState, session, setBooting]);

  useEffect(() => {
    if (queryError === null || queryError === undefined) {
      return;
    }

    const timeoutId = window.setTimeout(() => {
      if (queryError instanceof ApiError && queryError.status === 401) {
        resetAuthState("Phiên đăng nhập đã hết hạn. Vui lòng đăng nhập lại.");
        return;
      }
      setError(queryError instanceof Error ? queryError.message : "Không thể tải lịch sử trò chuyện.");
    }, 0);

    return () => window.clearTimeout(timeoutId);
  }, [queryError, resetAuthState]);

  async function handleAsk(values: AgentQuestionFormValues) {
    if (session === null) {
      setError("Vui lòng đăng nhập trước khi hỏi AI Agent.");
      return false;
    }

    setError("");
    setMessage("");

    try {
      let currentSession: StoredSession = session;
      let chatId = selectedChatId;

      if (chatId === null) {
        const created = await createChatMutation.mutateAsync(currentSession);
        currentSession = created.session;
        chatId = created.data.id;
        setSession(currentSession);
        setActiveChatId(chatId);
        setIsCreatingNew(false);
      }

      const result = await sendMessageMutation.mutateAsync({
        body: { question: values.question },
        chatId,
        session: currentSession,
      });
      setSession(result.session);
      queryClient.setQueryData(["agent", "chats", chatId], {
        data: {
          ...result.data.chat,
          messages: [...messages, result.data.user_message, result.data.assistant_message],
        },
        session: result.session,
      });
      await queryClient.invalidateQueries({ queryKey: ["agent", "chats"], exact: false });
      return true;
    } catch (apiError) {
      if (apiError instanceof ApiError && apiError.status === 401) {
        resetAuthState("Phiên đăng nhập đã hết hạn. Vui lòng đăng nhập lại.");
      } else {
        setError(apiError instanceof Error ? apiError.message : "Không thể gửi câu hỏi. Vui lòng thử lại.");
      }
      return false;
    }
  }

  function handleNewChat() {
    setActiveChatId(null);
    setIsCreatingNew(true);
    setIsHistoryOpen(false);
    setError("");
  }

  async function handleDelete(chatId: number) {
    if (session === null || !window.confirm("Bạn có chắc muốn xoá cuộc trò chuyện này?")) {
      return;
    }

    setError("");
    try {
      const result = await deleteChatMutation.mutateAsync({ chatId, session });
      setSession(result.session);
      queryClient.removeQueries({ queryKey: ["agent", "chats", chatId] });
      if (selectedChatId === chatId) {
        const nextChat = chats.find((chat) => chat.id !== chatId);
        setActiveChatId(nextChat?.id ?? null);
        setIsCreatingNew(nextChat === undefined);
      }
      await queryClient.invalidateQueries({ queryKey: ["agent", "chats"], exact: false });
    } catch (apiError) {
      setError(apiError instanceof Error ? apiError.message : "Không thể xoá cuộc trò chuyện.");
    }
  }

  async function handleLogout() {
    if (session === null) {
      resetAuthState();
      return;
    }

    setError("");
    setMessage("");
    try {
      await logoutMutation.mutateAsync(session);
    } catch {
      // Clear the local session even if server-side revoke cannot complete.
    } finally {
      resetAuthState("Bạn đã đăng xuất.");
    }
  }

  const loadingLabel = useMemo(() => {
    if (isBooting) return "Đang kiểm tra phiên đăng nhập...";
    if (session !== null && user === null) return "Đang tải hồ sơ người dùng...";
    return "Đang chuyển tới trang đăng nhập...";
  }, [isBooting, session, user]);

  if (isBooting || (session !== null && user === null) || session === null || user === null) {
    return (
      <main className="app-shell flex min-h-screen items-center justify-center px-4 text-foreground">
        <p className="flex items-center gap-2 text-sm font-medium">
          <Spinner />
          {loadingLabel}
        </p>
      </main>
    );
  }

  return (
    <main className="app-shell relative min-h-screen overflow-x-hidden text-foreground">
      <div className="grid-surface pointer-events-none absolute inset-0" />
      <section className="relative mx-auto flex min-h-screen w-full max-w-[1440px] flex-col gap-5 px-4 py-5 sm:px-6 sm:py-7 lg:px-8">
        <header className="flex items-center justify-between gap-4 border-b border-border/60 pb-5">
          <div className="flex items-center gap-3">
            <span className="grid size-10 place-items-center rounded-xl bg-primary text-primary-foreground">
              <Radar className="size-5" />
            </span>
            <div>
              <p className="text-lg font-bold tracking-[-0.03em]">AeroField</p>
              <p className="eyebrow mt-0.5 text-muted-foreground">Command center</p>
            </div>
          </div>
          <div className="hidden items-center gap-2 rounded-full border border-success/20 bg-success-muted px-3 py-2 sm:flex">
            <Activity className="size-3.5 text-success" />
            <span className="eyebrow text-success-foreground">Systems operational</span>
          </div>
        </header>

        {(message.length > 0 || error.length > 0) && (
          <Alert
            variant={error.length > 0 ? "destructive" : "success"}
            role={error.length > 0 ? "alert" : "status"}
          >
            <AlertDescription>{error.length > 0 ? error : message}</AlertDescription>
          </Alert>
        )}

        <section className="grid flex-1 gap-4 lg:grid-cols-[310px_minmax(0,1fr)]">
          <ChatHistoryPanel
            activeChatId={selectedChatId}
            chats={chats}
            isDeleting={deleteChatMutation.isPending}
            isLoading={chatsQuery.isLoading}
            isOpen={isHistoryOpen}
            search={search}
            user={user}
            onClose={() => setIsHistoryOpen(false)}
            onDelete={handleDelete}
            onLogout={handleLogout}
            onNewChat={handleNewChat}
            onOpen={() => setIsHistoryOpen(true)}
            onSearchChange={setSearch}
            onSelect={(chatId) => {
              setActiveChatId(chatId);
              setIsCreatingNew(false);
              setIsHistoryOpen(false);
            }}
          />
          {chatQuery.isLoading && selectedChatId !== null ? (
            <div className="flex min-h-[680px] items-center justify-center rounded-2xl border border-border bg-card/90">
              <p className="flex items-center gap-2 text-sm text-muted-foreground">
                <Spinner />
                Đang tải cuộc trò chuyện...
              </p>
            </div>
          ) : (
            <AgentQuestionPanel
              isLoading={isSending}
              messages={messages}
              title={activeChat?.title ?? null}
              onSubmit={handleAsk}
            />
          )}
        </section>
      </section>
    </main>
  );
}
