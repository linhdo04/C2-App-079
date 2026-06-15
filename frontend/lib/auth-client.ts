"use client";

import { AUTH_COOKIE_NAME, TOKEN_STORAGE_KEY } from "@/lib/auth-constants";
import type { StoredSession, TokenResponse } from "@/types/auth";

function writeAuthCookie(maxAgeSeconds: number) {
  document.cookie = `${AUTH_COOKIE_NAME}=1; Path=/; Max-Age=${maxAgeSeconds}; SameSite=Lax`;
}

function isStoredSession(value: unknown): value is StoredSession {
  if (typeof value !== "object" || value === null) {
    return false;
  }

  const session = value as Partial<StoredSession>;
  return (
    typeof session.access_token === "string" &&
    session.access_token.length > 0 &&
    session.token_type === "bearer" &&
    typeof session.expires_in === "number" &&
    typeof session.refresh_expires_in === "number" &&
    typeof session.received_at === "number"
  );
}

export function readSession(): StoredSession | null {
  if (typeof window === "undefined") {
    return null;
  }

  const rawSession = window.localStorage.getItem(TOKEN_STORAGE_KEY);
  if (rawSession === null) {
    return null;
  }

  try {
    const parsedSession = JSON.parse(rawSession) as unknown;
    if (!isStoredSession(parsedSession)) {
      window.localStorage.removeItem(TOKEN_STORAGE_KEY);
      return null;
    }

    const storedSession = parsedSession as StoredSession & {
      refresh_token?: string;
    };
    const session: StoredSession = {
      access_token: storedSession.access_token,
      token_type: storedSession.token_type,
      expires_in: storedSession.expires_in,
      refresh_expires_in: storedSession.refresh_expires_in,
      received_at: storedSession.received_at,
    };
    const refreshExpiresAt = session.received_at + session.refresh_expires_in * 1000;
    const refreshMaxAge = Math.floor((refreshExpiresAt - Date.now()) / 1000);

    if (refreshMaxAge > 0) {
      writeAuthCookie(refreshMaxAge);
    }

    if (storedSession.refresh_token !== undefined) {
      window.localStorage.setItem(TOKEN_STORAGE_KEY, JSON.stringify(session));
    }

    return session;
  } catch {
    window.localStorage.removeItem(TOKEN_STORAGE_KEY);
    return null;
  }
}

export function hasAuthSession() {
  if (typeof document === "undefined") {
    return false;
  }

  return (
    readSession() !== null || document.cookie.split("; ").some((cookie) => cookie.startsWith(`${AUTH_COOKIE_NAME}=`))
  );
}

export function saveSession(tokenResponse: TokenResponse): StoredSession {
  const session = {
    access_token: tokenResponse.access_token,
    token_type: tokenResponse.token_type,
    expires_in: tokenResponse.expires_in,
    refresh_expires_in: tokenResponse.refresh_expires_in,
    received_at: Date.now(),
  };
  window.localStorage.setItem(TOKEN_STORAGE_KEY, JSON.stringify(session));
  writeAuthCookie(tokenResponse.refresh_expires_in);
  return session;
}

export function clearSession() {
  window.localStorage.removeItem(TOKEN_STORAGE_KEY);
  document.cookie = `${AUTH_COOKIE_NAME}=; Path=/; Max-Age=0; SameSite=Lax`;
}

export function sessionTimeLeft(session: StoredSession | null, key: "access" | "refresh") {
  if (session === null) {
    return 0;
  }

  const expiresIn = key === "access" ? session.expires_in : session.refresh_expires_in;
  const expiresAt = session.received_at + expiresIn * 1000;
  return Math.max(0, Math.floor((expiresAt - Date.now()) / 1000));
}

export function formatTimeLeft(seconds: number) {
  if (seconds <= 0) {
    return "đã hết hạn";
  }

  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) {
    return `${minutes} phút`;
  }

  const hours = Math.floor(minutes / 60);
  if (hours < 48) {
    return `${hours} giờ`;
  }

  return `${Math.floor(hours / 24)} ngày`;
}
