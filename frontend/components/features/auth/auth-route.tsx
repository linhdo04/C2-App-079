"use client";

import { useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, Bot, CloudSun, Radar, ShieldCheck } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { AuthPanel } from "@/components/features/auth/auth-panel";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Spinner } from "@/components/ui/spinner";
import { useCurrentUserQuery, useLoginMutation, useRegisterMutation } from "@/lib/api-hooks";
import { hasAuthSession, saveSession } from "@/lib/auth-client";
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
  const { authStatus, clearAuth, setAuthenticated, setBooting, setUser } = useAuthStore();
  const isAuthenticated = authStatus === "authenticated";
  const currentUserQuery = useCurrentUserQuery(isAuthenticated);
  const registerMutation = useRegisterMutation();
  const loginMutation = useLoginMutation();
  const isLoading = registerMutation.isPending || loginMutation.isPending;
  const isCheckingSession = isAuthenticated && currentUserQuery.isFetching;
  const alternateMode = mode === "login" ? "register" : "login";

  useEffect(() => {
    if (!hasAuthSession()) {
      clearAuth();
      setBooting(false);
      return;
    }

    setAuthenticated(true);
  }, [clearAuth, setAuthenticated, setBooting]);

  useEffect(() => {
    if (currentUserQuery.data === undefined) {
      return;
    }

    setUser(currentUserQuery.data);
    setBooting(false);
    router.replace("/agent");
  }, [currentUserQuery.data, router, setBooting, setUser]);

  useEffect(() => {
    if (!isAuthenticated || currentUserQuery.error === null) {
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
  }, [clearAuth, currentUserQuery.error, isAuthenticated, queryClient, setBooting]);

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
      saveSession(tokenResponse);
      queryClient.removeQueries({ queryKey: ["auth"] });
      setAuthenticated(true);
      setMessage(mode === "register" ? "Tài khoản đã được tạo. Đang mở workspace..." : "Đăng nhập thành công.");
    } catch (apiError) {
      setError(apiError instanceof Error ? apiError.message : "Không thể xử lý yêu cầu. Vui lòng thử lại.");
    }
  }

  return (
    <main className="app-shell relative min-h-screen overflow-hidden text-foreground">
      <div className="grid-surface pointer-events-none absolute inset-0" />
      <section className="relative mx-auto grid min-h-screen w-full max-w-7xl gap-12 px-4 py-5 sm:px-6 sm:py-8 lg:grid-cols-[minmax(0,1fr)_minmax(380px,0.75fr)] lg:px-8">
        <div className="flex flex-col justify-between gap-12">
          <Button
            asChild
            variant="ghost"
            className="w-fit px-0 hover:bg-transparent hover:text-primary"
          >
            <Link href="/">
              <ArrowLeft />
              <span className="flex items-center gap-2">
                <Radar className="size-5 text-primary" />
                <strong>AeroField</strong>
              </span>
            </Link>
          </Button>

          <div className="reveal max-w-2xl">
            <p className="eyebrow text-primary">
              {mode === "register" ? "Create operator account" : "Operator access"}
            </p>
            <h1 className="text-balance mt-5 text-4xl font-bold leading-[1.02] tracking-[-0.045em] sm:text-6xl">
              {mode === "register" ? "Khởi tạo trung tâm vận hành của bạn." : "Tiếp tục phiên điều phối thông minh."}
            </h1>
            <p className="mt-6 max-w-xl text-base leading-7 text-muted-foreground">
              Truy cập AI Agent để tổng hợp tín hiệu thời tiết, mùa vụ và thị trường trong một luồng làm việc bảo mật.
            </p>
            <div className="mt-10 grid gap-3 sm:grid-cols-3">
              <Feature
                icon={Bot}
                label="AI insights"
              />
              <Feature
                icon={CloudSun}
                label="Live context"
              />
              <Feature
                icon={ShieldCheck}
                label="Secure session"
              />
            </div>
          </div>

          <p className="max-w-xl text-sm leading-6 text-muted-foreground">
            {mode === "register" ? "Đã có tài khoản?" : "Chưa có tài khoản?"}{" "}
            <Button
              asChild
              variant="link"
              className="inline-flex"
            >
              <Link href={`/${alternateMode}`}>{mode === "register" ? "Đăng nhập" : "Đăng ký"}</Link>
            </Button>
          </p>
        </div>

        <div className="flex items-center lg:py-12">
          <div className="reveal reveal-delay-1 w-full">
            <div className="mb-6">
              <p className="eyebrow text-muted-foreground">{mode === "register" ? "New account" : "Welcome back"}</p>
              <h2 className="mt-2 text-2xl font-bold tracking-[-0.03em]">
                {mode === "register" ? "Tạo tài khoản" : "Đăng nhập"}
              </h2>
            </div>
            {(message.length > 0 || error.length > 0) && (
              <Alert
                className="mb-4"
                variant={error.length > 0 ? "destructive" : "success"}
                role={error.length > 0 ? "alert" : "status"}
              >
                <AlertDescription>{error.length > 0 ? error : message}</AlertDescription>
              </Alert>
            )}

            {isCheckingSession ? (
              <Card>
                <CardContent className="flex items-center gap-2 p-4 text-sm font-medium text-muted-foreground sm:p-6">
                  <Spinner />
                  Đang kiểm tra phiên đăng nhập...
                </CardContent>
              </Card>
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

type FeatureProps = {
  icon: typeof Bot;
  label: string;
};

function Feature({ icon: Icon, label }: FeatureProps) {
  return (
    <div className="flex items-center gap-3 rounded-xl border border-border/70 bg-card/40 px-4 py-3">
      <Icon className="size-4 text-primary" />
      <span className="text-xs font-bold text-secondary-foreground">{label}</span>
    </div>
  );
}
