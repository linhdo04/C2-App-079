"use client";

import { useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, Bot, CloudSun, Radar, ShieldCheck } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { AuthPanel } from "@/components/features/auth/auth-panel";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Spinner } from "@/components/ui/spinner";
import { useLoginMutation } from "@/lib/api-hooks";
import { saveSession } from "@/lib/auth-client";
import { useAuthStore } from "@/lib/auth-store";
import type { AuthFormValues } from "@/lib/validation";
import { toast } from "sonner";

export function AuthRoute() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const authStatus = useAuthStore((state) => state.authStatus);
  const setAuthenticated = useAuthStore((state) => state.setAuthenticated);
  const isAuthenticated = authStatus === "authenticated";
  const loginMutation = useLoginMutation();
  const isLoading = loginMutation.isPending;

  async function handleSubmit(values: AuthFormValues) {
    try {
      const tokenResponse = await loginMutation.mutateAsync({
        email: values.email,
        password: values.password,
      });
      saveSession(tokenResponse);
      setAuthenticated(true);
      queryClient.removeQueries({ queryKey: ["auth"] });
      await queryClient.invalidateQueries({ queryKey: ["auth"] });
      toast.info("Đăng nhập thành công.");
      router.replace("/dashboard");
    } catch (apiError) {
      toast.error(apiError instanceof Error ? apiError.message : "Không thể xử lý yêu cầu. Vui lòng thử lại.");
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
            <p className="eyebrow text-primary">Operator access</p>
            <h1 className="text-balance mt-5 text-4xl font-bold leading-[1.02] tracking-[-0.045em] sm:text-6xl">
              Tiếp tục phiên điều phối thông minh.
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
            Chưa có tài khoản? Vui lòng liên hệ quản trị viên để được cấp quyền.
          </p>
        </div>

        <div className="flex items-center lg:py-12">
          <div className="reveal reveal-delay-1 w-full">
            <div className="mb-6">
              <p className="eyebrow text-muted-foreground">Welcome back</p>
              <h2 className="mt-2 text-2xl font-bold tracking-[-0.03em]">Đăng nhập</h2>
            </div>

            {isAuthenticated ? (
              <Card>
                <CardContent className="flex items-center gap-2 p-4 text-sm font-medium text-muted-foreground sm:p-6">
                  <Spinner />
                  Đang kiểm tra phiên đăng nhập...
                </CardContent>
              </Card>
            ) : (
              <AuthPanel
                isLoading={isLoading}
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
