import { NextResponse } from "next/server";
import {
  SESSION_COOKIE_NAME,
  formatClearSessionCookie,
  parseCookies,
  resolveSecurityContext,
  revokeSession,
  verifyCsrfProtection,
  verifySessionToken,
} from "../../../security";

export async function POST(request: Request): Promise<NextResponse> {
  const resolved = resolveSecurityContext(request);
  if (resolved.ok) {
    const csrfCheck = verifyCsrfProtection(request, resolved.context);
    if (!csrfCheck.ok) {
      return NextResponse.json(
        { detail: csrfCheck.error },
        { status: csrfCheck.status }
      );
    }
    revokeSession(resolved.context.session_id);
  } else {
    const cookies = parseCookies(request.headers.get("cookie"));
    const rawCookie = cookies[SESSION_COOKIE_NAME];
    if (rawCookie) {
      const verified = verifySessionToken(rawCookie);
      if (verified.ok) {
        revokeSession(verified.claims.sid);
      }
    }
  }

  const response = NextResponse.json(
    { authenticated: false, status: "logged_out" },
    { status: 200 }
  );
  response.headers.set("Set-Cookie", formatClearSessionCookie());
  return response;
}

