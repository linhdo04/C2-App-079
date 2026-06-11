"use client";

import { create } from "zustand";
import { clearSession } from "@/lib/auth-client";
import type { User } from "@/types/auth";

type AuthStatus = "anonymous" | "authenticated";

type AuthStore = {
  authStatus: AuthStatus;
  isBooting: boolean;
  user: User | null;
  clearAuth: () => void;
  setBooting: (isBooting: boolean) => void;
  setAuthenticated: (isAuthenticated: boolean) => void;
  setUser: (user: User | null) => void;
};

export const useAuthStore = create<AuthStore>((set) => ({
  authStatus: "anonymous",
  isBooting: true,
  user: null,
  clearAuth: () => {
    clearSession();
    set({
      authStatus: "anonymous",
      user: null,
    });
  },
  setBooting: (isBooting) => set({ isBooting }),
  setAuthenticated: (isAuthenticated) =>
    set({
      authStatus: isAuthenticated ? "authenticated" : "anonymous",
    }),
  setUser: (user) => set({ user }),
}));
