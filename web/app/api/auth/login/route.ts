import { NextResponse } from "next/server";
import {
  SESSION_COOKIE_NAME,
  SecurityStateStorageError,
  assertSecurityStoreHealthy,
  authenticateUserCredentials,
  checkLoginRateLimit,
  clearLoginRateLimit,
  createSessionToken,
  detectDeploymentSecurityMode,
  formatSessionCookie,
  parseCookies,
  permissionsForRoles,
  recordLoginFailedAttempt,
  revokeSession,
  verifySessionToken,
} from "../../../security";

export async function POST(request: Request): Promise<NextResponse> {
  const modeStatus = detectDeploymentSecurityMode();
  if (!modeStatus.ready) {
    return NextResponse.json(
      { detail: modeStatus.reason || "Authentication service is not configured." },
      { status: 503 }
    );
  }

  try {
    assertSecurityStoreHealthy();
  } catch (err) {
    return NextResponse.json(
      {
        detail:
          err instanceof SecurityStateStorageError
            ? `Authentication security store error: ${err.message}`
            : "Authentication security store is unavailable; failing closed.",
      },
      { status: 503 }
    );
  }

  let body: Record<string, unknown>;
  try {
    body = (await request.json()) as Record<string, unknown>;
  } catch {
    return NextResponse.json(
      { detail: "Login payload must be valid JSON." },
      { status: 400 }
    );
  }

  const username = String(body.username || "").trim();
  const password = String(body.password || "");
  const tenantId = body.tenant_id ? String(body.tenant_id).trim() : undefined;

  if (!username || !password) {
    return NextResponse.json(
      { detail: "Both username and password are required." },
      { status: 400 }
    );
  }

  if (!checkLoginRateLimit(request, username)) {
    return NextResponse.json(
      { detail: "Too many failed login attempts. Please try again later." },
      { status: 429 }
    );
  }

  // Rotate / invalidate any existing session token in cookies to prevent session fixation
  const cookies = parseCookies(request.headers.get("cookie"));
  const oldToken = cookies[SESSION_COOKIE_NAME];
  if (oldToken) {
    const oldVerified = verifySessionToken(oldToken);
    if (oldVerified.ok) {
      revokeSession(oldVerified.claims.sid);
    }
  }

  const authResult = authenticateUserCredentials({
    username,
    password,
    tenant_id: tenantId,
  });

  if (!authResult.ok) {
    recordLoginFailedAttempt(request, username);
    return NextResponse.json(
      { detail: authResult.error },
      { status: authResult.status }
    );
  }

  clearLoginRateLimit(request, username);

  const { token, claims } = createSessionToken({
    user_id: authResult.user.user_id,
    display_name: authResult.user.display_name,
    tenant_id: authResult.tenant_id,
    roles: authResult.roles,
  });

  const response = NextResponse.json(
    {
      authenticated: true,
      user_id: claims.sub,
      display_name: claims.name,
      tenant_id: claims.tenant_id,
      roles: claims.roles,
      permissions: permissionsForRoles(claims.roles),
      csrf_token: claims.csrf,
      session_id: claims.sid,
      deployment_mode: modeStatus.mode,
      expires_at: claims.exp,
    },
    { status: 200 }
  );
  response.headers.set("Set-Cookie", formatSessionCookie(token));
  return response;
}
