export const AUTH_COOKIE_NAME = "c2-app-authenticated";
export const TOKEN_STORAGE_KEY = "c2-app-auth";
export const ADMIN_ENTRY_PATH = "/admin/cost-management";
export const OPERATOR_ENTRY_PATH = "/dashboard";

export function isAdminPath(pathname: string) {
  return pathname === "/admin" || pathname.startsWith("/admin/");
}
