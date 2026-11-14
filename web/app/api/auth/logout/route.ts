import { NextResponse } from "next/server";
import {
  SESSION_COOKIE_NAME,
  SecurityStateStorageError,
  formatClearSessionCookie,
  parseCookies,
  resolveSecurityContext,
  revokeSession,
  verifyCsrfProtection,
  verifySessionToken,
} from "../../../security";

export async function POST(request: Request): Promise<NextResponse> {
  try {
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
  } catch (err) {
    const errRes = NextResponse.json(
      {
        authenticated: false,
        status: "error",
        detail:
          err instanceof SecurityStateStorageError
            ? `Session revocation persistence failed: ${err.message}`
            : "Session revocation persistence failed; failing closed.",
      },
      { status: 503 }
    );
    errRes.headers.set("Set-Cookie", formatClearSessionCookie());
    return errRes;
  }

  const response = NextResponse.json(
    { authenticated: false, status: "logged_out" },
    { status: 200 }
  );
  response.headers.set("Set-Cookie", formatClearSessionCookie());
  return response;
}

