"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { LockKeyhole, Mail, UserRound } from "lucide-react";
import { useEffect } from "react";
import { useForm, type Resolver } from "react-hook-form";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Field, FieldError, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Spinner } from "@/components/ui/spinner";
import { loginSchema, registerSchema, type AuthFormValues } from "@/lib/validation";
import type { AuthMode } from "@/types/auth";

type AuthPanelProps = {
  isLoading: boolean;
  mode: AuthMode;
  onModeChange: (mode: AuthMode) => void;
  onSubmit: (values: AuthFormValues) => void;
};

export function AuthPanel({ isLoading, mode, onModeChange, onSubmit }: AuthPanelProps) {
  const {
    clearErrors,
    formState: { errors },
    handleSubmit,
    register,
  } = useForm<AuthFormValues>({
    defaultValues: {
      email: "",
      name: "",
      password: "",
    },
    resolver: zodResolver(mode === "register" ? registerSchema : loginSchema) as unknown as Resolver<AuthFormValues>,
  });

  useEffect(() => {
    clearErrors();
  }, [clearErrors, mode]);

  return (
    <Card className="w-full border-border/80 bg-card/85">
      <CardContent className="p-5 sm:p-7">
        <form
          onSubmit={handleSubmit(onSubmit)}
          noValidate
        >
          <div className="grid grid-cols-2 gap-1 rounded-xl border border-border/60 bg-background/50 p-1">
            <Button
              className={
                mode === "login" ? "bg-secondary text-foreground shadow-sm hover:bg-secondary" : "text-muted-foreground"
              }
              variant="ghost"
              type="button"
              onClick={() => onModeChange("login")}
            >
              Đăng nhập
            </Button>
            <Button
              className={
                mode === "register"
                  ? "bg-secondary text-foreground shadow-sm hover:bg-secondary"
                  : "text-muted-foreground"
              }
              variant="ghost"
              type="button"
              onClick={() => onModeChange("register")}
            >
              Đăng ký
            </Button>
          </div>

          <div className="mt-7 grid gap-5">
            {mode === "register" && (
              <Field>
                <FieldLabel htmlFor="name">Tên</FieldLabel>
                <div className="relative">
                  <UserRound className="pointer-events-none absolute top-1/2 left-4 size-4 -translate-y-1/2 text-muted-foreground" />
                  <Input
                    id="name"
                    className="pl-11"
                    {...register("name")}
                    autoComplete="name"
                    maxLength={100}
                    placeholder="Nguyễn Văn An"
                    aria-invalid={errors.name !== undefined}
                    aria-describedby={errors.name !== undefined ? "name-error" : undefined}
                  />
                </div>
                {errors.name !== undefined && (
                  <FieldError
                    id="name-error"
                    role="alert"
                  >
                    {errors.name.message}
                  </FieldError>
                )}
              </Field>
            )}

            <Field>
              <FieldLabel htmlFor="email">Email</FieldLabel>
              <div className="relative">
                <Mail className="pointer-events-none absolute top-1/2 left-4 size-4 -translate-y-1/2 text-muted-foreground" />
                <Input
                  id="email"
                  className="pl-11"
                  {...register("email")}
                  type="email"
                  autoComplete="email"
                  placeholder="you@company.com"
                  aria-invalid={errors.email !== undefined}
                  aria-describedby={errors.email !== undefined ? "email-error" : undefined}
                />
              </div>
              {errors.email !== undefined && (
                <FieldError
                  id="email-error"
                  role="alert"
                >
                  {errors.email.message}
                </FieldError>
              )}
            </Field>

            <Field>
              <FieldLabel htmlFor="password">Mật khẩu</FieldLabel>
              <div className="relative">
                <LockKeyhole className="pointer-events-none absolute top-1/2 left-4 size-4 -translate-y-1/2 text-muted-foreground" />
                <Input
                  id="password"
                  className="pl-11"
                  {...register("password")}
                  type="password"
                  autoComplete={mode === "register" ? "new-password" : "current-password"}
                  minLength={mode === "register" ? 8 : 1}
                  maxLength={128}
                  placeholder="••••••••"
                  aria-invalid={errors.password !== undefined}
                  aria-describedby={errors.password !== undefined ? "password-error" : undefined}
                />
              </div>
              {errors.password !== undefined && (
                <FieldError
                  id="password-error"
                  role="alert"
                >
                  {errors.password.message}
                </FieldError>
              )}
            </Field>
          </div>

          <Button
            className="mt-7 w-full"
            size="lg"
            type="submit"
            disabled={isLoading}
          >
            {isLoading && <Spinner data-icon="inline-start" />}
            {isLoading ? "Đang xử lý..." : mode === "register" ? "Tạo tài khoản" : "Đăng nhập"}
          </Button>
        </form>
      </CardContent>
    </Card>
  );
}
