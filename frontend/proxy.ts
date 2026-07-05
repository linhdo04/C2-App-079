import { NextRequest, NextResponse } from "next/server";
import { AUTH_COOKIE_NAME } from "@/lib/auth-constants";

export function proxy(request: NextRequest) {
  // This application does not expose Server Actions. Reject forged or stale
  // action requests before Next.js attempts to resolve their action ID.
  if (request.headers.has("next-action")) {
    return new NextResponse(null, { status: 404 });
  }

  const isAuthenticated = request.cookies.has(AUTH_COOKIE_NAME);

  if (isAuthenticated) {
    return NextResponse.next();
  }

  const loginUrl = new URL("/login", request.url);
  loginUrl.searchParams.set("next", request.nextUrl.pathname);
  return NextResponse.redirect(loginUrl);
}

export const config = {
  matcher: [
    "/dashboard/:path*",
    "/admin/:path*",
    {
      source: "/:path*",
      has: [{ type: "header", key: "next-action" }],
    },
  ],
};
