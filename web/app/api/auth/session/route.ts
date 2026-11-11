import { NextResponse } from "next/server";
import {
  detectDeploymentSecurityMode,
  isProductionEnv,
  resolveSecurityContext,
} from "../../../security";

export async function GET(request: Request): Promise<NextResponse> {
  const modeStatus = detectDeploymentSecurityMode();
  const oidcConfigured = Boolean(
    (process.env.OIDC_ISSUER_URL || "").trim() &&
      (process.env.OIDC_CLIENT_ID || "").trim()
  );

  if (!modeStatus.ready) {
    return NextResponse.json(
      {
        authenticated: false,
        deployment_mode: modeStatus.mode,
        ready: false,
        detail: modeStatus.reason,
        oidc_enabled: oidcConfigured,
      },
      { status: 503 }
    );
  }

  const resolved = resolveSecurityContext(request);
  if (!resolved.ok) {
    return NextResponse.json(
      {
        authenticated: false,
        deployment_mode: modeStatus.mode,
        ready: true,
        oidc_enabled: oidcConfigured,
        local_community_hint: !isProductionEnv()
          ? "Local self-hosted accounts available: analyst / analyst-local-pass, reviewer / reviewer-local-pass, viewer / viewer-local-pass, admin / admin-local-pass"
          : undefined,
      },
      { status: 200 }
    );
  }

  const ctx = resolved.context;
  return NextResponse.json(
    {
      authenticated: ctx.authenticated,
      user_id: ctx.user_id,
      display_name: ctx.display_name,
      tenant_id: ctx.tenant_id,
      roles: ctx.roles,
      permissions: ctx.permissions,
      csrf_token: ctx.csrf_token,
      deployment_mode: ctx.deployment_mode,
      auth_method: ctx.auth_method,
      expires_at: ctx.expires_at,
      ready: true,
      oidc_enabled: oidcConfigured,
    },
    { status: 200 }
  );
}

