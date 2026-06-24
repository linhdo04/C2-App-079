export type AuthMode = "login" | "register";

export type User = {
  id: number;
  name: string;
  email: string;
  role: "operator" | "admin";
};

export type TokenResponse = {
  access_token: string;
  token_type: "bearer";
  expires_in: number;
  refresh_expires_in: number;
};

export type StoredSession = TokenResponse & {
  received_at: number;
};

export type LoginRequest = {
  email: string;
  password: string;
};

export type RegisterRequest = LoginRequest & {
  name: string;
};
