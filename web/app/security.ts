import crypto from "node:crypto";

export type Role = "viewer" | "analyst" | "reviewer" | "admin";

export type Permission =
  | "questionnaire:read"
  | "questionnaire:upload"
  | "policy:read"
  | "policy:upload"
  | "policy:delete"
  | "clause:read"
  | "clause:review"
  | "mapping:read"
  | "mapping:review"
  | "baseline:read"
  | "baseline:create"
  | "assessment:read"
  | "assessment:run";

export type DeploymentSecurityMode =
  | "public_demo_only"
  | "local_dev_bypass"
  | "authenticated_self_hosted"
  | "authenticated_hosted"
  | "misconfigured_production";

export type SecurityContext = {
  user_id: string;
  display_name: string;
  tenant_id: string;
  authenticated: boolean;
  roles: Role[];
  permissions: Permission[];
  session_id: string;
  csrf_token: string;
  deployment_mode: DeploymentSecurityMode;
  auth_method: "session_cookie" | "bearer_jwt" | "bearer_token" | "local_dev_bypass";
  expires_at: number;
};

export type WorkspaceUserRecord = {
  user_id: string;
  username: string;
  display_name: string;
  password?: string;
  password_sha256?: string;
  tenants: Record<string, Role[]>;
  disabled?: boolean;
};

export const SESSION_COOKIE_NAME = "crosswalk_session";
export const OIDC_STATE_COOKIE_NAME = "crosswalk_oidc_state";
export const DEFAULT_SESSION_TTL_SECONDS = 60 * 60 * 8; // 8 hours

export const ROLE_PERMISSIONS: Record<Role, readonly Permission[]> = {
  viewer: [
    "questionnaire:read",
    "policy:read",
    "clause:read",
    "mapping:read",
    "baseline:read",
    "assessment:read",
  ],
  analyst: [
    "questionnaire:read",
    "questionnaire:upload",
    "policy:read",
    "policy:upload",
    "clause:read",
    "mapping:read",
    "baseline:read",
    "assessment:read",
    "assessment:run",
  ],
  reviewer: [
    "questionnaire:read",
    "questionnaire:upload",
    "policy:read",
    "policy:upload",
    "clause:read",
    "clause:review",
    "mapping:read",
    "mapping:review",
    "baseline:read",
    "baseline:create",
    "assessment:read",
    "assessment:run",
  ],
  admin: [
    "questionnaire:read",
    "questionnaire:upload",
    "policy:read",
    "policy:upload",
    "policy:delete",
    "clause:read",
    "clause:review",
    "mapping:read",
    "mapping:review",
    "baseline:read",
    "baseline:create",
    "assessment:read",
    "assessment:run",
  ],
};

export const ACTION_PERMISSIONS: Record<string, Permission> = {
  status: "questionnaire:read",
  list_questionnaires: "questionnaire:read",
  get_questionnaire: "questionnaire:read",
  import_questionnaire: "questionnaire:upload",
  list_policies: "policy:read",
  get_policy: "policy:read",
  import_policy: "policy:upload",
  import_policy_text: "policy:upload",
  import_policy_file: "policy:upload",
  delete_policy: "policy:delete",
  list_clauses: "clause:read",
  get_policy_clauses: "clause:read",
  review_clause: "clause:review",
  review_clause_mapping: "mapping:review",
  list_baselines: "baseline:read",
  get_baseline: "baseline:read",
  create_baseline: "baseline:create",
  assess_coverage: "assessment:run",
  run_coverage_assessment: "assessment:run",
  run_policy_gap_assessment: "assessment:run",
  get_report: "assessment:read",
  get_gaps: "assessment:read",
};

// Server-side revocation and runtime user state
const revokedSessions = new Set<string>();
const runtimeUserOverrides = new Map<string, WorkspaceUserRecord>();

export function clearSecurityStateForTests(): void {
  revokedSessions.clear();
  runtimeUserOverrides.clear();
}

export function revokeSession(sessionId: string): void {
  if (sessionId) {
    revokedSessions.add(sessionId);
  }
}

export function isSessionRevoked(sessionId: string): boolean {
  return revokedSessions.has(sessionId);
}

export function isProductionEnv(): boolean {
  const env = (process.env.ENV || "").trim().toLowerCase();
  const nodeEnv = (process.env.NODE_ENV || "").trim().toLowerCase();
  return env === "production" || nodeEnv === "production";
}

export function constantTimeEqual(a: string, b: string): boolean {
  const bufA = Buffer.from(a, "utf8");
  const bufB = Buffer.from(b, "utf8");
  if (bufA.length !== bufB.length) {
    return false;
  }
  return crypto.timingSafeEqual(bufA, bufB);
}

export function normalizeRole(raw: string): Role | null {
  const r = (raw || "").trim().toLowerCase();
  if (r === "viewer" || r === "read_only" || r === "readonly") return "viewer";
  if (r === "analyst" || r === "contributor") return "analyst";
  if (
    r === "reviewer" ||
    r === "compliance" ||
    r === "legal" ||
    r === "risk" ||
    r === "policy_owner"
  ) {
    return "reviewer";
  }
  if (r === "admin" || r === "administrator") return "admin";
  return null;
}

export function permissionsForRoles(roles: readonly Role[]): Permission[] {
  const set = new Set<Permission>();
  for (const role of roles) {
    for (const perm of ROLE_PERMISSIONS[role] || []) {
      set.add(perm);
    }
  }
  return Array.from(set);
}

export function primaryRole(roles: readonly Role[]): Role {
  if (roles.includes("admin")) return "admin";
  if (roles.includes("reviewer")) return "reviewer";
  if (roles.includes("analyst")) return "analyst";
  return "viewer";
}

export function hasPermission(
  ctx: Pick<SecurityContext, "permissions">,
  permission: Permission
): boolean {
  return ctx.permissions.includes(permission);
}

function getSessionSecret(): string {
  const configured = (process.env.WORKSPACE_SESSION_SECRET || "").trim();
  if (configured) {
    return configured;
  }
  if (!isProductionEnv()) {
    return "local-community-dev-only-session-secret-not-for-prod-32b";
  }
  return "";
}

function defaultNonProdUsers(): WorkspaceUserRecord[] {
  const defaultTenant =
    (process.env.BANKING_CROSSWALK_TENANT_ID || "").trim() || "local-workspace";
  return [
    {
      user_id: "usr-local-analyst",
      username: "analyst",
      display_name: "Local Governance Analyst",
      password: "analyst-local-pass",
      tenants: { [defaultTenant]: ["analyst"] },
    },
    {
      user_id: "usr-local-reviewer",
      username: "reviewer",
      display_name: "Local Compliance Reviewer",
      password: "reviewer-local-pass",
      tenants: { [defaultTenant]: ["reviewer"] },
    },
    {
      user_id: "usr-local-viewer",
      username: "viewer",
      display_name: "Local Audit Viewer",
      password: "viewer-local-pass",
      tenants: { [defaultTenant]: ["viewer"] },
    },
    {
      user_id: "usr-local-admin",
      username: "admin",
      display_name: "Local Workspace Admin",
      password: "admin-local-pass",
      tenants: { [defaultTenant]: ["admin"] },
    },
  ];
}

export function loadWorkspaceUsers(): Map<string, WorkspaceUserRecord> {
  const map = new Map<string, WorkspaceUserRecord>();
  const rawJson = (process.env.WORKSPACE_USERS_JSON || "").trim();

  if (rawJson) {
    try {
      const parsed = JSON.parse(rawJson);
      if (Array.isArray(parsed)) {
        for (const item of parsed) {
          if (!item || typeof item !== "object") continue;
          const userId = String(item.user_id || item.username || "").trim();
          const username = String(item.username || item.user_id || "").trim();
          if (!userId || !username) continue;
          const tenants: Record<string, Role[]> = {};
          if (item.tenants && typeof item.tenants === "object") {
            for (const [tid, rlist] of Object.entries(item.tenants)) {
              const roles = (Array.isArray(rlist) ? rlist : [rlist])
                .map((x) => normalizeRole(String(x)))
                .filter((x): x is Role => x !== null);
              if (roles.length > 0) {
                tenants[tid] = roles;
              }
            }
          } else {
            const tid =
              String(item.tenant_id || process.env.BANKING_CROSSWALK_TENANT_ID || "local-workspace").trim();
            const rawRoles = Array.isArray(item.roles)
              ? item.roles
              : item.role
              ? [item.role]
              : ["viewer"];
            const roles = rawRoles
              .map((x: unknown) => normalizeRole(String(x)))
              .filter((x: Role | null): x is Role => x !== null);
            tenants[tid] = roles.length > 0 ? roles : ["viewer"];
          }
          const rec: WorkspaceUserRecord = {
            user_id: userId,
            username,
            display_name: String(item.display_name || username),
            password: item.password ? String(item.password) : undefined,
            password_sha256: item.password_sha256
              ? String(item.password_sha256)
              : undefined,
            tenants,
            disabled: Boolean(item.disabled),
          };
          map.set(userId, rec);
        }
      }
    } catch {
      // Invalid JSON fails closed
    }
  } else if (!isProductionEnv()) {
    for (const u of defaultNonProdUsers()) {
      map.set(u.user_id, u);
    }
  }

  for (const [uid, override] of runtimeUserOverrides.entries()) {
    map.set(uid, override);
  }
  return map;
}

export function upsertRuntimeWorkspaceUser(user: WorkspaceUserRecord): void {
  runtimeUserOverrides.set(user.user_id, user);
}

export function setRuntimeUserDisabled(userId: string, disabled: boolean): void {
  const users = loadWorkspaceUsers();
  const existing = users.get(userId);
  if (existing) {
    runtimeUserOverrides.set(userId, { ...existing, disabled });
  }
}

export function setRuntimeUserTenantRoles(
  userId: string,
  tenantId: string,
  roles: Role[] | null
): void {
  const users = loadWorkspaceUsers();
  const existing = users.get(userId);
  if (existing) {
    const nextTenants = { ...existing.tenants };
    if (roles === null || roles.length === 0) {
      delete nextTenants[tenantId];
    } else {
      nextTenants[tenantId] = roles;
    }
    runtimeUserOverrides.set(userId, { ...existing, tenants: nextTenants });
  }
}

export function detectDeploymentSecurityMode(): {
  mode: DeploymentSecurityMode;
  ready: boolean;
  reason?: string;
} {
  const prod = isProductionEnv();
  const sessionSecret = (process.env.WORKSPACE_SESSION_SECRET || "").trim();
  const apiKey = (process.env.CROSSWALK_API_KEY || "").trim();
  const hasUsersJson = Boolean((process.env.WORKSPACE_USERS_JSON || "").trim());
  const hasOidc = Boolean(
    (process.env.OIDC_ISSUER_URL || "").trim() &&
      (process.env.OIDC_CLIENT_ID || "").trim()
  );
  const hasBearerToken = Boolean((process.env.WORKSPACE_AUTH_TOKEN || "").trim());

  if (prod) {
    if (!apiKey) {
      return {
        mode: "misconfigured_production",
        ready: false,
        reason:
          "Server configuration error: CROSSWALK_API_KEY is required in production.",
      };
    }
    if (sessionSecret.length < 32 && !hasBearerToken) {
      return {
        mode: "misconfigured_production",
        ready: false,
        reason:
          "Document workspace authentication is not configured: WORKSPACE_SESSION_SECRET (>= 32 chars) is required in production.",
      };
    }
    if (!hasUsersJson && !hasOidc && !hasBearerToken) {
      return {
        mode: "misconfigured_production",
        ready: false,
        reason:
          "Document workspace authentication is not configured: an identity provider (OIDC_ISSUER_URL or WORKSPACE_USERS_JSON) is required in production.",
      };
    }
    return {
      mode: "authenticated_hosted",
      ready: true,
    };
  }

  const bypass = (process.env.ALLOW_LOCAL_DEV_AUTH_BYPASS || "")
    .trim()
    .toLowerCase();
  if (bypass === "true" || bypass === "1") {
    return {
      mode: "local_dev_bypass",
      ready: true,
    };
  }

  return {
    mode: "authenticated_self_hosted",
    ready: true,
  };
}

function base64UrlEncode(input: Buffer | string): string {
  const buf = typeof input === "string" ? Buffer.from(input, "utf8") : input;
  return buf
    .toString("base64")
    .replace(/\+/g, "-")
    .replace(/\//g, "_")
    .replace(/=+$/g, "");
}

function base64UrlDecodeToString(input: string): string {
  const padded = input.replace(/-/g, "+").replace(/_/g, "/");
  const padLen = (4 - (padded.length % 4)) % 4;
  return Buffer.from(padded + "=".repeat(padLen), "base64").toString("utf8");
}

export type SessionTokenClaims = {
  sub: string;
  name: string;
  tenant_id: string;
  roles: Role[];
  sid: string;
  csrf: string;
  iat: number;
  exp: number;
  iss: string;
  aud: string;
};

export function createSessionToken(params: {
  user_id: string;
  display_name?: string;
  tenant_id: string;
  roles: Role[];
  session_id?: string;
  csrf_token?: string;
  ttlSeconds?: number;
  secret?: string;
  issuer?: string;
  audience?: string;
}): { token: string; claims: SessionTokenClaims } {
  const secret = params.secret ?? getSessionSecret();
  if (!secret) {
    throw new Error("WORKSPACE_SESSION_SECRET is not configured");
  }
  const now = Math.floor(Date.now() / 1000);
  const ttl = params.ttlSeconds ?? DEFAULT_SESSION_TTL_SECONDS;
  const claims: SessionTokenClaims = {
    sub: params.user_id,
    name: params.display_name || params.user_id,
    tenant_id: params.tenant_id,
    roles: params.roles,
    sid: params.session_id || crypto.randomUUID(),
    csrf: params.csrf_token || crypto.randomBytes(24).toString("hex"),
    iat: now,
    exp: now + ttl,
    iss: params.issuer || (process.env.OIDC_ISSUER_URL || "deepaudit-crosswalk").trim(),
    aud: params.audience || (process.env.OIDC_CLIENT_ID || "deepaudit-workspace").trim(),
  };

  const headerB64 = base64UrlEncode(JSON.stringify({ alg: "HS256", typ: "JWT" }));
  const payloadB64 = base64UrlEncode(JSON.stringify(claims));
  const signingInput = `${headerB64}.${payloadB64}`;
  const sig = base64UrlEncode(
    crypto.createHmac("sha256", secret).update(signingInput).digest()
  );
  return {
    token: `${signingInput}.${sig}`,
    claims,
  };
}

export function verifySessionToken(
  token: string,
  options?: {
    secret?: string;
    expectedIssuer?: string;
    expectedAudience?: string;
  }
): { ok: true; claims: SessionTokenClaims } | { ok: false; error: string } {
  const secret = options?.secret ?? getSessionSecret();
  if (!secret) {
    return { ok: false, error: "Session verification secret is not configured" };
  }
  const parts = (token || "").trim().split(".");
  if (parts.length !== 3) {
    return { ok: false, error: "Malformed session token" };
  }
  const [headerB64, payloadB64, providedSig] = parts;
  const signingInput = `${headerB64}.${payloadB64}`;
  const expectedSig = base64UrlEncode(
    crypto.createHmac("sha256", secret).update(signingInput).digest()
  );
  if (!constantTimeEqual(providedSig, expectedSig)) {
    return { ok: false, error: "Invalid session token signature" };
  }

  let rawClaims: Record<string, unknown>;
  try {
    rawClaims = JSON.parse(base64UrlDecodeToString(payloadB64));
  } catch {
    return { ok: false, error: "Invalid session token payload" };
  }

  const now = Math.floor(Date.now() / 1000);
  const exp = Number(rawClaims.exp);
  if (!Number.isFinite(exp) || exp <= now) {
    return { ok: false, error: "Session token has expired" };
  }

  const expectedIss =
    options?.expectedIssuer ||
    (process.env.OIDC_ISSUER_URL || "").trim() ||
    undefined;
  if (expectedIss && rawClaims.iss !== expectedIss && rawClaims.iss !== "deepaudit-crosswalk") {
    return { ok: false, error: "Invalid token issuer (iss)" };
  }

  const expectedAud =
    options?.expectedAudience ||
    (process.env.OIDC_CLIENT_ID || "").trim() ||
    undefined;
  if (expectedAud && rawClaims.aud !== expectedAud && rawClaims.aud !== "deepaudit-workspace") {
    return { ok: false, error: "Invalid token audience (aud)" };
  }

  const sub = String(rawClaims.sub || "").trim();
  const tenantId = String(rawClaims.tenant_id || "").trim();
  const sid = String(rawClaims.sid || "").trim();
  const csrf = String(rawClaims.csrf || "").trim();
  const rawRoles = Array.isArray(rawClaims.roles) ? rawClaims.roles : [];
  const roles = rawRoles
    .map((r) => normalizeRole(String(r)))
    .filter((r): r is Role => r !== null);

  if (!sub || !tenantId || !sid || roles.length === 0) {
    return {
      ok: false,
      error: "Session token is missing required identity, tenant, or role claims",
    };
  }

  if (isSessionRevoked(sid)) {
    return { ok: false, error: "Session has been logged out or revoked" };
  }

  return {
    ok: true,
    claims: {
      sub,
      name: String(rawClaims.name || sub),
      tenant_id: tenantId,
      roles,
      sid,
      csrf,
      iat: Number(rawClaims.iat || now),
      exp,
      iss: String(rawClaims.iss || "deepaudit-crosswalk"),
      aud: String(rawClaims.aud || "deepaudit-workspace"),
    },
  };
}

export function parseCookies(cookieHeader: string | null): Record<string, string> {
  const out: Record<string, string> = {};
  if (!cookieHeader) return out;
  for (const part of cookieHeader.split(";")) {
    const idx = part.indexOf("=");
    if (idx <= 0) continue;
    const k = part.slice(0, idx).trim();
    const v = part.slice(idx + 1).trim();
    if (k) {
      out[k] = decodeURIComponent(v);
    }
  }
  return out;
}

export function formatSessionCookie(token: string, maxAgeSeconds = DEFAULT_SESSION_TTL_SECONDS): string {
  const secure = isProductionEnv() ? "; Secure" : "";
  return `${SESSION_COOKIE_NAME}=${encodeURIComponent(
    token
  )}; Path=/; HttpOnly; SameSite=Lax; Max-Age=${maxAgeSeconds}${secure}`;
}

export function formatClearSessionCookie(): string {
  const secure = isProductionEnv() ? "; Secure" : "";
  return `${SESSION_COOKIE_NAME}=; Path=/; HttpOnly; SameSite=Lax; Max-Age=0${secure}`;
}

export function signBackendWorkspaceContext(
  ctx: Pick<SecurityContext, "user_id" | "tenant_id" | "roles" | "session_id">,
  secret?: string
): string {
  const signingSecret =
    secret ??
    ((process.env.WORKSPACE_SESSION_SECRET || "").trim() ||
      (process.env.CROSSWALK_CONTEXT_SECRET || "").trim());
  if (!signingSecret) {
    return "";
  }
  const payload = {
    exp: Math.floor(Date.now() / 1000) + 300,
    roles: ctx.roles,
    session_id: ctx.session_id,
    tenant_id: ctx.tenant_id,
    user_id: ctx.user_id,
  };
  const sortedKeys = Object.keys(payload).sort();
  const canonicalObj: Record<string, unknown> = {};
  for (const k of sortedKeys) {
    canonicalObj[k] = (payload as Record<string, unknown>)[k];
  }
  const bodyB64 = base64UrlEncode(JSON.stringify(canonicalObj));
  const sig = crypto
    .createHmac("sha256", signingSecret)
    .update(bodyB64, "ascii")
    .digest("hex");
  return `${bodyB64}.${sig}`;
}

function isLoopbackRequest(request: Request): boolean {
  try {
    const url = new URL(request.url);
    const host = url.hostname.toLowerCase();
    return host === "localhost" || host === "127.0.0.1" || host === "::1" || host === "[::1]";
  } catch {
    return false;
  }
}

export function authenticateUserCredentials(params: {
  username: string;
  password: string;
  tenant_id?: string;
}):
  | {
      ok: true;
      user: WorkspaceUserRecord;
      tenant_id: string;
      roles: Role[];
    }
  | { ok: false; status: number; error: string } {
  const users = loadWorkspaceUsers();
  const uname = (params.username || "").trim().toLowerCase();
  const pwd = params.password || "";

  let matchedUser: WorkspaceUserRecord | undefined;
  for (const u of users.values()) {
    if (
      u.username.toLowerCase() === uname ||
      u.user_id.toLowerCase() === uname ||
      `${u.username.toLowerCase()}@local.crosswalk` === uname
    ) {
      matchedUser = u;
      break;
    }
  }

  if (!matchedUser) {
    return { ok: false, status: 401, error: "Invalid username or password" };
  }
  if (matchedUser.disabled) {
    return { ok: false, status: 403, error: "User account has been disabled" };
  }

  let passwordValid = false;
  if (matchedUser.password_sha256) {
    const candidateHash = crypto.createHash("sha256").update(pwd, "utf8").digest("hex");
    passwordValid = constantTimeEqual(
      candidateHash.toLowerCase(),
      matchedUser.password_sha256.toLowerCase()
    );
  } else if (typeof matchedUser.password === "string") {
    passwordValid = constantTimeEqual(pwd, matchedUser.password);
  }

  if (!passwordValid) {
    return { ok: false, status: 401, error: "Invalid username or password" };
  }

  const availableTenants = Object.keys(matchedUser.tenants);
  if (availableTenants.length === 0) {
    return {
      ok: false,
      status: 403,
      error: "User account has no assigned tenant memberships",
    };
  }

  const requestedTenant = (params.tenant_id || "").trim() || availableTenants[0];
  const tenantRoles = matchedUser.tenants[requestedTenant];
  if (!tenantRoles || tenantRoles.length === 0) {
    return {
      ok: false,
      status: 403,
      error: `User '${matchedUser.user_id}' is not authorised for tenant '${requestedTenant}'`,
    };
  }

  return {
    ok: true,
    user: matchedUser,
    tenant_id: requestedTenant,
    roles: tenantRoles,
  };
}

export function resolveSecurityContext(
  request: Request,
  requestedTenantId?: string | null
):
  | { ok: true; context: SecurityContext }
  | { ok: false; status: number; error: string } {
  const configuredServerTenant = (process.env.BANKING_CROSSWALK_TENANT_ID || "").trim();
  if (configuredServerTenant.toLowerCase() === "public-demo") {
    return {
      ok: false,
      status: 403,
      error:
        "The shared public-demo tenant is strictly isolated and cannot access the private document workspace.",
    };
  }

  const effectiveRequestedTenant =
    requestedTenantId !== undefined
      ? requestedTenantId
      : request.headers.get("x-tenant-id");
  if (
    effectiveRequestedTenant &&
    effectiveRequestedTenant.trim().toLowerCase() === "public-demo"
  ) {
    return {
      ok: false,
      status: 403,
      error:
        "The shared public-demo tenant is strictly isolated and cannot access the private document workspace.",
    };
  }

  const modeStatus = detectDeploymentSecurityMode();
  if (!modeStatus.ready) {
    return {
      ok: false,
      status: 503,
      error: modeStatus.reason || "Document workspace authentication is not configured.",
    };
  }

  // Check Authorization header or X-Workspace-Token first (Bearer JWT or configured Bearer token)
  const authHeader = (request.headers.get("authorization") || "").trim();
  const workspaceTokenHeader = (request.headers.get("x-workspace-token") || "").trim();
  const cookies = parseCookies(request.headers.get("cookie"));
  const cookieToken = cookies[SESSION_COOKIE_NAME];

  let verifiedClaims: SessionTokenClaims | null = null;
  let authMethod: SecurityContext["auth_method"] | null = null;

  if (authHeader || workspaceTokenHeader) {
    let rawBearer = "";
    if (workspaceTokenHeader) {
      rawBearer = workspaceTokenHeader;
    } else if (authHeader.toLowerCase().startsWith("bearer ")) {
      rawBearer = authHeader.slice(7).trim();
    } else {
      return {
        ok: false,
        status: 401,
        error: "Invalid Authorization header scheme; expected Bearer token.",
      };
    }
    if (!rawBearer) {
      return {
        ok: false,
        status: 401,
        error: "Empty Bearer token in Authorization header.",
      };
    }

    const configuredToken = (process.env.WORKSPACE_AUTH_TOKEN || "").trim();
    if (configuredToken && constantTimeEqual(rawBearer, configuredToken)) {
      const actor =
        (process.env.BANKING_CROSSWALK_ACTOR || "").trim() || "workspace-token-user";
      const rawRole =
        (process.env.BANKING_CROSSWALK_ROLE || "").trim() || "reviewer";
      const role = normalizeRole(rawRole) || "reviewer";
      const tenantId = configuredServerTenant || "local-workspace";
      if (
        effectiveRequestedTenant &&
        effectiveRequestedTenant.trim() &&
        effectiveRequestedTenant.trim() !== tenantId
      ) {
        return {
          ok: false,
          status: 403,
          error: `Authenticated principal is not authorised for tenant '${effectiveRequestedTenant}'`,
        };
      }
      const roles: Role[] = [role];
      return {
        ok: true,
        context: {
          user_id: actor,
          display_name: actor,
          tenant_id: tenantId,
          authenticated: true,
          roles,
          permissions: permissionsForRoles(roles),
          session_id: "bearer-static-token",
          csrf_token: "bearer-not-applicable",
          deployment_mode: modeStatus.mode,
          auth_method: "bearer_token",
          expires_at: Math.floor(Date.now() / 1000) + 3600,
        },
      };
    }

    const verified = verifySessionToken(rawBearer);
    if (!verified.ok) {
      return { ok: false, status: 401, error: verified.error };
    }
    verifiedClaims = verified.claims;
    authMethod = "bearer_jwt";
  } else if (cookieToken) {
    const verified = verifySessionToken(cookieToken);
    if (!verified.ok) {
      return { ok: false, status: 401, error: verified.error };
    }
    verifiedClaims = verified.claims;
    authMethod = "session_cookie";
  }

  if (verifiedClaims && authMethod) {
    // Live user & tenant membership check against user store (if user exists in registry)
    const users = loadWorkspaceUsers();
    const registeredUser = users.get(verifiedClaims.sub);
    let effectiveRoles = verifiedClaims.roles;
    let effectiveTenant = verifiedClaims.tenant_id;

    if (registeredUser && registeredUser.disabled) {
      return {
        ok: false,
        status: 401,
        error: "User account access has been revoked",
      };
    }

    if (effectiveRequestedTenant && effectiveRequestedTenant.trim()) {
      const reqTid = effectiveRequestedTenant.trim();
      if (registeredUser) {
        const rolesInReqTenant = registeredUser.tenants[reqTid];
        if (!rolesInReqTenant || rolesInReqTenant.length === 0) {
          return {
            ok: false,
            status: 403,
            error: `User '${verifiedClaims.sub}' is not a member of tenant '${reqTid}'`,
          };
        }
        effectiveTenant = reqTid;
        effectiveRoles = rolesInReqTenant;
      } else if (reqTid !== verifiedClaims.tenant_id) {
        return {
          ok: false,
          status: 403,
          error: `Session is bound to tenant '${verifiedClaims.tenant_id}', not '${reqTid}'`,
        };
      }
    } else if (registeredUser) {
      const liveRoles = registeredUser.tenants[effectiveTenant];
      if (!liveRoles || liveRoles.length === 0) {
        return {
          ok: false,
          status: 403,
          error: `User '${verifiedClaims.sub}' is no longer a member of tenant '${effectiveTenant}'`,
        };
      }
      effectiveRoles = liveRoles;
    }

    if (
      isProductionEnv() &&
      configuredServerTenant &&
      !constantTimeEqual(effectiveTenant, configuredServerTenant)
    ) {
      return {
        ok: false,
        status: 403,
        error: "Authenticated tenant does not match the server-bound tenant",
      };
    }

    if (effectiveTenant.toLowerCase() === "public-demo") {
      return {
        ok: false,
        status: 403,
        error: "The 'public-demo' tenant cannot be used for private workspace sessions",
      };
    }

    return {
      ok: true,
      context: {
        user_id: verifiedClaims.sub,
        display_name: verifiedClaims.name,
        tenant_id: effectiveTenant,
        authenticated: true,
        roles: effectiveRoles,
        permissions: permissionsForRoles(effectiveRoles),
        session_id: verifiedClaims.sid,
        csrf_token: verifiedClaims.csrf,
        deployment_mode: modeStatus.mode,
        auth_method: authMethod,
        expires_at: verifiedClaims.exp,
      },
    };
  }

  // No session cookie or Bearer token was supplied.
  // Check if explicit local-only dev bypass is enabled in non-production on loopback.
  if (
    !isProductionEnv() &&
    modeStatus.mode === "local_dev_bypass" &&
    isLoopbackRequest(request)
  ) {
    const devTenant = configuredServerTenant || "local-workspace";
    if (
      requestedTenantId &&
      requestedTenantId.trim() &&
      requestedTenantId.trim() !== devTenant
    ) {
      return {
        ok: false,
        status: 403,
        error: "Cross-tenant request rejected in local dev bypass mode",
      };
    }
    const devRole =
      normalizeRole(process.env.BANKING_CROSSWALK_ROLE || "reviewer") || "reviewer";
    const roles: Role[] = [devRole];
    return {
      ok: true,
      context: {
        user_id:
          (process.env.BANKING_CROSSWALK_ACTOR || "").trim() || "local-dev-operator",
        display_name: "Local Dev Bypass Operator (UNAUTHENTICATED)",
        tenant_id: devTenant,
        authenticated: false,
        roles,
        permissions: permissionsForRoles(roles),
        session_id: "local-dev-bypass-session",
        csrf_token: "local-dev-csrf-token",
        deployment_mode: "local_dev_bypass",
        auth_method: "local_dev_bypass",
        expires_at: Math.floor(Date.now() / 1000) + 3600,
      },
    };
  }

  return {
    ok: false,
    status: 401,
    error:
      "Authentication required: sign in to access the private document workspace.",
  };
}

export function verifyCsrfProtection(
  request: Request,
  ctx: SecurityContext
): { ok: true } | { ok: false; status: number; error: string } {
  const method = (request.method || "GET").toUpperCase();
  if (method === "GET" || method === "HEAD" || method === "OPTIONS") {
    return { ok: true };
  }

  // Origin / Referer check when present
  const originHeader = request.headers.get("origin");
  const refererHeader = request.headers.get("referer");
  try {
    const reqUrl = new URL(request.url);
    const expectedOrigin = reqUrl.origin.toLowerCase();
    if (originHeader) {
      const actualOrigin = new URL(originHeader).origin.toLowerCase();
      if (actualOrigin !== expectedOrigin) {
        return {
          ok: false,
          status: 403,
          error: "CSRF origin validation failed: cross-origin state-changing request rejected.",
        };
      }
    } else if (refererHeader) {
      const actualRefererOrigin = new URL(refererHeader).origin.toLowerCase();
      if (actualRefererOrigin !== expectedOrigin) {
        return {
          ok: false,
          status: 403,
          error: "CSRF referer validation failed: cross-origin state-changing request rejected.",
        };
      }
    }
  } catch {
    return {
      ok: false,
      status: 403,
      error: "CSRF validation failed: malformed Origin or Referer header.",
    };
  }

  // Cookie-authenticated sessions require matching X-CSRF-Token header
  if (ctx.auth_method === "session_cookie") {
    const headerToken = (request.headers.get("x-csrf-token") || "").trim();
    if (!headerToken || !constantTimeEqual(headerToken, ctx.csrf_token)) {
      return {
        ok: false,
        status: 403,
        error: "CSRF token missing or invalid (X-CSRF-Token header required).",
      };
    }
  }

  return { ok: true };
}

// ─────────────────────────────────────────────────────────────────────────────
// OIDC / OAuth2 Authorization Code + PKCE Helpers
// ─────────────────────────────────────────────────────────────────────────────

export type OidcPkceState = {
  state: string;
  nonce: string;
  code_verifier: string;
  code_challenge: string;
  redirect_uri: string;
  exp: number;
};

export function createOidcPkceSession(redirectUri: string): {
  pkce: OidcPkceState;
  signedStateCookieValue: string;
  authorizeUrl: string;
} {
  const issuer = (process.env.OIDC_ISSUER_URL || "https://oidc.example.local").trim().replace(/\/+$/, "");
  const clientId = (process.env.OIDC_CLIENT_ID || "deepaudit-workspace").trim();
  const state = crypto.randomBytes(16).toString("hex");
  const nonce = crypto.randomBytes(16).toString("hex");
  const codeVerifier = base64UrlEncode(crypto.randomBytes(32));
  const codeChallenge = base64UrlEncode(
    crypto.createHash("sha256").update(codeVerifier, "ascii").digest()
  );
  const exp = Math.floor(Date.now() / 1000) + 600;

  const pkce: OidcPkceState = {
    state,
    nonce,
    code_verifier: codeVerifier,
    code_challenge: codeChallenge,
    redirect_uri: redirectUri,
    exp,
  };

  const secret = getSessionSecret();
  const payloadB64 = base64UrlEncode(JSON.stringify(pkce));
  const sig = base64UrlEncode(
    crypto.createHmac("sha256", secret).update(payloadB64).digest()
  );
  const signedStateCookieValue = `${payloadB64}.${sig}`;

  const authUrl = new URL(`${issuer}/authorize`);
  authUrl.searchParams.set("response_type", "code");
  authUrl.searchParams.set("client_id", clientId);
  authUrl.searchParams.set("redirect_uri", redirectUri);
  authUrl.searchParams.set("scope", "openid profile email roles");
  authUrl.searchParams.set("state", state);
  authUrl.searchParams.set("nonce", nonce);
  authUrl.searchParams.set("code_challenge", codeChallenge);
  authUrl.searchParams.set("code_challenge_method", "S256");

  return {
    pkce,
    signedStateCookieValue,
    authorizeUrl: authUrl.toString(),
  };
}

export function verifyOidcCallbackAndIssueSession(params: {
  callbackState: string;
  signedStateCookie: string;
  idToken: string;
  expectedIssuer?: string;
  expectedAudience?: string;
}):
  | { ok: true; sessionToken: string; claims: SessionTokenClaims }
  | { ok: false; status: number; error: string } {
  const secret = getSessionSecret();
  if (!secret) {
    return { ok: false, status: 503, error: "Session secret is not configured" };
  }
  const cookieParts = (params.signedStateCookie || "").split(".");
  if (cookieParts.length !== 2) {
    return { ok: false, status: 401, error: "Missing or malformed OIDC PKCE state cookie" };
  }
  const [payloadB64, sig] = cookieParts;
  const expectedSig = base64UrlEncode(
    crypto.createHmac("sha256", secret).update(payloadB64).digest()
  );
  if (!constantTimeEqual(sig, expectedSig)) {
    return { ok: false, status: 401, error: "Invalid OIDC PKCE state cookie signature" };
  }

  let pkceState: OidcPkceState;
  try {
    pkceState = JSON.parse(base64UrlDecodeToString(payloadB64));
  } catch {
    return { ok: false, status: 401, error: "Malformed OIDC PKCE state payload" };
  }

  if (pkceState.exp <= Math.floor(Date.now() / 1000)) {
    return { ok: false, status: 401, error: "OIDC authorization state has expired" };
  }
  if (
    !params.callbackState ||
    !constantTimeEqual(params.callbackState, pkceState.state)
  ) {
    return { ok: false, status: 401, error: "OIDC state mismatch" };
  }

  // Verify the ID token (JWT signed with OIDC_CLIENT_SECRET or WORKSPACE_SESSION_SECRET)
  const idTokenSecret =
    (process.env.OIDC_CLIENT_SECRET || "").trim() || secret;
  const parts = (params.idToken || "").split(".");
  if (parts.length !== 3) {
    return { ok: false, status: 401, error: "Malformed OIDC ID token" };
  }
  const [idHeader, idPayload, idSig] = parts;
  const expectedIdSig = base64UrlEncode(
    crypto
      .createHmac("sha256", idTokenSecret)
      .update(`${idHeader}.${idPayload}`)
      .digest()
  );
  if (!constantTimeEqual(idSig, expectedIdSig)) {
    return { ok: false, status: 401, error: "Invalid OIDC ID token signature" };
  }

  let idClaims: Record<string, unknown>;
  try {
    idClaims = JSON.parse(base64UrlDecodeToString(idPayload));
  } catch {
    return { ok: false, status: 401, error: "Malformed OIDC ID token claims" };
  }

  const now = Math.floor(Date.now() / 1000);
  if (!Number.isFinite(Number(idClaims.exp)) || Number(idClaims.exp) <= now) {
    return { ok: false, status: 401, error: "OIDC ID token has expired" };
  }

  const expectedIss =
    params.expectedIssuer ||
    (process.env.OIDC_ISSUER_URL || "https://oidc.example.local").trim();
  if (idClaims.iss !== expectedIss) {
    return { ok: false, status: 401, error: "OIDC ID token issuer (iss) mismatch" };
  }

  const expectedAud =
    params.expectedAudience ||
    (process.env.OIDC_CLIENT_ID || "deepaudit-workspace").trim();
  if (idClaims.aud !== expectedAud) {
    return { ok: false, status: 401, error: "OIDC ID token audience (aud) mismatch" };
  }

  if (
    !idClaims.nonce ||
    !constantTimeEqual(String(idClaims.nonce), pkceState.nonce)
  ) {
    return { ok: false, status: 401, error: "OIDC ID token nonce mismatch" };
  }

  const sub = String(idClaims.sub || "").trim();
  const tenantId = String(
    idClaims.tenant_id ||
      process.env.BANKING_CROSSWALK_TENANT_ID ||
      "local-workspace"
  ).trim();
  const rawRoles = Array.isArray(idClaims.roles)
    ? idClaims.roles
    : idClaims.role
    ? [idClaims.role]
    : ["viewer"];
  const roles = rawRoles
    .map((r) => normalizeRole(String(r)))
    .filter((r): r is Role => r !== null);

  if (!sub || roles.length === 0) {
    return {
      ok: false,
      status: 401,
      error: "OIDC ID token is missing required sub or role claims",
    };
  }

  const issued = createSessionToken({
    user_id: sub,
    display_name: String(idClaims.name || idClaims.email || sub),
    tenant_id: tenantId,
    roles,
  });

  return {
    ok: true,
    sessionToken: issued.token,
    claims: issued.claims,
  };
}
