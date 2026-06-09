"use client";

import { useMutation, useQuery } from "@tanstack/react-query";
import { requestApi, requestProtected } from "@/lib/api-client";
import type { AgentAskRequest, AgentResponse } from "@/types/agent";
import type { LoginRequest, RegisterRequest, StoredSession, TokenResponse, User } from "@/types/auth";

export function useCurrentUserQuery(session: StoredSession | null) {
  return useQuery({
    enabled: session !== null,
    queryKey: ["auth", "me", session?.received_at],
    queryFn: () => requestProtected<User>("/auth/me", session as StoredSession),
  });
}

export function useRegisterMutation() {
  return useMutation({
    mutationFn: (body: RegisterRequest) =>
      requestApi<User>("/auth/register", {
        method: "POST",
        body: JSON.stringify(body),
      }),
  });
}

export function useLoginMutation() {
  return useMutation({
    mutationFn: (body: LoginRequest) =>
      requestApi<TokenResponse>("/auth/login", {
        method: "POST",
        body: JSON.stringify(body),
      }),
  });
}

export function useLogoutMutation() {
  return useMutation({
    mutationFn: (session: StoredSession) =>
      requestApi<void>(
        "/auth/logout",
        {
          method: "POST",
        },
        session.access_token,
      ),
  });
}

export function useAgentAskMutation() {
  return useMutation({
    mutationFn: ({ body, session }: { body: AgentAskRequest; session: StoredSession }) =>
      requestProtected<AgentResponse>("/agent/ask", session, {
        method: "POST",
        body: JSON.stringify(body),
      }),
  });
}
