import { afterEach, describe, expect, it, vi } from "vitest";
import { GET, POST } from "../app/api/workspace/route";
import {
  clearSecurityStateForTests,
  createSessionToken,
  formatSessionCookie,
} from "../app/security";

afterEach(() => {
  clearSecurityStateForTests();
  vi.unstubAllGlobals();
  vi.unstubAllEnvs();
});

function buildAuthenticatedHeaders(params?: {
  user_id?: string;
  tenant_id?: string;
  roles?: ("viewer" | "analyst" | "reviewer" | "admin")[];
}): Record<string, string> {
  const { token, claims } = createSessionToken({
    user_id: params?.user_id || "usr-local-reviewer",
    tenant_id: params?.tenant_id || "local-workspace",
    roles: params?.roles || ["reviewer"],
  });
  return {
    Cookie: formatSessionCookie(token).split(";")[0],
    "X-CSRF-Token": claims.csrf,
  };
}

describe("private document-first workspace gateway (/api/workspace)", () => {
  it("rejects unauthenticated GET / POST requests by default when local dev bypass is not enabled", async () => {
    const getRes = await GET(new Request("http://localhost/api/workspace"));
    expect(getRes.status).toBe(401);

    const postRes = await POST(
      new Request("http://localhost/api/workspace", {
        method: "POST",
        body: JSON.stringify({ action: "list_questionnaires" }),
      })
    );
    expect(postRes.status).toBe(401);
  });

  it("exposes local_private_single_tenant status when ALLOW_LOCAL_DEV_AUTH_BYPASS=true on loopback", async () => {
    vi.stubEnv("ALLOW_LOCAL_DEV_AUTH_BYPASS", "true");
    const res = await GET(new Request("http://localhost/api/workspace"));
    expect(res.status).toBe(200);
    const body = await res.json();
    expect(body.workspace_mode).toBe("local_private_single_tenant");
    expect(body.deployment_mode).toBe("local_dev_bypass");
    expect(body.tenant_scope).toBe("local-workspace");
    expect(body.public_demo_isolated).toBe(true);
    expect(body.supported_targets.questionnaire.status).toBe("available");
    expect(body.supported_targets.strategy.status).toBe("planned_unavailable");
  });

  it("rejects the shared public-demo tenant from accessing private workspace endpoints", async () => {
    vi.stubEnv("BANKING_CROSSWALK_TENANT_ID", "public-demo");
    const res = await POST(
      new Request("http://localhost/api/workspace", {
        method: "POST",
        headers: buildAuthenticatedHeaders(),
        body: JSON.stringify({ action: "list_questionnaires" }),
      })
    );
    expect(res.status).toBe(403);
    const body = await res.json();
    expect(body.error).toMatch(/public-demo/i);
  });

  it("fails closed in production when authentication or API key is missing", async () => {
    vi.stubEnv("ENV", "production");
    vi.stubEnv("BANKING_CROSSWALK_TENANT_ID", "");
    vi.stubEnv("CROSSWALK_API_KEY", "");
    const res = await POST(
      new Request("http://localhost/api/workspace", {
        method: "POST",
        body: JSON.stringify({ action: "list_policies" }),
      })
    );
    expect(res.status).toBe(503);
  });

  it("enforces WORKSPACE_AUTH_TOKEN when configured using constant-time comparison", async () => {
    vi.stubEnv("WORKSPACE_AUTH_TOKEN", "secret-workspace-session-token");

    const unauth = await POST(
      new Request("http://localhost/api/workspace", {
        method: "POST",
        body: JSON.stringify({ action: "list_questionnaires" }),
      })
    );
    expect(unauth.status).toBe(401);

    const wrongToken = await POST(
      new Request("http://localhost/api/workspace", {
        method: "POST",
        headers: { "X-Workspace-Token": "wrong-token" },
        body: JSON.stringify({ action: "list_questionnaires" }),
      })
    );
    expect(wrongToken.status).toBe(401);

    const fetcher = vi
      .fn()
      .mockResolvedValue(new Response(JSON.stringify([]), { status: 200 }));
    vi.stubGlobal("fetch", fetcher);

    const validToken = await POST(
      new Request("http://localhost/api/workspace", {
        method: "POST",
        headers: {
          Authorization: "Bearer secret-workspace-session-token",
        },
        body: JSON.stringify({ action: "list_questionnaires" }),
      })
    );
    expect(validToken.status).toBe(200);
    expect(fetcher).toHaveBeenCalledTimes(1);
  });

  it("rejects cross-tenant headers/body and overrides client-supplied actor/role with verified session identity", async () => {
    const fetcher = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          clause_id: "CL-1",
          review_status: "approved",
        }),
        { status: 200 }
      )
    );
    vi.stubGlobal("fetch", fetcher);
    vi.stubEnv("BANKING_CROSSWALK_TENANT_ID", "bank-anz-private");
    vi.stubEnv("CROSSWALK_API_KEY", "server-secret-api-key");

    const authHeaders = buildAuthenticatedHeaders({
      user_id: "usr-local-reviewer",
      tenant_id: "bank-anz-private",
      roles: ["reviewer"],
    });

    // Cross-tenant header attempt MUST be rejected with 403
    const crossTenantAttempt = await POST(
      new Request("http://localhost/api/workspace", {
        method: "POST",
        headers: {
          ...authHeaders,
          "X-Tenant-ID": "forged-other-bank",
        },
        body: JSON.stringify({
          action: "review_clause",
          clause_id: "CL-1",
          status: "approved",
        }),
      })
    );
    expect(crossTenantAttempt.status).toBe(403);

    // Valid tenant with spoofed body actor/role -> overwrites with verified user_id and role
    const res = await POST(
      new Request("http://localhost/api/workspace", {
        method: "POST",
        headers: {
          ...authHeaders,
          "X-API-Key": "forged-key",
        },
        body: JSON.stringify({
          action: "review_clause",
          clause_id: "CL-1",
          status: "approved",
          actor: "spoofed-actor",
          role: "admin",
        }),
      })
    );
    expect(res.status).toBe(200);
    expect(fetcher).toHaveBeenCalledTimes(1);
    const [url, init] = fetcher.mock.calls[0];
    expect(url).toContain("/v1/enterprise/clauses/CL-1/review");
    expect(init.headers["X-Tenant-ID"]).toBe("bank-anz-private");
    expect(init.headers["X-API-Key"]).toBe("server-secret-api-key");
    expect(init.headers["X-Actor"]).toBe("usr-local-reviewer");
    expect(init.headers["X-Role"]).toBe("reviewer");
    const forwardedBody = JSON.parse(init.body);
    expect(forwardedBody.actor).toBe("usr-local-reviewer");
    expect(forwardedBody.role).toBe("reviewer");
    expect(await res.text()).not.toContain("server-secret-api-key");
  });

  it("routes control mapping approval separately from clause approval (P1-S0 invariant)", async () => {
    const fetcher = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          mapping_id: "MAP-1",
          review_status: "approved",
        }),
        { status: 200 }
      )
    );
    vi.stubGlobal("fetch", fetcher);
    const res = await POST(
      new Request("http://localhost/api/workspace", {
        method: "POST",
        headers: buildAuthenticatedHeaders(),
        body: JSON.stringify({
          action: "review_clause_mapping",
          clause_id: "CL-1",
          mapping_id: "MAP-1",
          status: "approved",
        }),
      })
    );
    expect(res.status).toBe(200);
    const [url, init] = fetcher.mock.calls[0];
    expect(url).toContain(
      "/v1/enterprise/clauses/CL-1/mappings/MAP-1/review"
    );
    expect(init.method).toBe("PUT");
  });

  it("blocks DEMO_BANKING_V1 and strategy targets in customer coverage assessments", async () => {
    const fetcher = vi.fn();
    vi.stubGlobal("fetch", fetcher);
    const headers = buildAuthenticatedHeaders();

    const demoAttempt = await POST(
      new Request("http://localhost/api/workspace", {
        method: "POST",
        headers,
        body: JSON.stringify({
          action: "assess_coverage",
          questionnaire_id: "DEMO_BANKING_V1",
          assessment_mode: "regulatory_only",
        }),
      })
    );
    expect(demoAttempt.status).toBe(400);

    const packAttempt = await POST(
      new Request("http://localhost/api/workspace", {
        method: "POST",
        headers,
        body: JSON.stringify({
          action: "assess_coverage",
          questionnaire_id: "QBANK-REAL123",
          questionnaire_pack: "DEMO_BANKING_V1",
          assessment_mode: "regulatory_only",
        }),
      })
    );
    expect(packAttempt.status).toBe(400);

    const strategyAttempt = await POST(
      new Request("http://localhost/api/workspace", {
        method: "POST",
        headers,
        body: JSON.stringify({
          action: "assess_coverage",
          questionnaire_id: "QBANK-REAL123",
          assessment_target_type: "strategy",
          assessment_mode: "regulatory_only",
        }),
      })
    );
    expect(strategyAttempt.status).toBe(501);
    expect(fetcher).not.toHaveBeenCalled();
  });

  it("enforces 1 MB payload limit on non-upload workspace actions", async () => {
    const fetcher = vi.fn();
    vi.stubGlobal("fetch", fetcher);
    const res = await POST(
      new Request("http://localhost/api/workspace", {
        method: "POST",
        headers: buildAuthenticatedHeaders(),
        body: JSON.stringify({
          action: "list_questionnaires",
          padding: "x".repeat(1_000_050),
        }),
      })
    );
    expect(res.status).toBe(413);
    expect(fetcher).not.toHaveBeenCalled();
  });
});
