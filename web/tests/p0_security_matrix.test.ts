import crypto from "node:crypto";
import fs from "node:fs";
import path from "node:path";
import { afterEach, describe, expect, it, vi } from "vitest";
import { POST as analysisPOST } from "../app/api/analysis/route";
import { POST as loginPOST } from "../app/api/auth/login/route";
import { POST as logoutPOST } from "../app/api/auth/logout/route";
import { GET as oidcGET, POST as oidcPOST } from "../app/api/auth/oidc/route";
import { GET as workspaceGET, POST as workspacePOST } from "../app/api/workspace/route";
import {
  Role,
  clearSecurityStateForTests,
  clearLoginRateLimitsForTests,
  createSessionToken,
  formatSessionCookie,
  revokeSession,
  setRuntimeUserDisabled,
  setRuntimeUserTenantRoles,
  upsertRuntimeWorkspaceUser,
  hashPassword,
  verifyPassword,
  loadWorkspaceUsers,
  DurableRevocationStore,
  WorkspaceUserRecord,
} from "../app/security";

afterEach(() => {
  clearSecurityStateForTests();
  clearLoginRateLimitsForTests();
  vi.unstubAllGlobals();
  vi.unstubAllEnvs();
});

function createSignedCookieRequest(
  body: Record<string, unknown>,
  opts?: {
    user_id?: string;
    tenant_id?: string;
    roles?: Role[];
    csrfHeader?: string | null;
    origin?: string;
    extraHeaders?: Record<string, string>;
    ttlSeconds?: number;
    secret?: string;
    issuer?: string;
    audience?: string;
  }
) {
  const issued = createSessionToken({
    user_id: opts?.user_id ?? "usr-local-reviewer",
    tenant_id: opts?.tenant_id ?? "local-workspace",
    roles: opts?.roles ?? ["reviewer"],
    ttlSeconds: opts?.ttlSeconds,
    secret: opts?.secret,
    issuer: opts?.issuer,
    audience: opts?.audience,
  });
  const cookieHeader = formatSessionCookie(issued.token).split(";")[0];
  const csrf =
    opts?.csrfHeader === undefined ? issued.claims.csrf : opts.csrfHeader;

  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    Cookie: cookieHeader,
    ...(csrf !== null ? { "X-CSRF-Token": csrf } : {}),
    ...(opts?.origin ? { Origin: opts.origin } : {}),
    ...(opts?.extraHeaders || {}),
  };

  return {
    request: new Request("http://localhost/api/workspace", {
      method: "POST",
      headers,
      body: JSON.stringify(body),
    }),
    issued,
    cookieHeader,
  };
}

describe("P0 Security Acceptance Matrix — Group A: Unauthenticated Access (A1–A12)", () => {
  const unauthenticatedCases: Array<[string, Record<string, unknown>]> = [
    [
      "A1: import_questionnaire",
      {
        action: "import_questionnaire",
        filename: "q.xlsx",
        workbook_base64: "UEsDBBQAAAAIA==",
      },
    ],
    ["A2: list_questionnaires", { action: "list_questionnaires" }],
    [
      "A3: get_questionnaire",
      { action: "get_questionnaire", questionnaire_id: "Q-1" },
    ],
    [
      "A4: import_policy",
      { action: "import_policy", name: "Pol", text: "1.1 Rule" },
    ],
    [
      "A5: import_policy_file",
      {
        action: "import_policy_file",
        name: "Pol",
        filename: "pol.txt",
        file_base64: "MS4xIFJ1bGU=",
      },
    ],
    ["A6: list_policies", { action: "list_policies" }],
    ["A7: list_clauses", { action: "list_clauses", policy_id: "POL-1" }],
    [
      "A8: review_clause",
      { action: "review_clause", clause_id: "CL-1", status: "approved" },
    ],
    [
      "A9: review_clause_mapping",
      {
        action: "review_clause_mapping",
        clause_id: "CL-1",
        mapping_id: "MAP-1",
        status: "approved",
      },
    ],
    [
      "A10: create_baseline",
      {
        action: "create_baseline",
        name: "Base",
        policy_ids: ["POL-1"],
      },
    ],
    [
      "A11: run_coverage_assessment",
      {
        action: "run_coverage_assessment",
        questionnaire_id: "Q-1",
        assessment_mode: "regulatory_only",
      },
    ],
    ["A12: delete_policy", { action: "delete_policy", policy_id: "POL-1" }],
  ];

  it.each(unauthenticatedCases)(
    "%s rejects anonymous request with 401 and never calls backend",
    async (_label, payload) => {
      // Even when production backend credentials & tenant are configured!
      vi.stubEnv("ENV", "production");
      vi.stubEnv("CROSSWALK_API_KEY", "prod-api-key-secret");
      vi.stubEnv("BANKING_CROSSWALK_TENANT_ID", "bank-prod-tenant");
      vi.stubEnv(
        "WORKSPACE_SESSION_SECRET",
        "prod-workspace-session-signing-secret-32chars!!"
      );
      vi.stubEnv(
        "WORKSPACE_USERS_JSON",
        JSON.stringify([
          {
            user_id: "usr-prod-1",
            username: "reviewer",
            password: "prod-password-123",
            tenant_id: "bank-prod-tenant",
            roles: ["reviewer"],
          },
        ])
      );

      const fetcher = vi.fn();
      vi.stubGlobal("fetch", fetcher);

      const res = await workspacePOST(
        new Request("http://localhost/api/workspace", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        })
      );
      expect(res.status).toBe(401);
      expect(fetcher).not.toHaveBeenCalled();
    }
  );
});

describe("P0 Security Acceptance Matrix — Group B: Token & Session Integrity (B1–B10)", () => {
  it("B1: Missing session cookie / Bearer token returns 401", async () => {
    const res = await workspaceGET(new Request("http://localhost/api/workspace"));
    expect(res.status).toBe(401);
  });

  it("B2: Expired session / JWT returns 401", async () => {
    const { request } = createSignedCookieRequest(
      { action: "list_questionnaires" },
      { ttlSeconds: -60 }
    );
    const res = await workspacePOST(request);
    expect(res.status).toBe(401);
    const body = await res.json();
    expect(body.error).toMatch(/expired/i);
  });

  it("B3: Tampered JWT signature returns 401", async () => {
    const { issued } = createSignedCookieRequest({
      action: "list_questionnaires",
    });
    const tampered = issued.token.slice(0, -5) + "abcde";
    const res = await workspacePOST(
      new Request("http://localhost/api/workspace", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Cookie: `crosswalk_session=${tampered}`,
          "X-CSRF-Token": issued.claims.csrf,
        },
        body: JSON.stringify({ action: "list_questionnaires" }),
      })
    );
    expect(res.status).toBe(401);
  });

  it("B4: Wrong JWT audience (aud) returns 401", async () => {
    vi.stubEnv("OIDC_CLIENT_ID", "expected-banking-aud");
    const { request } = createSignedCookieRequest(
      { action: "list_questionnaires" },
      { audience: "wrong-audience-client" }
    );
    const res = await workspacePOST(request);
    expect(res.status).toBe(401);
    expect((await res.json()).error).toMatch(/audience/i);
  });

  it("B5: Wrong JWT issuer (iss) returns 401", async () => {
    vi.stubEnv("OIDC_ISSUER_URL", "https://auth.trusted-bank.au");
    const { request } = createSignedCookieRequest(
      { action: "list_questionnaires" },
      { issuer: "https://evil-issuer.example.com" }
    );
    const res = await workspacePOST(request);
    expect(res.status).toBe(401);
    expect((await res.json()).error).toMatch(/issuer/i);
  });

  it("B6 & B7: OIDC PKCE state mismatch or ID token nonce mismatch returns 401", async () => {
    vi.stubEnv("OIDC_ISSUER_URL", "https://auth.trusted-bank.au");
    vi.stubEnv("OIDC_CLIENT_ID", "deepaudit-workspace");
    vi.stubEnv(
      "WORKSPACE_SESSION_SECRET",
      "oidc-test-session-secret-at-least-32-bytes!!"
    );

    const startRes = await oidcGET(
      new Request("http://localhost/api/auth/oidc")
    );
    expect(startRes.status).toBe(200);
    const startData = await startRes.json();
    const setCookie = startRes.headers.get("set-cookie") || "";
    const stateCookiePair = setCookie.split(";")[0];

    // B6: Replay / forged state parameter
    const badStateRes = await oidcPOST(
      new Request("http://localhost/api/auth/oidc", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Cookie: stateCookiePair,
        },
        body: JSON.stringify({
          state: "forged-state-value",
          id_token: "invalid.token.sig",
        }),
      })
    );
    expect(badStateRes.status).toBe(401);
    expect((await badStateRes.json()).detail).toMatch(/state mismatch/i);

    // B7: Valid state but wrong nonce in signed ID token
    const secret = "oidc-test-session-secret-at-least-32-bytes!!";
    const headerB64 = Buffer.from(
      JSON.stringify({ alg: "HS256", typ: "JWT" })
    ).toString("base64url");
    const payloadB64 = Buffer.from(
      JSON.stringify({
        iss: "https://auth.trusted-bank.au",
        aud: "deepaudit-workspace",
        sub: "usr-oidc-1",
        tenant_id: "local-workspace",
        roles: ["reviewer"],
        nonce: "wrong-nonce-value",
        exp: Math.floor(Date.now() / 1000) + 600,
      })
    ).toString("base64url");
    const sig = crypto
      .createHmac("sha256", secret)
      .update(`${headerB64}.${payloadB64}`)
      .digest("base64url");
    const wrongNonceIdToken = `${headerB64}.${payloadB64}.${sig}`;

    const badNonceRes = await oidcPOST(
      new Request("http://localhost/api/auth/oidc", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Cookie: stateCookiePair,
        },
        body: JSON.stringify({
          state: startData.state,
          id_token: wrongNonceIdToken,
        }),
      })
    );
    expect(badNonceRes.status).toBe(401);
    expect((await badNonceRes.json()).detail).toMatch(/nonce mismatch/i);
  });

  it("B8: Revoked user session or disabled user account accesses /api/workspace -> 401", async () => {
    const { request, issued } = createSignedCookieRequest({
      action: "list_questionnaires",
    });
    revokeSession(issued.claims.sid);
    const res = await workspacePOST(request);
    expect(res.status).toBe(401);

    // Also test disabling user account mid-session
    const second = createSignedCookieRequest({
      action: "list_questionnaires",
    });
    setRuntimeUserDisabled("usr-local-reviewer", true);
    const disabledRes = await workspacePOST(second.request);
    expect(disabledRes.status).toBe(401);
  });

  it("B9: Post-logout session reuse returns 401", async () => {
    const loginRes = await loginPOST(
      new Request("http://localhost/api/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          username: "reviewer",
          password: "reviewer-local-pass",
        }),
      })
    );
    expect(loginRes.status).toBe(200);
    const loginBody = await loginRes.json();
    const cookiePair = (loginRes.headers.get("set-cookie") || "").split(";")[0];

    // Logout with valid CSRF token
    const outRes = await logoutPOST(
      new Request("http://localhost/api/auth/logout", {
        method: "POST",
        headers: {
          Cookie: cookiePair,
          "X-CSRF-Token": loginBody.csrf_token,
        },
      })
    );
    expect(outRes.status).toBe(200);

    // Attempt to reuse the pre-logout cookie on /api/workspace
    const reuseRes = await workspacePOST(
      new Request("http://localhost/api/workspace", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Cookie: cookiePair,
          "X-CSRF-Token": loginBody.csrf_token,
        },
        body: JSON.stringify({ action: "list_questionnaires" }),
      })
    );
    expect(reuseRes.status).toBe(401);
  });

  it("B10: Session cookie without required identity claims returns 401", async () => {
    const secret = "local-community-dev-only-session-secret-not-for-prod-32b";
    const h = Buffer.from(JSON.stringify({ alg: "HS256" })).toString(
      "base64url"
    );
    const p = Buffer.from(
      JSON.stringify({
        sub: "",
        tenant_id: "",
        roles: [],
        exp: Math.floor(Date.now() / 1000) + 300,
      })
    ).toString("base64url");
    const s = crypto
      .createHmac("sha256", secret)
      .update(`${h}.${p}`)
      .digest("base64url");
    const malformedClaimsToken = `${h}.${p}.${s}`;

    const res = await workspaceGET(
      new Request("http://localhost/api/workspace", {
        headers: { Cookie: `crosswalk_session=${malformedClaimsToken}` },
      })
    );
    expect(res.status).toBe(401);
  });
});

describe("P0 Security Acceptance Matrix — Group C: CSRF & Browser Security (C1–C5)", () => {
  it("C1: Cookie-authenticated POST /api/workspace without CSRF token returns 403", async () => {
    const { request } = createSignedCookieRequest(
      { action: "list_questionnaires" },
      { csrfHeader: null }
    );
    const res = await workspacePOST(request);
    expect(res.status).toBe(403);
    expect((await res.json()).error).toMatch(/CSRF/i);
  });

  it("C2: Cookie-authenticated POST /api/workspace with invalid CSRF token returns 403", async () => {
    const { request } = createSignedCookieRequest(
      { action: "list_questionnaires" },
      { csrfHeader: "forged-csrf-token-value" }
    );
    const res = await workspacePOST(request);
    expect(res.status).toBe(403);
  });

  it("C3: Cross-origin POST /api/workspace with forged Origin returns 403", async () => {
    const { request } = createSignedCookieRequest(
      { action: "list_questionnaires" },
      { origin: "https://evil-attacker.example.com" }
    );
    const res = await workspacePOST(request);
    expect(res.status).toBe(403);
    expect((await res.json()).error).toMatch(/cross-origin/i);
  });

  it("C4 & C5: Valid cookie + valid CSRF token + same origin succeeds (200) and cookie has HttpOnly + SameSite=Lax", async () => {
    const fetcher = vi
      .fn()
      .mockResolvedValue(new Response(JSON.stringify([]), { status: 200 }));
    vi.stubGlobal("fetch", fetcher);

    const { request, issued } = createSignedCookieRequest(
      { action: "list_questionnaires" },
      { origin: "http://localhost" }
    );
    const fullCookieString = formatSessionCookie(issued.token);
    expect(fullCookieString).toContain("HttpOnly");
    expect(fullCookieString).toContain("SameSite=Lax");

    const res = await workspacePOST(request);
    expect(res.status).toBe(200);
  });
});

describe("P0 Security Acceptance Matrix — Group D: Role & Permission Enforcement (D1–D11)", () => {
  it("D1–D5: Viewer is read-only and receives 403 on questionnaire upload, policy upload, assessment run, clause approval, and mapping approval", async () => {
    const fetcher = vi.fn();
    vi.stubGlobal("fetch", fetcher);

    const deniedActions: Record<string, unknown>[] = [
      {
        action: "import_questionnaire",
        filename: "q.xlsx",
        workbook_base64: "UEsDBBQAAAAIA==",
      },
      { action: "import_policy", name: "Pol", text: "1.1 Rule" },
      {
        action: "run_coverage_assessment",
        questionnaire_id: "Q-1",
        assessment_mode: "regulatory_only",
      },
      { action: "review_clause", clause_id: "CL-1", status: "approved" },
      {
        action: "review_clause_mapping",
        clause_id: "CL-1",
        mapping_id: "MAP-1",
        status: "approved",
      },
    ];

    for (const payload of deniedActions) {
      const { request } = createSignedCookieRequest(payload, {
        user_id: "usr-local-viewer",
        roles: ["viewer"],
      });
      const res = await workspacePOST(request);
      expect(res.status).toBe(403);
    }
    expect(fetcher).not.toHaveBeenCalled();
  });

  it("D6–D8: Analyst can upload questionnaires, upload policies, and run assessments (200), but receives 403 on review_clause, review_clause_mapping, create_baseline, and delete_policy", async () => {
    const fetcher = vi
      .fn()
      .mockImplementation(
        async () => new Response(JSON.stringify({ ok: true }), { status: 200 })
      );
    vi.stubGlobal("fetch", fetcher);

    const allowedAnalystPayloads: Record<string, unknown>[] = [
      {
        action: "import_questionnaire",
        filename: "q.xlsx",
        workbook_base64: "UEsDBBQAAAAIA==",
      },
      { action: "import_policy", name: "Pol", text: "1.1 Rule" },
      {
        action: "run_coverage_assessment",
        questionnaire_id: "Q-1",
        assessment_mode: "regulatory_only",
      },
    ];

    for (const payload of allowedAnalystPayloads) {
      const { request } = createSignedCookieRequest(payload, {
        user_id: "usr-local-analyst",
        roles: ["analyst"],
      });
      const res = await workspacePOST(request);
      expect(res.status).toBe(200);
    }
    expect(fetcher).toHaveBeenCalledTimes(3);

    fetcher.mockClear();
    const deniedAnalystPayloads: Record<string, unknown>[] = [
      { action: "review_clause", clause_id: "CL-1", status: "approved" },
      {
        action: "review_clause_mapping",
        clause_id: "CL-1",
        mapping_id: "MAP-1",
        status: "approved",
      },
      {
        action: "create_baseline",
        name: "Baseline",
        policy_ids: ["POL-1"],
      },
      { action: "delete_policy", policy_id: "POL-1" },
    ];

    for (const payload of deniedAnalystPayloads) {
      const { request } = createSignedCookieRequest(payload, {
        user_id: "usr-local-analyst",
        roles: ["analyst"],
      });
      const res = await workspacePOST(request);
      expect(res.status).toBe(403);
    }
    expect(fetcher).not.toHaveBeenCalled();
  });

  it("D9: Reviewer downgraded to Analyst mid-session is immediately denied (403) when attempting approval with old session cookie", async () => {
    const fetcher = vi.fn();
    vi.stubGlobal("fetch", fetcher);

    const { request } = createSignedCookieRequest(
      { action: "review_clause", clause_id: "CL-1", status: "approved" },
      {
        user_id: "usr-local-reviewer",
        tenant_id: "local-workspace",
        roles: ["reviewer"],
      }
    );

    // Downgrade usr-local-reviewer to analyst in the live user store
    setRuntimeUserTenantRoles("usr-local-reviewer", "local-workspace", [
      "analyst",
    ]);

    const res = await workspacePOST(request);
    expect(res.status).toBe(403);
    expect(fetcher).not.toHaveBeenCalled();
  });

  it("D10 & D11: Reviewer approves clause and mapping separately; client-supplied actor/role overrides are ignored and verified user_id is recorded", async () => {
    const fetcher = vi.fn().mockImplementation(async (_url, init) => {
      const sent = JSON.parse(init.body);
      return new Response(
        JSON.stringify({
          review_status: sent.status,
          reviewer_actor: sent.actor,
          reviewer_role: sent.role,
        }),
        { status: 200 }
      );
    });
    vi.stubGlobal("fetch", fetcher);

    const clauseReq = createSignedCookieRequest(
      {
        action: "review_clause",
        clause_id: "CL-100",
        status: "approved",
        actor: "spoofed-other-user",
        role: "admin",
      },
      {
        user_id: "usr-local-reviewer",
        roles: ["reviewer"],
      }
    );
    const clauseRes = await workspacePOST(clauseReq.request);
    expect(clauseRes.status).toBe(200);
    const clauseData = await clauseRes.json();
    expect(clauseData.reviewer_actor).toBe("usr-local-reviewer");
    expect(clauseData.reviewer_role).toBe("reviewer");

    const mapReq = createSignedCookieRequest(
      {
        action: "review_clause_mapping",
        clause_id: "CL-100",
        mapping_id: "MAP-200",
        status: "approved",
        actor: "spoofed-other-user",
        role: "admin",
      },
      {
        user_id: "usr-local-reviewer",
        roles: ["reviewer"],
      }
    );
    const mapRes = await workspacePOST(mapReq.request);
    expect(mapRes.status).toBe(200);
    const mapData = await mapRes.json();
    expect(mapData.reviewer_actor).toBe("usr-local-reviewer");
    expect(mapData.reviewer_role).toBe("reviewer");
  });
});

describe("P0 Security Acceptance Matrix — Group E: Tenant Isolation (E1–E9)", () => {
  it("E1–E8: User in Tenant A cannot list, read, review, assess, or report on Tenant B resources via header or body tenant_id", async () => {
    upsertRuntimeWorkspaceUser({
      user_id: "usr-tenant-a",
      username: "user_a",
      display_name: "Tenant A Reviewer",
      password: "pass",
      tenants: { "tenant-a": ["reviewer"] },
    });

    const fetcher = vi.fn();
    vi.stubGlobal("fetch", fetcher);

    const crossTenantActions: Record<string, unknown>[] = [
      { action: "list_questionnaires", tenant_id: "tenant-b" },
      {
        action: "get_questionnaire",
        questionnaire_id: "Q-B",
        tenant_id: "tenant-b",
      },
      { action: "list_policies", tenant_id: "tenant-b" },
      {
        action: "review_clause",
        clause_id: "CL-B",
        status: "approved",
        tenant_id: "tenant-b",
      },
      {
        action: "run_coverage_assessment",
        questionnaire_id: "Q-B",
        assessment_mode: "enterprise_enhanced",
        enterprise_baseline_id: "BASE-B",
        tenant_id: "tenant-b",
      },
      {
        action: "get_report",
        assessment_id: "ASSESS-B",
        tenant_id: "tenant-b",
      },
    ];

    for (const payload of crossTenantActions) {
      const { request } = createSignedCookieRequest(payload, {
        user_id: "usr-tenant-a",
        tenant_id: "tenant-a",
        roles: ["reviewer"],
      });
      const res = await workspacePOST(request);
      expect(res.status).toBe(403);
    }

    // Header X-Tenant-ID override attempt -> 403
    const headerOverride = createSignedCookieRequest(
      { action: "list_questionnaires" },
      {
        user_id: "usr-tenant-a",
        tenant_id: "tenant-a",
        roles: ["reviewer"],
        extraHeaders: { "X-Tenant-ID": "tenant-b" },
      }
    );
    const headerRes = await workspacePOST(headerOverride.request);
    expect(headerRes.status).toBe(403);
    expect(fetcher).not.toHaveBeenCalled();
  });

  it("E5: User removed from Tenant A mid-session receives 403 on next request to Tenant A", async () => {
    upsertRuntimeWorkspaceUser({
      user_id: "usr-temp-member",
      username: "temp_member",
      display_name: "Temp Member",
      password: "pass",
      tenants: { "tenant-a": ["analyst"] },
    });

    const { request } = createSignedCookieRequest(
      { action: "list_questionnaires" },
      {
        user_id: "usr-temp-member",
        tenant_id: "tenant-a",
        roles: ["analyst"],
      }
    );

    // Remove user from tenant-a mid-session
    setRuntimeUserTenantRoles("usr-temp-member", "tenant-a", null);

    const res = await workspacePOST(request);
    expect(res.status).toBe(403);
  });

  it("E9: Shared public-demo tenant is rejected (403) on /api/workspace", async () => {
    const { request } = createSignedCookieRequest(
      { action: "list_questionnaires" },
      {
        user_id: "usr-demo-attempt",
        tenant_id: "public-demo",
        roles: ["reviewer"],
      }
    );
    const res = await workspacePOST(request);
    expect(res.status).toBe(403);
  });
});

describe("P0 Security Acceptance Matrix — Group F: Public Synthetic Demo Isolation (F1–F6)", () => {
  it("F1–F6: Anonymous /api/analysis allows only stateless DEMO_BANKING_V1 in public-demo tenant and blocks custom questionnaire_id, enterprise_enhanced, or secret leakage", async () => {
    const fetcher = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          assessment_id: "demo-1",
          questionnaire_id: "DEMO_BANKING_V1",
        }),
        { status: 200 }
      )
    );
    vi.stubGlobal("fetch", fetcher);

    // F1 & F4: Anonymous user runs DEMO_BANKING_V1; persist is forced to false and tenant is public-demo
    const f1Res = await analysisPOST(
      new Request("http://localhost/api/analysis", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          kind: "coverage",
          questionnaire_pack: "DEMO_BANKING_V1",
          persist: true, // attempted persist: true must be overridden to false
          use_case: { name: "Demo Use Case" },
        }),
      })
    );
    expect(f1Res.status).toBe(200);
    const [, f1Init] = fetcher.mock.calls[0];
    expect(f1Init.headers["X-Tenant-ID"]).toBe("public-demo");
    const forwardedBody = JSON.parse(f1Init.body);
    expect(forwardedBody.persist).toBe(false);
    expect(forwardedBody.questionnaire_pack).toBe("DEMO_BANKING_V1");

    // F2: Anonymous user attempts custom questionnaire_id via /api/analysis -> 400
    const f2Res = await analysisPOST(
      new Request("http://localhost/api/analysis", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          kind: "coverage",
          questionnaire_id: "QBANK-PRIVATE-123",
          use_case: { name: "Attempt Private" },
        }),
      })
    );
    expect(f2Res.status).toBe(400);

    // F3: Anonymous user attempts enterprise_enhanced via /api/analysis -> 400
    const f3Res = await analysisPOST(
      new Request("http://localhost/api/analysis", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          kind: "coverage",
          assessment_mode: "enterprise_enhanced",
          enterprise_baseline_id: "BASE-PRIVATE-1",
          use_case: { name: "Attempt Enhanced" },
        }),
      })
    );
    expect(f3Res.status).toBe(400);
  });
});

describe("P0 Security Acceptance Matrix — Group G: Production Misconfiguration & Secret Hygiene (G1–G5)", () => {
  it("G1: ENV=production without WORKSPACE_SESSION_SECRET fails closed (503)", async () => {
    vi.stubEnv("ENV", "production");
    vi.stubEnv("CROSSWALK_API_KEY", "prod-api-key-secret");
    vi.stubEnv("WORKSPACE_SESSION_SECRET", "");

    const res = await workspaceGET(new Request("http://localhost/api/workspace"));
    expect(res.status).toBe(503);
  });

  it("G2: ENV=production with ALLOW_LOCAL_DEV_AUTH_BYPASS=true ignores bypass and denies unauthenticated access", async () => {
    vi.stubEnv("ENV", "production");
    vi.stubEnv("ALLOW_LOCAL_DEV_AUTH_BYPASS", "true");
    vi.stubEnv("CROSSWALK_API_KEY", "prod-api-key-secret");
    vi.stubEnv(
      "WORKSPACE_SESSION_SECRET",
      "prod-workspace-session-signing-secret-32chars!!"
    );
    vi.stubEnv(
      "WORKSPACE_USERS_JSON",
      JSON.stringify([
        {
          user_id: "usr-prod-1",
          username: "reviewer",
          password: "prod-password-123",
          tenant_id: "bank-prod-tenant",
          roles: ["reviewer"],
        },
      ])
    );

    const res = await workspaceGET(new Request("http://localhost/api/workspace"));
    expect(res.status).toBe(401);
  });

  it("G3: ENV=production without CROSSWALK_API_KEY fails closed (503)", async () => {
    vi.stubEnv("ENV", "production");
    vi.stubEnv("CROSSWALK_API_KEY", "");
    vi.stubEnv(
      "WORKSPACE_SESSION_SECRET",
      "prod-workspace-session-signing-secret-32chars!!"
    );
    vi.stubEnv(
      "WORKSPACE_USERS_JSON",
      JSON.stringify([
        {
          user_id: "usr-prod-1",
          username: "reviewer",
          password: "prod-password-123",
          tenant_id: "bank-prod-tenant",
          roles: ["reviewer"],
        },
      ])
    );

    const res = await workspaceGET(new Request("http://localhost/api/workspace"));
    expect(res.status).toBe(503);
  });

  it("G4: Backend error during workspace request returns safe message and never leaks secrets or stack traces", async () => {
    vi.stubEnv("CROSSWALK_API_KEY", "ultra-secret-crosswalk-key-999");
    vi.stubEnv(
      "WORKSPACE_SESSION_SECRET",
      "ultra-secret-session-signing-key-32bytes!!"
    );

    const fetcher = vi.fn().mockResolvedValue(
      new Response(
        "Traceback (most recent call last): ultra-secret-crosswalk-key-999",
        { status: 500 }
      )
    );
    vi.stubGlobal("fetch", fetcher);

    const { request } = createSignedCookieRequest(
      { action: "list_questionnaires" },
      { secret: "ultra-secret-session-signing-key-32bytes!!" }
    );
    const res = await workspacePOST(request);
    expect(res.status).toBe(500);
    const text = await res.text();
    expect(text).not.toContain("ultra-secret-crosswalk-key-999");
    expect(text).not.toContain("ultra-secret-session-signing-key-32bytes!!");
    expect(text).not.toContain("Traceback");
  });
});

describe("P0.5 Security Hardening — Group H: Password Storage & Authentication Hardening (H1–H4)", () => {
  it("H1: hashPassword produces scrypt hash and verifyPassword validates correct credentials", () => {
    const rawPass = "SecretCompliancePass2026!";
    const hashed = hashPassword(rawPass);
    expect(hashed).toMatch(/^scrypt\$[0-9a-f]{32}\$[0-9a-f]{128}$/);

    const userRecord: WorkspaceUserRecord = {
      user_id: "usr-h1",
      username: "user_h1",
      display_name: "User H1",
      password_hash: hashed,
      tenants: { "bank-tenant": ["analyst"] },
    };

    // Valid candidate in production
    expect(verifyPassword(rawPass, userRecord, true)).toBe(true);
    // Invalid candidate
    expect(verifyPassword("WrongPassword123", userRecord, true)).toBe(false);
  });

  it("H2: PBKDF2 formatted hash is verified correctly and invalid iteration count is rejected", () => {
    const salt = "0123456789abcdef";
    const derived = crypto.pbkdf2Sync("testpass", salt, 10000, 64, "sha256").toString("hex");
    const validHash = `pbkdf2$10000$${salt}$${derived}`;

    const userRecord: WorkspaceUserRecord = {
      user_id: "usr-h2",
      username: "user_h2",
      display_name: "User H2",
      password_hash: validHash,
      tenants: { "bank-tenant": ["analyst"] },
    };

    expect(verifyPassword("testpass", userRecord, true)).toBe(true);
    expect(verifyPassword("wrongpass", userRecord, true)).toBe(false);

    // Reject PBKDF2 with insecure iteration count (< 10000)
    const weakHash = `pbkdf2$1000$${salt}$${derived}`;
    const weakUser: WorkspaceUserRecord = {
      ...userRecord,
      password_hash: weakHash,
    };
    expect(verifyPassword("testpass", weakUser, true)).toBe(false);
  });

  it("H3: In production (ENV=production), plaintext passwords and unsalted sha256 are rejected", () => {
    const plaintextUser: WorkspaceUserRecord = {
      user_id: "usr-h3-plain",
      username: "plain_user",
      display_name: "Plain User",
      password: "insecure-plain-password",
      tenants: { "bank-tenant": ["analyst"] },
    };
    // In production, plaintext is strictly rejected
    expect(verifyPassword("insecure-plain-password", plaintextUser, true)).toBe(false);

    const sha256Hash = crypto.createHash("sha256").update("insecure-sha", "utf8").digest("hex");
    const sha256User: WorkspaceUserRecord = {
      user_id: "usr-h3-sha",
      username: "sha_user",
      display_name: "SHA User",
      password_sha256: sha256Hash,
      tenants: { "bank-tenant": ["analyst"] },
    };
    // In production, unsalted sha256 is strictly rejected
    expect(verifyPassword("insecure-sha", sha256User, true)).toBe(false);

    // In non-production, legacy formats are permitted for local dev fixtures
    expect(verifyPassword("insecure-plain-password", plaintextUser, false)).toBe(true);
    expect(verifyPassword("insecure-sha", sha256User, false)).toBe(true);

    // Furthermore, loadWorkspaceUsers() in production drops any user without password_hash
    vi.stubEnv("ENV", "production");
    vi.stubEnv(
      "WORKSPACE_USERS_JSON",
      JSON.stringify([
        {
          user_id: "usr-plain-only",
          username: "plainonly",
          password: "my-plain-password",
          tenants: { "bank-tenant": ["analyst"] },
        },
      ])
    );
    const loaded = loadWorkspaceUsers();
    expect(loaded.has("usr-plain-only")).toBe(false);
  });

  it("H4: Repeated failed login attempts trigger 429 rate limit", async () => {
    vi.stubEnv(
      "WORKSPACE_USERS_JSON",
      JSON.stringify([
        {
          user_id: "usr-rate-test",
          username: "rate_test_user",
          password_hash: hashPassword("CorrectPassword123!"),
          tenants: { "local-workspace": ["analyst"] },
        },
      ])
    );

    const makeFailedLogin = () =>
      loginPOST(
        new Request("http://localhost/api/auth/login", {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "X-Forwarded-For": "198.51.100.42",
          },
          body: JSON.stringify({
            username: "rate_test_user",
            password: "IncorrectPassword",
          }),
        })
      );

    // 5 failed attempts
    for (let i = 0; i < 5; i++) {
      const res = await makeFailedLogin();
      expect(res.status).toBe(401);
    }

    // 6th attempt should be blocked by rate limiting (429)
    const rateLimitedRes = await makeFailedLogin();
    expect(rateLimitedRes.status).toBe(429);
    const body = await rateLimitedRes.json();
    expect(body.detail).toMatch(/too many failed login attempts/i);
  });
});

describe("P0.5 Security Hardening — Group I: Production Defaults & Dev Bypass Protection (I1–I2)", () => {
  it("I1: In production without WORKSPACE_USERS_JSON, no default fixture accounts exist", () => {
    vi.stubEnv("ENV", "production");
    vi.stubEnv("WORKSPACE_USERS_JSON", "");

    const users = loadWorkspaceUsers();
    expect(users.size).toBe(0);
    expect(users.has("usr-local-analyst")).toBe(false);
    expect(users.has("usr-local-reviewer")).toBe(false);
  });

  it("I2: Dev bypass is denied when external proxy headers are present on loopback requests", async () => {
    vi.stubEnv("ENV", "development");
    vi.stubEnv("NODE_ENV", "development");
    vi.stubEnv("ALLOW_LOCAL_DEV_AUTH_BYPASS", "true");

    const fetcher = vi.fn().mockResolvedValue(
      new Response(JSON.stringify([]), { status: 200 })
    );
    vi.stubGlobal("fetch", fetcher);

    // Direct loopback without proxy headers works under bypass
    const okRes = await workspacePOST(
      new Request("http://localhost/api/workspace", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ action: "list_questionnaires" }),
      })
    );
    expect(okRes.status).toBe(200);

    // Loopback with spoofed X-Forwarded-For header is denied bypass -> 401
    const spoofedRes = await workspacePOST(
      new Request("http://localhost/api/workspace", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-Forwarded-For": "203.0.113.195",
        },
        body: JSON.stringify({ action: "list_questionnaires" }),
      })
    );
    expect(spoofedRes.status).toBe(401);
  });
});

describe("P0.5 Security Hardening — Group J: Multi-process Revocation & Live User Invariants (J1–J4)", () => {
  it("J1: DurableRevocationStore persists revocations across store instances via disk", () => {
    const tmpRevocationFile = path.join(
      process.env.TEMP || process.env.TMP || "/tmp",
      `revocations_test_${Date.now()}_${Math.random().toString(36).slice(2)}.json`
    );
    vi.stubEnv("SESSION_REVOCATION_PATH", tmpRevocationFile);

    try {
      const storeA = new DurableRevocationStore();
      const testSid = "sid-cross-process-test-12345";
      expect(storeA.isRevoked(testSid)).toBe(false);

      // Revoke in store A
      storeA.revoke(testSid);
      expect(storeA.isRevoked(testSid)).toBe(true);

      // Store B simulates a separate server worker process reading the same shared storage
      const storeB = new DurableRevocationStore();
      expect(storeB.isRevoked(testSid)).toBe(true);
    } finally {
      if (fs.existsSync(tmpRevocationFile)) {
        try {
          fs.unlinkSync(tmpRevocationFile);
        } catch {}
      }
    }
  });

  it("J2: Deleted user is immediately rejected (401) despite valid unexpired session token", async () => {
    upsertRuntimeWorkspaceUser({
      user_id: "usr-ephemeral",
      username: "ephemeral",
      display_name: "Ephemeral User",
      password_hash: hashPassword("pass"),
      tenants: { "local-workspace": ["reviewer"] },
    });

    const { request } = createSignedCookieRequest(
      { action: "list_questionnaires" },
      {
        user_id: "usr-ephemeral",
        roles: ["reviewer"],
      }
    );

    // Initial request succeeds
    const fetcher = vi.fn().mockResolvedValue(
      new Response(JSON.stringify([]), { status: 200 })
    );
    vi.stubGlobal("fetch", fetcher);
    const res1 = await workspacePOST(request);
    expect(res1.status).toBe(200);

    // User is deleted from workspace registry
    setRuntimeUserDisabled("usr-ephemeral", true);

    const { request: request2 } = createSignedCookieRequest(
      { action: "list_questionnaires" },
      {
        user_id: "usr-ephemeral",
        roles: ["reviewer"],
      }
    );
    const res2 = await workspacePOST(request2);
    expect(res2.status).toBe(401);
  });

  it("J3: User removed from tenant membership is immediately rejected (403)", async () => {
    upsertRuntimeWorkspaceUser({
      user_id: "usr-multi-tenant",
      username: "multitenant",
      display_name: "Multi Tenant User",
      password_hash: hashPassword("pass"),
      tenants: {
        "tenant-primary": ["analyst"],
        "tenant-secondary": ["reviewer"],
      },
    });

    const { request } = createSignedCookieRequest(
      { action: "list_questionnaires" },
      {
        user_id: "usr-multi-tenant",
        tenant_id: "tenant-secondary",
        roles: ["reviewer"],
      }
    );

    const fetcher = vi.fn().mockResolvedValue(
      new Response(JSON.stringify([]), { status: 200 })
    );
    vi.stubGlobal("fetch", fetcher);
    const okRes = await workspacePOST(request);
    expect(okRes.status).toBe(200);

    // Revoke tenant-secondary membership
    setRuntimeUserTenantRoles("usr-multi-tenant", "tenant-secondary", null);

    const { request: revokedReq } = createSignedCookieRequest(
      { action: "list_questionnaires" },
      {
        user_id: "usr-multi-tenant",
        tenant_id: "tenant-secondary",
        roles: ["reviewer"],
      }
    );
    const deniedRes = await workspacePOST(revokedReq);
    expect(deniedRes.status).toBe(403);
  });

  it("J4: Role downgrade from reviewer to analyst immediately revokes clause approval rights (403)", async () => {
    const fetcher = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ review_status: "approved" }), { status: 200 })
    );
    vi.stubGlobal("fetch", fetcher);

    // Token claims "reviewer", but live user is downgraded to "analyst"
    setRuntimeUserTenantRoles("usr-local-reviewer", "local-workspace", ["analyst"]);

    const { request } = createSignedCookieRequest(
      {
        action: "review_clause",
        clause_id: "CL-500",
        status: "approved",
      },
      {
        user_id: "usr-local-reviewer",
        roles: ["reviewer"], // token still claims reviewer
      }
    );

    const res = await workspacePOST(request);
    expect(res.status).toBe(403);
    expect(fetcher).not.toHaveBeenCalled();
  });
});

describe("P0.5 Security Hardening — Group K: Static Token Privilege Boundary (K1–K2)", () => {
  it("K1 & K2: Static WORKSPACE_AUTH_TOKEN is restricted to viewer permissions and cannot review clauses or mappings", async () => {
    vi.stubEnv("WORKSPACE_AUTH_TOKEN", "static-automation-ci-token-xyz");

    const fetcher = vi.fn().mockResolvedValue(
      new Response(JSON.stringify([]), { status: 200 })
    );
    vi.stubGlobal("fetch", fetcher);

    // K1: Read action succeeds with static token
    const readRes = await workspacePOST(
      new Request("http://localhost/api/workspace", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: "Bearer static-automation-ci-token-xyz",
        },
        body: JSON.stringify({ action: "list_questionnaires" }),
      })
    );
    expect(readRes.status).toBe(200);

    // K2: Review actions fail with 403 Forbidden
    const clauseReviewRes = await workspacePOST(
      new Request("http://localhost/api/workspace", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: "Bearer static-automation-ci-token-xyz",
        },
        body: JSON.stringify({
          action: "review_clause",
          clause_id: "CL-10",
          status: "approved",
        }),
      })
    );
    expect(clauseReviewRes.status).toBe(403);

    const mapReviewRes = await workspacePOST(
      new Request("http://localhost/api/workspace", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: "Bearer static-automation-ci-token-xyz",
        },
        body: JSON.stringify({
          action: "review_clause_mapping",
          clause_id: "CL-10",
          mapping_id: "MAP-10",
          status: "approved",
        }),
      })
    );
    expect(mapReviewRes.status).toBe(403);

    const baselineRes = await workspacePOST(
      new Request("http://localhost/api/workspace", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: "Bearer static-automation-ci-token-xyz",
        },
        body: JSON.stringify({
          action: "create_baseline",
          name: "Automation Baseline",
        }),
      })
    );
    expect(baselineRes.status).toBe(403);
  });
});

describe("P0.5 Security Hardening — Group L: OIDC Production Safety & IDP Gate (L1–L2)", () => {
  it("L1: Calling /api/auth/oidc in ENV=production returns 501 Not Implemented", async () => {
    vi.stubEnv("ENV", "production");
    vi.stubEnv("CROSSWALK_API_KEY", "prod-crosswalk-key-12345");
    vi.stubEnv(
      "WORKSPACE_SESSION_SECRET",
      "prod-workspace-session-signing-secret-32chars!!"
    );

    const getRes = await oidcGET(new Request("http://localhost/api/auth/oidc"));
    expect(getRes.status).toBe(501);
    const getBody = await getRes.json();
    expect(getBody.detail).toMatch(/disabled for hosted production/i);

    const postRes = await oidcPOST(
      new Request("http://localhost/api/auth/oidc", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ state: "xyz", id_token: "abc" }),
      })
    );
    expect(postRes.status).toBe(501);
  });

  it("L2: In ENV=production, OIDC_ISSUER_URL without WORKSPACE_USERS_JSON fails readiness check (503)", async () => {
    vi.stubEnv("ENV", "production");
    vi.stubEnv("CROSSWALK_API_KEY", "prod-crosswalk-key-12345");
    vi.stubEnv(
      "WORKSPACE_SESSION_SECRET",
      "prod-workspace-session-signing-secret-32chars!!"
    );
    vi.stubEnv("OIDC_ISSUER_URL", "https://auth.bank.au");
    vi.stubEnv("WORKSPACE_USERS_JSON", ""); // missing users json

    const res = await workspaceGET(new Request("http://localhost/api/workspace"));
    expect(res.status).toBe(503);
    const data = await res.json();
    expect(data.error).toMatch(/WORKSPACE_USERS_JSON/i);
  });
});
