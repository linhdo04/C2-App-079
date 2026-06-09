"use client";

import { useMutation, useQuery } from "@tanstack/react-query";
import { requestApi, requestProtected } from "@/lib/api-client";
import type { AgentAskRequest, AgentResponse, ChatDetail, ChatMessageResponse, ChatSession } from "@/types/agent";
import type { LoginRequest, RegisterRequest, TokenResponse, User } from "@/types/auth";

export function useCurrentUserQuery(isAuthenticated: boolean) {
  return useQuery({
    enabled: isAuthenticated,
    queryKey: ["auth", "me"],
    queryFn: () => requestProtected<User>("/auth/me"),
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
    mutationFn: () =>
      requestProtected<void>("/auth/logout", {
        method: "POST",
      }),
  });
}

export function useAgentAskMutation() {
  return useMutation({
    mutationFn: (body: AgentAskRequest) =>
      requestProtected<AgentResponse>("/agent/ask", {
        method: "POST",
        body: JSON.stringify(body),
      }),
  });
}

export function useChatsQuery(isAuthenticated: boolean, search: string) {
  const searchParams = new URLSearchParams();
  if (search.trim().length > 0) {
    searchParams.set("search", search.trim());
  }
  const queryString = searchParams.toString();

  return useQuery({
    enabled: isAuthenticated,
    queryKey: ["agent", "chats", search.trim()],
    queryFn: () => requestProtected<ChatSession[]>(`/agent/chats${queryString.length > 0 ? `?${queryString}` : ""}`),
  });
}

export function useChatQuery(isAuthenticated: boolean, chatId: number | null) {
  return useQuery({
    enabled: isAuthenticated && chatId !== null,
    queryKey: ["agent", "chats", chatId],
    queryFn: () => requestProtected<ChatDetail>(`/agent/chats/${chatId}`),
  });
}

export function useCreateChatMutation() {
  return useMutation({
    mutationFn: () =>
      requestProtected<ChatSession>("/agent/chats", {
        method: "POST",
        body: JSON.stringify({}),
      }),
  });
}

export function useDeleteChatMutation() {
  return useMutation({
    mutationFn: (chatId: number) =>
      requestProtected<void>(`/agent/chats/${chatId}`, {
        method: "DELETE",
      }),
  });
}

export function useSendChatMessageMutation() {
  return useMutation({
    mutationFn: ({ body, chatId }: { body: AgentAskRequest; chatId: number }) =>
      requestProtected<ChatMessageResponse>(`/agent/chats/${chatId}/messages`, {
        method: "POST",
        body: JSON.stringify(body),
      }),
  });
}
