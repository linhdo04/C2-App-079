"use client";

import { useMutation, useQuery } from "@tanstack/react-query";
import { requestApi, requestProtected } from "@/lib/api-client";
import type { AgentAskRequest, AgentResponse, ChatDetail, ChatMessageResponse, ChatSession } from "@/types/agent";
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

export function useChatsQuery(session: StoredSession | null, search: string) {
  const searchParams = new URLSearchParams();
  if (search.trim().length > 0) {
    searchParams.set("search", search.trim());
  }
  const queryString = searchParams.toString();

  return useQuery({
    enabled: session !== null,
    queryKey: ["agent", "chats", search.trim()],
    queryFn: () =>
      requestProtected<ChatSession[]>(
        `/agent/chats${queryString.length > 0 ? `?${queryString}` : ""}`,
        session as StoredSession,
      ),
  });
}

export function useChatQuery(session: StoredSession | null, chatId: number | null) {
  return useQuery({
    enabled: session !== null && chatId !== null,
    queryKey: ["agent", "chats", chatId],
    queryFn: () => requestProtected<ChatDetail>(`/agent/chats/${chatId}`, session as StoredSession),
  });
}

export function useCreateChatMutation() {
  return useMutation({
    mutationFn: (session: StoredSession) =>
      requestProtected<ChatSession>("/agent/chats", session, {
        method: "POST",
        body: JSON.stringify({}),
      }),
  });
}

export function useDeleteChatMutation() {
  return useMutation({
    mutationFn: ({ chatId, session }: { chatId: number; session: StoredSession }) =>
      requestProtected<void>(`/agent/chats/${chatId}`, session, {
        method: "DELETE",
      }),
  });
}

export function useSendChatMessageMutation() {
  return useMutation({
    mutationFn: ({ body, chatId, session }: { body: AgentAskRequest; chatId: number; session: StoredSession }) =>
      requestProtected<ChatMessageResponse>(`/agent/chats/${chatId}/messages`, session, {
        method: "POST",
        body: JSON.stringify(body),
      }),
  });
}
