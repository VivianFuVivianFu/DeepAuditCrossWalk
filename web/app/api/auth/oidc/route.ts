import { NextResponse } from "next/server";
import {
  OIDC_STATE_COOKIE_NAME,
  createOidcPkceSession,
  formatSessionCookie,
  isProductionEnv,
  parseCookies,
  permissionsForRoles,
  verifyOidcCallbackAndIssueSession,
} from "../../../security";

export async function GET(request: Request): Promise<NextResponse> {
  if (isProductionEnv()) {
    return NextResponse.json(
      {
        detail:
          "OIDC Authorization Code Flow with JWKS verification is currently experimental and disabled for hosted production. Please configure WORKSPACE_USERS_JSON or await the dedicated standards-compliant OIDC release.",
      },
      { status: 501 }
    );
  }

  const url = new URL(request.url);
  const callbackState = url.searchParams.get("state");
  const idToken = url.searchParams.get("id_token");

  if (callbackState || idToken) {
    const cookies = parseCookies(request.headers.get("cookie"));
    const stateCookie = cookies[OIDC_STATE_COOKIE_NAME] || "";
    const result = verifyOidcCallbackAndIssueSession({
      callbackState: callbackState || "",
      signedStateCookie: stateCookie,
      idToken: idToken || "",
    });
    if (!result.ok) {
      return NextResponse.json(
        { detail: result.error },
        { status: result.status }
      );
    }
    const response = NextResponse.json(
      {
        authenticated: true,
        user_id: result.claims.sub,
        display_name: result.claims.name,
        tenant_id: result.claims.tenant_id,
        roles: result.claims.roles,
        permissions: permissionsForRoles(result.claims.roles),
        csrf_token: result.claims.csrf,
      },
      { status: 200 }
    );
    response.headers.set("Set-Cookie", formatSessionCookie(result.sessionToken));
    return response;
  }

  const redirectUri =
    url.searchParams.get("redirect_uri") || `${url.origin}/api/auth/oidc`;
  const pkceSession = createOidcPkceSession(redirectUri);
  const secure = isProductionEnv() ? "; Secure" : "";
  const response = NextResponse.json(
    {
      authorize_url: pkceSession.authorizeUrl,
      state: pkceSession.pkce.state,
      code_challenge: pkceSession.pkce.code_challenge,
      code_challenge_method: "S256",
    },
    { status: 200 }
  );
  response.headers.set(
    "Set-Cookie",
    `${OIDC_STATE_COOKIE_NAME}=${encodeURIComponent(
      pkceSession.signedStateCookieValue
    )}; Path=/; HttpOnly; SameSite=Lax; Max-Age=600${secure}`
  );
  return response;
}

export async function POST(request: Request): Promise<NextResponse> {
  if (isProductionEnv()) {
    return NextResponse.json(
      {
        detail:
          "OIDC Authorization Code Flow with JWKS verification is currently experimental and disabled for hosted production. Please configure WORKSPACE_USERS_JSON or await the dedicated standards-compliant OIDC release.",
      },
      { status: 501 }
    );
  }

  let body: Record<string, unknown>;
  try {
    body = (await request.json()) as Record<string, unknown>;
  } catch {
    return NextResponse.json(
      { detail: "OIDC callback payload must be valid JSON." },
      { status: 400 }
    );
  }

  const cookies = parseCookies(request.headers.get("cookie"));
  const stateCookie =
    cookies[OIDC_STATE_COOKIE_NAME] || String(body.state_cookie || "");
  const callbackState = String(body.state || "");
  const idToken = String(body.id_token || "");

  const result = verifyOidcCallbackAndIssueSession({
    callbackState,
    signedStateCookie: stateCookie,
    idToken,
  });

  if (!result.ok) {
    return NextResponse.json(
      { detail: result.error },
      { status: result.status }
    );
  }

  const response = NextResponse.json(
    {
      authenticated: true,
      user_id: result.claims.sub,
      display_name: result.claims.name,
      tenant_id: result.claims.tenant_id,
      roles: result.claims.roles,
      permissions: permissionsForRoles(result.claims.roles),
      csrf_token: result.claims.csrf,
      session_id: result.claims.sid,
    },
    { status: 200 }
  );
  response.headers.set("Set-Cookie", formatSessionCookie(result.sessionToken));
  return response;
}
