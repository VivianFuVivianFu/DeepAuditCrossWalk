import crypto from "node:crypto";
import fs from "node:fs";
import path from "node:path";

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
  password_hash?: string;
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

// ─────────────────────────────────────────────────────────────────────────────
// Durable Server-Side Session Revocation Store
// ─────────────────────────────────────────────────────────────────────────────

type RevocationEntry = {
  sid: string;
  revokedAt: number;
  expiresAt: number;
};

export class DurableRevocationStore {
  private memory = new Map<string, number>();
  private filePath: string | null = null;
  private initialized = false;

  private resolveFilePath(): string | null {
    const configured = (process.env.SESSION_REVOCATION_PATH || "").trim();
    if (configured) {
      return path.resolve(configured);
    }
    const tmp = process.env.TMPDIR || process.env.TEMP || process.env.TMP || "/tmp";
    return path.join(tmp, "crosswalk_revocations.json");
  }

  private ensureLoaded(): void {
    if (this.initialized) return;
    this.initialized = true;
    this.filePath = this.resolveFilePath();
    if (!this.filePath) return;
    try {
      if (fs.existsSync(this.filePath)) {
        const raw = fs.readFileSync(this.filePath, "utf8");
        const parsed: RevocationEntry[] = JSON.parse(raw);
        const now = Math.floor(Date.now() / 1000);
        for (const entry of parsed) {
          if (entry && entry.sid && entry.expiresAt > now) {
            this.memory.set(entry.sid, entry.expiresAt);
          }
        }
      }
    } catch {
      // In-memory fallback if file unreadable
    }
  }

  private persist(): void {
    this.filePath = this.resolveFilePath();
    if (!this.filePath) return;
    try {
      const now = Math.floor(Date.now() / 1000);
      const entries: RevocationEntry[] = [];
      for (const [sid, exp] of this.memory.entries()) {
        if (exp > now) {
          entries.push({ sid, revokedAt: now, expiresAt: exp });
        }
      }
      const dir = path.dirname(this.filePath);
      if (!fs.existsSync(dir)) {
        fs.mkdirSync(dir, { recursive: true });
      }
      const tmp = `${this.filePath}.${process.pid}.${Date.now()}.tmp`;
      fs.writeFileSync(tmp, JSON.stringify(entries), "utf8");
      fs.renameSync(tmp, this.filePath);
    } catch {
      // In-memory fallback if file write fails
    }
  }

  revoke(sid: string, expiresAt: number = Math.floor(Date.now() / 1000) + DEFAULT_SESSION_TTL_SECONDS): void {
    if (!sid) return;
    this.ensureLoaded();
    this.memory.set(sid, expiresAt);
    this.persist();
  }

  isRevoked(sid: string): boolean {
    if (!sid) return false;
    this.ensureLoaded();
    const exp = this.memory.get(sid);
    if (!exp) return false;
    const now = Math.floor(Date.now() / 1000);
    if (exp <= now) {
      this.memory.delete(sid);
      return false;
    }
    return true;
  }

  clear(): void {
    this.memory.clear();
    this.initialized = false;
    const fp = this.resolveFilePath();
    if (fp && fs.existsSync(fp)) {
      try {
        fs.unlinkSync(fp);
      } catch {}
    }
  }
}

const revocationStore = new DurableRevocationStore();
const runtimeUserOverrides = new Map<string, WorkspaceUserRecord>();

type AttemptRecord = { count: number; firstAttempt: number };
const failedLoginAttempts = new Map<string, AttemptRecord>();

export function clearLoginRateLimitsForTests(): void {
  failedLoginAttempts.clear();
}

function getLoginRateLimitKey(request: Request, username: string): string {
  const xff = (request.headers.get("x-forwarded-for") || "").split(",")[0].trim();
  const ip = xff || "direct";
  return `${ip}:${username.toLowerCase()}`;
}

export function checkLoginRateLimit(request: Request, username: string): boolean {
  const key = getLoginRateLimitKey(request, username);
  const record = failedLoginAttempts.get(key);
  if (!record) return true;
  const now = Date.now();
  if (now - record.firstAttempt > 60_000) {
    failedLoginAttempts.delete(key);
    return true;
  }
  return record.count < 5;
}

export function recordLoginFailedAttempt(request: Request, username: string): void {
  const key = getLoginRateLimitKey(request, username);
  const now = Date.now();
  const record = failedLoginAttempts.get(key);
  if (!record || now - record.firstAttempt > 60_000) {
    failedLoginAttempts.set(key, { count: 1, firstAttempt: now });
  } else {
    record.count += 1;
  }
}

export function clearLoginRateLimit(request: Request, username: string): void {
  const key = getLoginRateLimitKey(request, username);
  failedLoginAttempts.delete(key);
}

export function clearSecurityStateForTests(): void {
  revocationStore.clear();
  runtimeUserOverrides.clear();
  failedLoginAttempts.clear();
}

export function revokeSession(sessionId: string, expiresAt?: number): void {
  if (sessionId) {
    revocationStore.revoke(sessionId, expiresAt);
  }
}

export function isSessionRevoked(sessionId: string): boolean {
  return revocationStore.isRevoked(sessionId);
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

export function hashPassword(password: string): string {
  if (!password || typeof password !== "string") {
    throw new Error("Password must be a non-empty string");
  }
  const salt = crypto.randomBytes(16).toString("hex");
  const derived = crypto.scryptSync(password, salt, 64, {
    N: 16384,
    r: 8,
    p: 1,
  });
  return `scrypt$${salt}$${derived.toString("hex")}`;
}

export function verifyPassword(
  candidate: string,
  user: WorkspaceUserRecord,
  isProduction: boolean
): boolean {
  if (!candidate || typeof candidate !== "string") {
    return false;
  }
  if (user.password_hash) {
    if (user.password_hash.startsWith("scrypt$")) {
      const parts = user.password_hash.split("$");
      if (parts.length !== 3) return false;
      const [, salt, expectedHashHex] = parts;
      const derived = crypto.scryptSync(candidate, salt, 64, {
        N: 16384,
        r: 8,
        p: 1,
      });
      const bufExpected = Buffer.from(expectedHashHex, "hex");
      if (derived.length !== bufExpected.length) return false;
      return crypto.timingSafeEqual(derived, bufExpected);
    }
    if (user.password_hash.startsWith("pbkdf2$")) {
      const parts = user.password_hash.split("$");
      if (parts.length !== 4) return false;
      const [, iterStr, salt, expectedHashHex] = parts;
      const iters = parseInt(iterStr, 10);
      if (isNaN(iters) || iters < 10000) return false;
      const derived = crypto.pbkdf2Sync(candidate, salt, iters, 64, "sha256");
      const bufExpected = Buffer.from(expectedHashHex, "hex");
      if (derived.length !== bufExpected.length) return false;
      return crypto.timingSafeEqual(derived, bufExpected);
    }
    return false;
  }

  // Legacy insecure password formats (plain sha256 or plaintext):
  // Strictly REJECTED in production
  if (isProduction) {
    return false;
  }

  // Non-production fallback for development/test fixtures only
  if (user.password_sha256) {
    const candidateHash = crypto.createHash("sha256").update(candidate, "utf8").digest("hex");
    return constantTimeEqual(candidateHash.toLowerCase(), user.password_sha256.toLowerCase());
  }
  if (typeof user.password === "string") {
    return constantTimeEqual(candidate, user.password);
  }
  return false;
}

function defaultTestFixtureUsers(): WorkspaceUserRecord[] {
  const defaultTenant =
    (process.env.BANKING_CROSSWALK_TENANT_ID || "").trim() || "local-workspace";
  return [
    {
      user_id: "usr-local-analyst",
      username: "analyst",
      display_name: "Local Governance Analyst",
      password_hash:
        "scrypt$e5a38ab4c74f5339c3b73dfbae7552e5$e305fd070e4334ca1af6b655f6e9ebab217c42c8c2efda066b8640832dbc88e0ebe1eebeab88db74d3ee7730788ff399b64df6d6748552cfb5abf678436f7155",
      password: "analyst-local-pass",
      tenants: { [defaultTenant]: ["analyst"] },
    },
    {
      user_id: "usr-local-reviewer",
      username: "reviewer",
      display_name: "Local Compliance Reviewer",
      password_hash:
        "scrypt$b3c11b6fe4df7d1c847b09d108cd8935$5b272507d239e7827a5e08f07e35113e7ac35766cce9a09a6e7dd4584f38150a7a3fa2cc589453f60d90d63e1f0976eaf45ff96fe6b9c143879b7a0e834552b7",
      password: "reviewer-local-pass",
      tenants: { [defaultTenant]: ["reviewer"] },
    },
    {
      user_id: "usr-local-viewer",
      username: "viewer",
      display_name: "Local Audit Viewer",
      password_hash:
        "scrypt$607fbf979105b278aafbc3627b89cc3b$28de084fe270b26b79be558ce1e0b9b6d81df850a07b658fa4fbe3afbc0dcc4692bc525ac49732ef00056b516b0ba43a2daf247cfcca91d994e060016f7742a3",
      password: "viewer-local-pass",
      tenants: { [defaultTenant]: ["viewer"] },
    },
    {
      user_id: "usr-local-admin",
      username: "admin",
      display_name: "Local Workspace Admin",
      password_hash:
        "scrypt$a4aed08f1c2b819a4993937782acbbb8$501b0a37d097b3a96f064d408c678c0e2d54aa5cabf6756178f6ea1786c17a8467cfe3f880170fe4fed564373be90a33804f9ef4d91bf9d2955392ad4752352a",
      password: "admin-local-pass",
      tenants: { [defaultTenant]: ["admin"] },
    },
  ];
}

export function loadWorkspaceUsers(): Map<string, WorkspaceUserRecord> {
  const map = new Map<string, WorkspaceUserRecord>();
  const rawJson = (process.env.WORKSPACE_USERS_JSON || "").trim();
  const prod = isProductionEnv();

  if (rawJson) {
    try {
      const parsed = JSON.parse(rawJson);
      if (Array.isArray(parsed)) {
        for (const item of parsed) {
          if (!item || typeof item !== "object") continue;
          const userId = String(item.user_id || item.username || "").trim();
          const username = String(item.username || item.user_id || "").trim();
          if (!userId || !username) continue;

          // In production, reject accounts with insecure plaintext/unsalted password formats
          if (prod && !item.password_hash) {
            continue;
          }

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
            password_hash: item.password_hash ? String(item.password_hash) : undefined,
            password: item.password && !prod ? String(item.password) : undefined,
            password_sha256:
              item.password_sha256 && !prod
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
  } else if (!prod) {
    for (const u of defaultTestFixtureUsers()) {
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
    if (!hasUsersJson && !hasBearerToken) {
      return {
        mode: "misconfigured_production",
        ready: false,
        reason:
          "Document workspace authentication is not configured: an identity provider (WORKSPACE_USERS_JSON) is required in production. OIDC is currently experimental and disabled for hosted production.",
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
    const xff = request.headers.get("x-forwarded-for");
    const xri = request.headers.get("x-real-ip");
    const forwarded = request.headers.get("forwarded");
    const xfh = request.headers.get("x-forwarded-host");
    if (xff || xri || forwarded || xfh) {
      return false;
    }
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
  const prod = isProductionEnv();

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
    try {
      crypto.scryptSync(pwd, "dummy-salt-16bytes", 64, { N: 16384, r: 8, p: 1 });
    } catch {}
    return { ok: false, status: 401, error: "Invalid username or password" };
  }
  if (matchedUser.disabled) {
    return { ok: false, status: 401, error: "Invalid username or password" };
  }

  const passwordValid = verifyPassword(pwd, matchedUser, prod);
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
        (process.env.BANKING_CROSSWALK_ACTOR || "").trim() || "service-automation";
      // Static automation tokens cannot impersonate human reviewers or approve requirements
      const staticRoles: Role[] = ["viewer"];
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
      return {
        ok: true,
        context: {
          user_id: `svc-${actor}`,
          display_name: `Automated Service Principal (${actor})`,
          tenant_id: tenantId,
          authenticated: true,
          roles: staticRoles,
          permissions: permissionsForRoles(staticRoles).filter(
            (p) =>
              p !== "clause:review" &&
              p !== "mapping:review" &&
              p !== "baseline:create" &&
              p !== "policy:delete"
          ),
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
    if (
      verifiedClaims.tenant_id.toLowerCase() === "public-demo" ||
      (effectiveRequestedTenant &&
        effectiveRequestedTenant.trim().toLowerCase() === "public-demo")
    ) {
      return {
        ok: false,
        status: 403,
        error:
          "The 'public-demo' tenant cannot be used for private workspace sessions",
      };
    }

    if (isSessionRevoked(verifiedClaims.sid)) {
      return { ok: false, status: 401, error: "Session has been logged out or revoked" };
    }

    // Live user & tenant membership check against user store
    const users = loadWorkspaceUsers();
    const registeredUser = users.get(verifiedClaims.sub);

    // Requirement 7: A deleted local user must not retain access through an old signed session
    if (!registeredUser) {
      return {
        ok: false,
        status: 401,
        error: "User account no longer exists in workspace registry",
      };
    }

    if (registeredUser.disabled) {
      return {
        ok: false,
        status: 401,
        error: "User account access has been revoked",
      };
    }

    let effectiveTenant = verifiedClaims.tenant_id;
    if (effectiveRequestedTenant && effectiveRequestedTenant.trim()) {
      effectiveTenant = effectiveRequestedTenant.trim();
    }

    const liveTenantRoles = registeredUser.tenants[effectiveTenant];
    if (!liveTenantRoles || liveTenantRoles.length === 0) {
      return {
        ok: false,
        status: 403,
        error: `User '${verifiedClaims.sub}' is not a member of tenant '${effectiveTenant}'`,
      };
    }

    // Live roles override static token claims (role downgrades take effect immediately)
    const effectiveRoles = liveTenantRoles;

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
    const isLoopback = (h: string) =>
      h === "localhost" || h === "127.0.0.1" || h === "::1" || h === "[::1]";

    const matchesExpected = (candidateOrigin: string) => {
      const cand = new URL(candidateOrigin);
      if (cand.origin.toLowerCase() === expectedOrigin) return true;
      if (
        cand.port === reqUrl.port &&
        cand.protocol.toLowerCase() === reqUrl.protocol.toLowerCase() &&
        isLoopback(cand.hostname.toLowerCase()) &&
        isLoopback(reqUrl.hostname.toLowerCase())
      ) {
        return true;
      }
      return false;
    };

    if (originHeader) {
      if (!matchesExpected(originHeader)) {
        return {
          ok: false,
          status: 403,
          error:
            "CSRF origin validation failed: cross-origin state-changing request rejected.",
        };
      }
    } else if (refererHeader) {
      if (!matchesExpected(refererHeader)) {
        return {
          ok: false,
          status: 403,
          error:
            "CSRF referer validation failed: cross-origin state-changing request rejected.",
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
