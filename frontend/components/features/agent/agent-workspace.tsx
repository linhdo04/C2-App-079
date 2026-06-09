"use client";

import { useQueryClient } from "@tanstack/react-query";
import { Activity, Radar } from "lucide-react";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useState } from "react";
import { AgentQuestionPanel } from "@/components/features/agent/agent-question-panel";
import { SessionPanel } from "@/components/features/auth/session-panel";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Spinner } from "@/components/ui/spinner";
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
      <main className="app-shell flex min-h-screen items-center justify-center px-4 text-foreground">
        <p className="flex items-center gap-2 text-sm font-medium">
          <Spinner />
          Đang kiểm tra phiên đăng nhập...
        </p>
      </main>
    );
  }

  if (session !== null && user === null) {
    return (
      <main className="app-shell flex min-h-screen items-center justify-center px-4 text-foreground">
        <p className="flex items-center gap-2 text-sm font-medium">
          <Spinner />
          Đang tải hồ sơ người dùng...
        </p>
      </main>
    );
  }

  if (session === null || user === null) {
    return (
      <main className="app-shell flex min-h-screen items-center justify-center px-4 text-foreground">
        <p className="flex items-center gap-2 text-sm font-medium">
          <Spinner />
          Đang chuyển tới trang đăng nhập...
        </p>
      </main>
    );
  }

  return (
    <main className="app-shell relative min-h-screen overflow-x-hidden text-foreground">
      <div className="grid-surface pointer-events-none absolute inset-0" />
      <section className="relative mx-auto flex min-h-screen w-full max-w-7xl flex-col gap-6 px-4 py-5 sm:px-6 sm:py-7 lg:px-8">
        <header className="flex flex-col gap-5 border-b border-border/60 pb-5 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex items-center gap-3">
            <span className="grid size-10 place-items-center rounded-xl bg-primary text-primary-foreground">
              <Radar className="size-5" />
            </span>
            <div>
              <p className="text-lg font-bold tracking-[-0.03em]">AeroField</p>
              <p className="eyebrow mt-0.5 text-muted-foreground">Command center</p>
            </div>
          </div>
          <div className="flex w-fit items-center gap-2 rounded-full border border-success/20 bg-success-muted px-3 py-2">
            <Activity className="size-3.5 text-success" />
            <span className="eyebrow text-success-foreground">Systems operational</span>
          </div>
        </header>

        <div>
          <p className="eyebrow text-primary">AI workspace</p>
          <h1 className="mt-2 text-3xl font-bold tracking-[-0.04em] sm:text-4xl">Trung tâm điều phối nông nghiệp</h1>
          <p className="mt-2 max-w-2xl text-sm leading-6 text-muted-foreground">
            Phân tích bối cảnh vận hành và chuyển dữ liệu thành hành động rõ ràng.
          </p>
        </div>

        {(message.length > 0 || error.length > 0) && (
          <Alert
            variant={error.length > 0 ? "destructive" : "success"}
            role={error.length > 0 ? "alert" : "status"}
          >
            <AlertDescription>{error.length > 0 ? error : message}</AlertDescription>
          </Alert>
        )}

        <section className="grid flex-1 gap-5 lg:grid-cols-[280px_minmax(0,1fr)]">
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
