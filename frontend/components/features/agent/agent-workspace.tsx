"use client";

import { useQueryClient } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useState } from "react";
import { AgentQuestionPanel } from "@/components/features/agent/agent-question-panel";
import { SessionPanel } from "@/components/features/agent/session-panel";
import { useAgentAskMutation, useCurrentUserQuery, useLogoutMutation } from "@/lib/api-hooks";
import { ApiError } from "@/lib/api-client";
import { formatTimeLeft, readSession, sessionTimeLeft } from "@/lib/auth-client";
import { useAuthStore } from "@/lib/auth-store";
import type { AgentQuestionFormValues } from "@/lib/validation";

export function AgentWorkspace() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const [answer, setAnswer] = useState("");
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const { clearAuth, isBooting, session, setBooting, setSession, setUser, user } = useAuthStore();
  const currentUserQuery = useCurrentUserQuery(session);
  const logoutMutation = useLogoutMutation();
  const agentAskMutation = useAgentAskMutation();

  const accessTimeLeft = useMemo(() => formatTimeLeft(sessionTimeLeft(session, "access")), [session]);
  const refreshTimeLeft = useMemo(() => formatTimeLeft(sessionTimeLeft(session, "refresh")), [session]);

  const resetAuthState = useCallback(
    (notice?: string) => {
      clearAuth();
      queryClient.removeQueries({ queryKey: ["auth"] });
      setAnswer("");
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
    if (session === null || currentUserQuery.error === null) {
      return;
    }

    const timeoutId = window.setTimeout(() => {
      resetAuthState("Phiên đăng nhập đã hết hạn. Vui lòng đăng nhập lại.");
      setBooting(false);
    }, 0);

    return () => {
      window.clearTimeout(timeoutId);
    };
  }, [currentUserQuery.error, resetAuthState, session, setBooting]);

  async function handleAsk(values: AgentQuestionFormValues) {
    if (session === null) {
      setError("Vui lòng đăng nhập trước khi hỏi AI Agent.");
      return;
    }

    setError("");
    setMessage("");
    setAnswer("");

    try {
      const result = await agentAskMutation.mutateAsync({
        body: { question: values.question },
        session,
      });
      setSession(result.session);
      setAnswer(result.data.answer);
    } catch (apiError) {
      if (apiError instanceof ApiError && apiError.status === 401) {
        resetAuthState("Phiên đăng nhập đã hết hạn. Vui lòng đăng nhập lại.");
        return;
      }

      setError(apiError instanceof Error ? apiError.message : "Không thể gửi câu hỏi. Vui lòng thử lại.");
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
      // Client session must be cleared even if server-side revoke cannot complete.
    } finally {
      resetAuthState("Bạn đã đăng xuất.");
    }
  }

  if (isBooting) {
    return (
      <main className="flex min-h-screen items-center justify-center bg-[#f7f4ef] px-4 text-[#1b1f1d]">
        <p className="text-sm font-medium">Đang kiểm tra phiên đăng nhập...</p>
      </main>
    );
  }

  if (session !== null && user === null) {
    return (
      <main className="flex min-h-screen items-center justify-center bg-[#f7f4ef] px-4 text-[#1b1f1d]">
        <p className="text-sm font-medium">Đang tải hồ sơ người dùng...</p>
      </main>
    );
  }

  if (session === null || user === null) {
    return (
      <main className="flex min-h-screen items-center justify-center bg-[#f7f4ef] px-4 text-[#1b1f1d]">
        <p className="text-sm font-medium">Đang chuyển tới trang đăng nhập...</p>
      </main>
    );
  }

  return (
    <main className="min-h-screen overflow-x-hidden bg-[#f7f4ef] text-[#1b1f1d]">
      <section className="mx-auto flex min-h-screen w-full max-w-6xl flex-col gap-6 px-4 py-5 sm:px-6 sm:py-8 lg:px-8">
        <header className="flex flex-col gap-2 border-b border-[#d8d2c7] pb-5 sm:flex-row sm:items-end sm:justify-between">
          <div>
            <p className="text-sm font-semibold uppercase tracking-[0.12em] text-[#456b58]">Autonomous Drones</p>
            <h1 className="mt-2 text-3xl font-semibold text-[#1d2b24] sm:text-4xl">Trợ lý nông nghiệp AI</h1>
          </div>
          <p className="max-w-xl text-sm leading-6 text-[#526158]">
            Đăng nhập để hỏi AI Agent về thời tiết, thị trường và phân tích mùa vụ từ backend FastAPI.
          </p>
        </header>

        {(message.length > 0 || error.length > 0) && (
          <div
            className={`rounded-xl border px-4 py-3 text-sm ${
              error.length > 0
                ? "border-[#c45d4c] bg-[#fff3ef] text-[#7e2416]"
                : "border-[#8aa892] bg-[#eef7ef] text-[#235035]"
            }`}
            role={error.length > 0 ? "alert" : "status"}
          >
            {error.length > 0 ? error : message}
          </div>
        )}

        <section className="grid flex-1 gap-5 lg:grid-cols-[320px_minmax(0,1fr)]">
          <SessionPanel
            accessTimeLeft={accessTimeLeft}
            isLoading={logoutMutation.isPending}
            refreshTimeLeft={refreshTimeLeft}
            user={user}
            onLogout={handleLogout}
          />
          <AgentQuestionPanel
            answer={answer}
            isLoading={agentAskMutation.isPending}
            onSubmit={handleAsk}
          />
        </section>
      </section>
    </main>
  );
}
