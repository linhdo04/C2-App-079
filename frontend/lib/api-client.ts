"use client";

import { readSession, saveSession } from "@/lib/auth-client";
import type { ApiResponse } from "@/types/api";
import type { StoredSession, TokenResponse } from "@/types/auth";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL;

type ApiErrorBody = {
  detail?: string;
  message?: string;
  error?: string;
};

type FetchInit = NonNullable<Parameters<typeof fetch>[1]>;

export type ServerSentEvent = {
  event: string;
  data: unknown;
};

export class ApiError extends Error {
  status: number;

  constructor(message: string, status: number) {
    super(message);
    this.status = status;
  }
}

let refreshRequest: Promise<StoredSession> | null = null;

async function parseError(response: Response): Promise<string> {
  try {
    const body = (await response.json()) as ApiErrorBody;
    if (typeof body.message === "string" && body.message.length > 0) {
      return body.message;
    }
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

export function refreshSession(): Promise<StoredSession> {
  if (refreshRequest === null) {
    refreshRequest = requestApi<ApiResponse<TokenResponse>>("/auth/refresh", {
      method: "POST",
    })
      .then((response) => saveSession(response.data))
      .finally(() => {
        refreshRequest = null;
      });
  }

  return refreshRequest;
}

export async function requestProtected<T>(path: string, init: FetchInit = {}): Promise<T> {
  let session = readSession();
  session ??= await refreshSession();

  try {
    return await requestApi<T>(path, init, session.access_token);
  } catch (error) {
    if (!(error instanceof ApiError) || error.status !== 401) {
      throw error;
    }
  }

  const refreshedSession = await refreshSession();
  return requestApi<T>(path, init, refreshedSession.access_token);
}

async function fetchProtectedStream(path: string, init: FetchInit): Promise<Response> {
  let currentSession = readSession();
  currentSession ??= await refreshSession();

  let response = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    credentials: "include",
    headers: protectedHeaders(init, currentSession.access_token),
  });

  if (response.status === 401) {
    currentSession = await refreshSession();
    response = await fetch(`${API_BASE_URL}${path}`, {
      ...init,
      credentials: "include",
      headers: protectedHeaders(init, currentSession.access_token),
    });
  }

  if (!response.ok) {
    throw new ApiError(await parseError(response), response.status);
  }
  if (response.body === null) {
    throw new ApiError("Máy chủ không trả về luồng dữ liệu.", response.status);
  }

  return response;
}

function protectedHeaders(init: FetchInit, accessToken: string) {
  const headers = new Headers(init.headers);
  headers.set("Authorization", `Bearer ${accessToken}`);
  if (!headers.has("Content-Type") && init.body !== undefined) {
    headers.set("Content-Type", "application/json");
  }
  headers.set("Accept", "text/event-stream");
  return headers;
}

function parseEventBlock(block: string): ServerSentEvent | null {
  let event = "message";
  const dataLines: string[] = [];

  for (const line of block.split(/\r?\n/)) {
    if (line.startsWith(":")) {
      continue;
    }

    const colonIndex = line.indexOf(":");
    const field = colonIndex === -1 ? line : line.slice(0, colonIndex);
    let value = colonIndex === -1 ? "" : line.slice(colonIndex + 1);
    if (value.startsWith(" ")) {
      value = value.slice(1);
    }

    if (field === "event") {
      event = value;
    } else if (field === "data") {
      dataLines.push(value);
    }
  }

  if (dataLines.length === 0) {
    return null;
  }

  const rawData = dataLines.join("\n");
  try {
    return { event, data: JSON.parse(rawData) as unknown };
  } catch {
    return { event, data: rawData };
  }
}

export async function requestProtectedEventStream(
  path: string,
  init: FetchInit,
  onEvent: (event: ServerSentEvent) => void,
): Promise<void> {
  const response = await fetchProtectedStream(path, init);
  const reader = response.body!.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    buffer += decoder.decode(value, { stream: !done });

    let boundary = buffer.search(/\r?\n\r?\n/);
    while (boundary >= 0) {
      const separator = buffer.slice(boundary).match(/^\r?\n\r?\n/)?.[0] ?? "\n\n";
      const event = parseEventBlock(buffer.slice(0, boundary));
      buffer = buffer.slice(boundary + separator.length);
      if (event !== null) {
        onEvent(event);
      }
      boundary = buffer.search(/\r?\n\r?\n/);
    }

    if (done) {
      const event = parseEventBlock(buffer);
      if (event !== null) {
        onEvent(event);
      }
      break;
    }
  }
}
