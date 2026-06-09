"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useEffect } from "react";
import { useForm, type Resolver } from "react-hook-form";
import type { AuthMode } from "@/types/auth";
import { loginSchema, registerSchema, type AuthFormValues } from "@/lib/validation";

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
    <form
      className="w-full rounded-2xl border border-[#d8d2c7] bg-white p-4 shadow-sm sm:p-6"
      onSubmit={handleSubmit(onSubmit)}
      noValidate
    >
      <div className="grid grid-cols-2 gap-2 rounded-xl bg-[#ebe5da] p-1">
        <button
          className={`min-h-11 rounded-lg px-3 text-sm font-semibold ${
            mode === "login" ? "bg-white text-[#1d2b24] shadow-sm" : "text-[#526158]"
          }`}
          type="button"
          onClick={() => onModeChange("login")}
        >
          Đăng nhập
        </button>
        <button
          className={`min-h-11 rounded-lg px-3 text-sm font-semibold ${
            mode === "register" ? "bg-white text-[#1d2b24] shadow-sm" : "text-[#526158]"
          }`}
          type="button"
          onClick={() => onModeChange("register")}
        >
          Đăng ký
        </button>
      </div>

      <div className="mt-5 grid gap-4">
        {mode === "register" && (
          <label className="grid gap-2 text-sm font-medium text-[#273a31]">
            Tên
            <input
              className="min-h-11 rounded-xl border border-[#cfc7ba] px-3 text-base outline-none focus:border-[#47745d] focus:ring-2 focus:ring-[#47745d]/20"
              {...register("name")}
              autoComplete="name"
              maxLength={100}
              aria-invalid={errors.name !== undefined}
            />
            {errors.name !== undefined && <span className="text-sm text-[#7e2416]">{errors.name.message}</span>}
          </label>
        )}

        <label className="grid gap-2 text-sm font-medium text-[#273a31]">
          Email
          <input
            className="min-h-11 rounded-xl border border-[#cfc7ba] px-3 text-base outline-none focus:border-[#47745d] focus:ring-2 focus:ring-[#47745d]/20"
            {...register("email")}
            type="email"
            autoComplete="email"
            aria-invalid={errors.email !== undefined}
          />
          {errors.email !== undefined && <span className="text-sm text-[#7e2416]">{errors.email.message}</span>}
        </label>

        <label className="grid gap-2 text-sm font-medium text-[#273a31]">
          Mật khẩu
          <input
            className="min-h-11 rounded-xl border border-[#cfc7ba] px-3 text-base outline-none focus:border-[#47745d] focus:ring-2 focus:ring-[#47745d]/20"
            {...register("password")}
            type="password"
            autoComplete={mode === "register" ? "new-password" : "current-password"}
            minLength={mode === "register" ? 8 : 1}
            maxLength={128}
            aria-invalid={errors.password !== undefined}
          />
          {errors.password !== undefined && <span className="text-sm text-[#7e2416]">{errors.password.message}</span>}
        </label>
      </div>

      <button
        className="mt-6 min-h-11 w-full rounded-xl bg-[#2f5d48] px-4 text-sm font-semibold text-white transition hover:bg-[#254a39] disabled:cursor-not-allowed disabled:bg-[#93a79b]"
        type="submit"
        disabled={isLoading}
      >
        {isLoading ? "Đang xử lý..." : mode === "register" ? "Tạo tài khoản" : "Đăng nhập"}
      </button>
    </form>
  );
}
