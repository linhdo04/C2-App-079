"use client";

import type { User } from "@/types/auth";

type SessionPanelProps = {
  accessTimeLeft: string;
  isLoading: boolean;
  refreshTimeLeft: string;
  user: User;
  onLogout: () => void;
};

export function SessionPanel({ accessTimeLeft, isLoading, refreshTimeLeft, user, onLogout }: SessionPanelProps) {
  return (
    <aside className="rounded-2xl border border-[#d8d2c7] bg-white p-4 shadow-sm sm:p-5">
      <p className="text-sm font-semibold text-[#456b58]">Đang đăng nhập</p>
      <h2 className="mt-2 text-xl font-semibold text-[#1d2b24]">{user.name}</h2>
      <p className="mt-1 break-words text-sm text-[#526158]">{user.email}</p>

      <dl className="mt-5 grid gap-3 text-sm">
        <div className="rounded-xl bg-[#f7f4ef] p-3">
          <dt className="font-medium text-[#273a31]">Access token</dt>
          <dd className="mt-1 text-[#526158]">Còn {accessTimeLeft}</dd>
        </div>
        <div className="rounded-xl bg-[#f7f4ef] p-3">
          <dt className="font-medium text-[#273a31]">Refresh token</dt>
          <dd className="mt-1 text-[#526158]">Còn {refreshTimeLeft}</dd>
        </div>
      </dl>

      <button
        className="mt-5 min-h-11 w-full rounded-xl border border-[#b9afa1] px-4 text-sm font-semibold text-[#273a31] transition hover:bg-[#f0ebe2] disabled:cursor-not-allowed disabled:text-[#8a8175]"
        type="button"
        onClick={onLogout}
        disabled={isLoading}
      >
        Đăng xuất
      </button>
    </aside>
  );
}
