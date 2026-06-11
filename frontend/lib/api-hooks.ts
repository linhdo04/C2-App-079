"use client";

import { useInfiniteQuery, useMutation, useQuery } from "@tanstack/react-query";
import { requestApi, requestProtected } from "@/lib/api-client";
import type { ApiResponse, CursorMeta } from "@/types/api";
import type { AgentAskRequest, AgentResponse, ChatDetail, ChatMessageResponse, ChatSession } from "@/types/agent";
import type { LoginRequest, RegisterRequest, TokenResponse, User } from "@/types/auth";
import type { TelemetryResponse } from "@/types/dashboard";

export function useCurrentUserQuery(isAuthenticated: boolean) {
  return useQuery({
    enabled: isAuthenticated,
    queryKey: ["auth", "me"],
    queryFn: () => requestProtected<ApiResponse<User>>("/auth/me").then((response) => response.data),
  });
}

export function useDashboardTelemetryQuery() {
  return useQuery({
    queryKey: ["dashboard", "telemetry"],
    queryFn: () => requestProtected<TelemetryResponse>("/dashboard/telemetry?limit=24"),
    refetchInterval: 60_000,
  });
}

export function useRegisterMutation() {
  return useMutation({
    mutationFn: (body: RegisterRequest) =>
      requestApi<ApiResponse<User>>("/auth/register", {
        method: "POST",
        body: JSON.stringify(body),
      }).then((response) => response.data),
  });
}

export function useLoginMutation() {
  return useMutation({
    mutationFn: (body: LoginRequest) =>
      requestApi<ApiResponse<TokenResponse>>("/auth/login", {
        method: "POST",
        body: JSON.stringify(body),
      }).then((response) => response.data),
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
      requestProtected<ApiResponse<AgentResponse>>("/agent/ask", {
        method: "POST",
        body: JSON.stringify(body),
      }).then((response) => response.data),
  });
}

export function useChatsQuery(isAuthenticated: boolean, search: string) {
  const normalizedSearch = search.trim();

  return useInfiniteQuery({
    enabled: isAuthenticated,
    queryKey: ["agent", "chats", normalizedSearch],
    initialPageParam: null as string | null,
    queryFn: ({ pageParam }) => {
      const searchParams = new URLSearchParams({ limit: "20" });
      if (normalizedSearch.length > 0) {
        searchParams.set("search", normalizedSearch);
      }
      if (pageParam !== null) {
        searchParams.set("cursor", pageParam);
      }
      return requestProtected<ApiResponse<ChatSession[], CursorMeta>>(`/agent/chats?${searchParams.toString()}`);
    },
    getNextPageParam: (lastPage) => lastPage.meta.next_cursor ?? undefined,
  });
}

export function useChatQuery(isAuthenticated: boolean, chatId: number | null) {
  return useQuery({
    enabled: isAuthenticated && chatId !== null,
    queryKey: ["agent", "chats", chatId],
    queryFn: () =>
      requestProtected<ApiResponse<ChatDetail>>(`/agent/chats/${chatId}`).then((response) => response.data),
  });
}

export function useCreateChatMutation() {
  return useMutation({
    mutationFn: () =>
      requestProtected<ApiResponse<ChatSession>>("/agent/chats", {
        method: "POST",
        body: JSON.stringify({}),
      }).then((response) => response.data),
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
      requestProtected<ApiResponse<ChatMessageResponse>>(`/agent/chats/${chatId}/messages`, {
        method: "POST",
        body: JSON.stringify(body),
      }).then((response) => response.data),
  });
}
