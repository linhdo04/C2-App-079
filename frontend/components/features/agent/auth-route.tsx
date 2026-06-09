"use client";

import { useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { AuthPanel } from "@/components/features/agent/auth-panel";
import { useCurrentUserQuery, useLoginMutation, useRegisterMutation } from "@/lib/api-hooks";
import { readSession, saveSession } from "@/lib/auth-client";
import { useAuthStore } from "@/lib/auth-store";
import type { AuthFormValues } from "@/lib/validation";
import type { AuthMode } from "@/types/auth";

type AuthRouteProps = {
  mode: AuthMode;
};

export function AuthRoute({ mode }: AuthRouteProps) {
  const router = useRouter();
  const queryClient = useQueryClient();
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const { clearAuth, session, setBooting, setSession, setUser } = useAuthStore();
  const currentUserQuery = useCurrentUserQuery(session);
  const registerMutation = useRegisterMutation();
  const loginMutation = useLoginMutation();
  const isLoading = registerMutation.isPending || loginMutation.isPending;
  const isCheckingSession = session !== null && currentUserQuery.isFetching;
  const alternateMode = mode === "login" ? "register" : "login";

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
    if (currentUserQuery.data === undefined) {
      return;
    }

    setSession(currentUserQuery.data.session);
    setUser(currentUserQuery.data.data);
    setBooting(false);
    router.replace("/agent");
  }, [currentUserQuery.data, router, setBooting, setSession, setUser]);

  useEffect(() => {
    if (session === null || currentUserQuery.error === null) {
      return;
    }

    const timeoutId = window.setTimeout(() => {
      clearAuth();
      queryClient.removeQueries({ queryKey: ["auth"] });
      setBooting(false);
      setMessage("Phiên đăng nhập đã hết hạn. Vui lòng đăng nhập lại.");
    }, 0);

    return () => {
      window.clearTimeout(timeoutId);
    };
  }, [clearAuth, currentUserQuery.error, queryClient, session, setBooting]);

  async function handleSubmit(values: AuthFormValues) {
    setError("");
    setMessage("");

    try {
      if (mode === "register") {
        await registerMutation.mutateAsync({
          name: values.name ?? "",
          email: values.email,
          password: values.password,
        });
      }

      const tokenResponse = await loginMutation.mutateAsync({
        email: values.email,
        password: values.password,
      });
      const nextSession = saveSession(tokenResponse);
      setSession(nextSession);
      setMessage(mode === "register" ? "Tài khoản đã được tạo. Đang mở workspace..." : "Đăng nhập thành công.");
    } catch (apiError) {
      setError(apiError instanceof Error ? apiError.message : "Không thể xử lý yêu cầu. Vui lòng thử lại.");
    }
  }

  return (
    <main className="min-h-screen overflow-x-hidden bg-[#f7f4ef] text-[#1b1f1d]">
      <section className="mx-auto grid min-h-screen w-full max-w-6xl gap-8 px-4 py-5 sm:px-6 sm:py-8 lg:grid-cols-[minmax(0,0.9fr)_minmax(360px,1fr)] lg:px-8">
        <div className="flex flex-col justify-between gap-10">
          <Link
            className="w-fit text-sm font-semibold text-[#456b58] transition hover:text-[#1d2b24]"
            href="/"
          >
            ← Autonomous Drones
          </Link>

          <div className="max-w-2xl">
            <p className="text-sm font-semibold uppercase tracking-[0.12em] text-[#456b58]">
              {mode === "register" ? "Tạo tài khoản" : "Đăng nhập"}
            </p>
            <h1 className="mt-3 text-3xl font-semibold leading-tight text-[#1d2b24] sm:text-5xl">
              {mode === "register" ? "Bắt đầu phiên làm việc với AI Agent." : "Mở workspace điều phối nông nghiệp."}
            </h1>
            <p className="mt-4 text-base leading-7 text-[#526158]">
              Frontend lưu token cục bộ bằng khóa hiện tại, tự refresh access token qua backend FastAPI và dùng phiên
              đăng nhập đó cho các câu hỏi gửi tới AI Agent.
            </p>
          </div>

          <p className="max-w-xl text-sm leading-6 text-[#526158]">
            {mode === "register" ? "Đã có tài khoản?" : "Chưa có tài khoản?"}{" "}
            <Link
              className="font-semibold text-[#2f5d48] underline-offset-4 hover:underline"
              href={`/${alternateMode}`}
            >
              {mode === "register" ? "Đăng nhập" : "Đăng ký"}
            </Link>
          </p>
        </div>

        <div className="flex items-center">
          <div className="w-full">
            {(message.length > 0 || error.length > 0) && (
              <div
                className={`mb-4 rounded-xl border px-4 py-3 text-sm ${
                  error.length > 0
                    ? "border-[#c45d4c] bg-[#fff3ef] text-[#7e2416]"
                    : "border-[#8aa892] bg-[#eef7ef] text-[#235035]"
                }`}
                role={error.length > 0 ? "alert" : "status"}
              >
                {error.length > 0 ? error : message}
              </div>
            )}

            {isCheckingSession ? (
              <div className="rounded-2xl border border-[#d8d2c7] bg-white p-4 text-sm font-medium text-[#526158] shadow-sm sm:p-6">
                Đang kiểm tra phiên đăng nhập...
              </div>
            ) : (
              <AuthPanel
                isLoading={isLoading}
                mode={mode}
                onModeChange={(nextMode) => router.push(`/${nextMode}`)}
                onSubmit={handleSubmit}
              />
            )}
          </div>
        </div>
      </section>
    </main>
  );
}
