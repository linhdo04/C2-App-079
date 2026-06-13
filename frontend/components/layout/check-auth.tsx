"use client";

import { publicRouters } from "@/consts/public-routers";
import { PublicRouter } from "@/enums/public-routers";
import { useCurrentUserQuery } from "@/lib/api-hooks";
import { useAuthStore } from "@/lib/auth-store";
import { useQueryClient } from "@tanstack/react-query";
import { usePathname, useRouter } from "next/navigation";
import { ReactNode, useEffect } from "react";

export default function CheckAuth({ children }: { children: ReactNode }) {
  const { authStatus, setAuthenticated, setBooting, setUser, clearAuth } = useAuthStore();
  const currentUserQuery = useCurrentUserQuery(true);
  const queryClient = useQueryClient();
  const router = useRouter();
  const pathname = usePathname();

  const isAuthenticated = authStatus === "authenticated";

  useEffect(() => {
    if (currentUserQuery.data === undefined) {
      setAuthenticated(false);
      setBooting(false);
      if (!publicRouters.includes(pathname)) {
        router.replace(PublicRouter.Login);
      }
      return;
    }

    if (publicRouters.includes(pathname)) {
      router.replace(PublicRouter.Home);
    }

    setUser(currentUserQuery.data);
    setBooting(false);
    setAuthenticated(true);
  }, [currentUserQuery.data, setBooting, setUser, setAuthenticated, pathname, router]);

  useEffect(() => {
    if (!isAuthenticated || currentUserQuery.error === null) {
      return;
    }

    const timeoutId = window.setTimeout(() => {
      clearAuth();
      queryClient.removeQueries({ queryKey: ["auth"] });
      setBooting(false);
    }, 0);

    return () => {
      window.clearTimeout(timeoutId);
    };
  }, [clearAuth, currentUserQuery.error, isAuthenticated, queryClient, setBooting]);

  return <>{children}</>;
}
