"use client";

import { saveSession } from "@/lib/auth-client";
import type { StoredSession, TokenResponse } from "@/types/auth";

const API_BASE_URL = process.env.NEXT_PUBLIC_BACKEND_URL?.replace(/\/$/, "") ?? "http://localhost:8000";

type ApiErrorBody = {
  detail?: string;
};

type FetchInit = Parameters<typeof fetch>[1];

export class ApiError extends Error {
  status: number;

  constructor(message: string, status: number) {
    super(message);
    this.status = status;
  }
}

async function parseError(response: Response): Promise<string> {
  try {
    const body = (await response.json()) as ApiErrorBody;
    if (typeof body.detail === "string" && body.detail.length > 0) {
      return body.detail;
    }
  } catch {
    return "Không thể xử lý phản hồi từ máy chủ.";
  }

  return "Yêu cầu không thành công. Vui lòng thử lại.";
}

export async function requestApi<T>(path: string, init: FetchInit = {}, accessToken?: string): Promise<T> {
  const headers = new Headers(init.headers);
  if (!headers.has("Content-Type") && init.body !== undefined) {
    headers.set("Content-Type", "application/json");
  }
  if (accessToken !== undefined) {
    headers.set("Authorization", `Bearer ${accessToken}`);
  }

  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    credentials: "include",
    headers,
  });
  if (!response.ok) {
    throw new ApiError(await parseError(response), response.status);
  }
  if (response.status === 204) {
    return undefined as T;
  }

  return (await response.json()) as T;
}

export async function refreshSession(): Promise<StoredSession> {
  const tokenResponse = await requestApi<TokenResponse>("/auth/refresh", {
    method: "POST",
  });
  return saveSession(tokenResponse);
}

export async function requestProtected<T>(
  path: string,
  session: StoredSession,
  init: FetchInit = {},
): Promise<{ data: T; session: StoredSession }> {
  try {
    const data = await requestApi<T>(path, init, session.access_token);
    return { data, session };
  } catch (error) {
    if (!(error instanceof ApiError) || error.status !== 401) {
      throw error;
    }
  }

  const refreshedSession = await refreshSession();
  const data = await requestApi<T>(path, init, refreshedSession.access_token);
  return { data, session: refreshedSession };
}
