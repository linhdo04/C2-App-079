"use client";

import { publicRouters } from "@/consts/public-routers";
import { PublicRouter } from "@/enums/public-routers";
import { useCurrentUserQuery } from "@/lib/api-hooks";
import { ADMIN_ENTRY_PATH, OPERATOR_ENTRY_PATH, isAdminPath } from "@/lib/auth-constants";
import { useAuthStore } from "@/lib/auth-store";
import { useQueryClient } from "@tanstack/react-query";
import { usePathname, useRouter } from "next/navigation";
import { ReactNode, useEffect } from "react";
import Loading from "./loading";

export default function CheckAuth({ children }: { children: ReactNode }) {
  const { setAuthenticated, setUser, clearAuth } = useAuthStore();
  const authStatus = useAuthStore((state) => state.authStatus);
  const currentUserQuery = useCurrentUserQuery(true);
  const queryClient = useQueryClient();
  const router = useRouter();
  const pathname = usePathname();

  const isAuthenticated = authStatus === "authenticated";
  const isCheckingAuth = currentUserQuery.isPending || currentUserQuery.isFetching;

  useEffect(() => {
    if (isCheckingAuth) {
      return;
    }

    if (currentUserQuery.data === undefined) {
      setAuthenticated(false);
      if (!publicRouters.includes(pathname)) {
        router.replace(PublicRouter.Login);
      }
      return;
    }

    const user = currentUserQuery.data;
    const entryPath = user.role === "admin" ? ADMIN_ENTRY_PATH : OPERATOR_ENTRY_PATH;

    setUser(user);
    setAuthenticated(true);

    if (user.role === "admin" && !isAdminPath(pathname)) {
      router.replace(entryPath);
      return;
    }

    if (user.role !== "admin" && isAdminPath(pathname)) {
      router.replace(entryPath);
      return;
    }

    if (pathname === PublicRouter.Login) {
      router.replace(entryPath);
    }
  }, [currentUserQuery.data, isCheckingAuth, pathname, router, setAuthenticated, setUser]);

  useEffect(() => {
    if (!isAuthenticated || currentUserQuery.error === null) {
      return;
    }

    const timeoutId = window.setTimeout(() => {
      clearAuth();
      queryClient.removeQueries({ queryKey: ["auth"] });

      if (!publicRouters.includes(pathname)) {
        router.replace(PublicRouter.Login);
      }
    }, 0);

    return () => {
      window.clearTimeout(timeoutId);
    };
  }, [clearAuth, currentUserQuery.error, isAuthenticated, pathname, queryClient, router]);

  if (isCheckingAuth) {
    return <Loading />;
  }

  return <>{children}</>;
}
