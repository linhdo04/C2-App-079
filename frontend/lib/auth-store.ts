"use client";

import { create } from "zustand";
import { clearSession } from "@/lib/auth-client";
import type { StoredSession, User } from "@/types/auth";

type AuthStatus = "anonymous" | "authenticated";

type AuthStore = {
  authStatus: AuthStatus;
  isBooting: boolean;
  session: StoredSession | null;
  user: User | null;
  clearAuth: () => void;
  setBooting: (isBooting: boolean) => void;
  setSession: (session: StoredSession | null) => void;
  setUser: (user: User | null) => void;
};

export const useAuthStore = create<AuthStore>((set) => ({
  authStatus: "anonymous",
  isBooting: true,
  session: null,
  user: null,
  clearAuth: () => {
    clearSession();
    set({
      authStatus: "anonymous",
      session: null,
      user: null,
    });
  },
  setBooting: (isBooting) => set({ isBooting }),
  setSession: (session) =>
    set({
      authStatus: session === null ? "anonymous" : "authenticated",
      session,
    }),
  setUser: (user) => set({ user }),
}));
