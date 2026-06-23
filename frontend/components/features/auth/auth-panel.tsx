"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { LockKeyhole, Mail } from "lucide-react";
import { useForm, type Resolver } from "react-hook-form";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Field, FieldError, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Spinner } from "@/components/ui/spinner";
import { loginSchema, type AuthFormValues } from "@/lib/validation";

type AuthPanelProps = {
  isLoading: boolean;
  onSubmit: (values: AuthFormValues) => void;
};

export function AuthPanel({ isLoading, onSubmit }: AuthPanelProps) {
  const {
    formState: { errors },
    handleSubmit,
    register,
  } = useForm<AuthFormValues>({
    defaultValues: {
      email: "",
      name: "",
      password: "",
    },
    resolver: zodResolver(loginSchema) as unknown as Resolver<AuthFormValues>,
  });

  return (
    <Card className="w-full border-border/80 bg-card/85">
      <CardContent className="p-5 sm:p-7">
        <form
          onSubmit={handleSubmit(onSubmit)}
          noValidate
        >
          <div className="grid rounded-xl border border-border/60 bg-background/50 p-1">
            <Button
              className="bg-secondary text-foreground shadow-sm hover:bg-secondary"
              variant="ghost"
              type="button"
            >
              Đăng nhập
            </Button>
          </div>

          <div className="mt-7 grid gap-5">
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
                  autoComplete="current-password"
                  minLength={1}
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
            {isLoading ? "Đang xử lý..." : "Đăng nhập"}
          </Button>
        </form>
      </CardContent>
    </Card>
  );
}
