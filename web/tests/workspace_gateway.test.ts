import { afterEach, describe, expect, it, vi } from "vitest";
import { GET, POST } from "../app/api/workspace/route";

afterEach(() => {
  vi.unstubAllGlobals();
  vi.unstubAllEnvs();
});

describe("private document-first workspace gateway (/api/workspace)", () => {
  it("exposes local_private_single_tenant status and marks strategy assessment as planned_unavailable", async () => {
    const res = await GET(new Request("http://localhost/api/workspace"));
    expect(res.status).toBe(200);
    const body = await res.json();
    expect(body.workspace_mode).toBe("local_private_single_tenant");
    expect(body.tenant_scope).toBe("local-private-workspace");
    expect(body.public_demo_isolated).toBe(true);
    expect(body.supported_targets.questionnaire.status).toBe("available");
    expect(body.supported_targets.strategy.status).toBe("planned_unavailable");
  });

  it("rejects the shared public-demo tenant from accessing private workspace endpoints", async () => {
    vi.stubEnv("BANKING_CROSSWALK_TENANT_ID", "public-demo");
    const res = await POST(
      new Request("http://localhost/api/workspace", {
        method: "POST",
        body: JSON.stringify({ action: "list_questionnaires" }),
      }),
    );
    expect(res.status).toBe(403);
    const body = await res.json();
    expect(body.error).toMatch(/public-demo/i);
  });

  it("fails closed in production when server-bound tenant or API key is missing", async () => {
    vi.stubEnv("ENV", "production");
    vi.stubEnv("BANKING_CROSSWALK_TENANT_ID", "");
    vi.stubEnv("CROSSWALK_API_KEY", "");
    const res = await POST(
      new Request("http://localhost/api/workspace", {
        method: "POST",
        body: JSON.stringify({ action: "list_policies" }),
      }),
    );
    expect(res.status).toBe(403);
  });

  it("enforces WORKSPACE_AUTH_TOKEN when configured using constant-time comparison", async () => {
    vi.stubEnv("WORKSPACE_AUTH_TOKEN", "secret-workspace-session-token");

    const unauth = await POST(
      new Request("http://localhost/api/workspace", {
        method: "POST",
        body: JSON.stringify({ action: "list_questionnaires" }),
      }),
    );
    expect(unauth.status).toBe(401);

    const wrongToken = await POST(
      new Request("http://localhost/api/workspace", {
        method: "POST",
        headers: { "X-Workspace-Token": "wrong-token" },
        body: JSON.stringify({ action: "list_questionnaires" }),
      }),
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
      }),
    );
    expect(validToken.status).toBe(200);
    expect(fetcher).toHaveBeenCalledTimes(1);
  });

  it("ignores browser-supplied tenant IDs, API keys, and reviewer identities and injects server-bound context", async () => {
    const fetcher = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          clause_id: "CL-1",
          review_status: "approved",
        }),
        { status: 200 },
      ),
    );
    vi.stubGlobal("fetch", fetcher);
    vi.stubEnv("BANKING_CROSSWALK_TENANT_ID", "bank-anz-private");
    vi.stubEnv("CROSSWALK_API_KEY", "server-secret-api-key");
    vi.stubEnv("BANKING_CROSSWALK_ACTOR", "jane.reviewer@bank.example");
    vi.stubEnv("BANKING_CROSSWALK_ROLE", "compliance");

    const res = await POST(
      new Request("http://localhost/api/workspace", {
        method: "POST",
        headers: {
          "X-Tenant-ID": "forged-other-bank",
          "X-API-Key": "forged-key",
        },
        body: JSON.stringify({
          action: "review_clause",
          clause_id: "CL-1",
          status: "approved",
          tenant_id: "forged-other-bank",
          actor: "spoofed-actor",
          role: "admin",
        }),
      }),
    );
    expect(res.status).toBe(200);
    expect(fetcher).toHaveBeenCalledTimes(1);
    const [url, init] = fetcher.mock.calls[0];
    expect(url).toContain("/v1/enterprise/clauses/CL-1/review");
    expect(init.headers["X-Tenant-ID"]).toBe("bank-anz-private");
    expect(init.headers["X-API-Key"]).toBe("server-secret-api-key");
    expect(init.headers["X-Actor"]).toBe("jane.reviewer@bank.example");
    expect(init.headers["X-Role"]).toBe("compliance");
    const forwardedBody = JSON.parse(init.body);
    expect(forwardedBody.actor).toBe("jane.reviewer@bank.example");
    expect(forwardedBody.role).toBe("compliance");
    expect(await res.text()).not.toContain("server-secret-api-key");
  });

  it("routes control mapping approval separately from clause approval (P1-S0 invariant)", async () => {
    const fetcher = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          mapping_id: "MAP-1",
          review_status: "approved",
        }),
        { status: 200 },
      ),
    );
    vi.stubGlobal("fetch", fetcher);
    const res = await POST(
      new Request("http://localhost/api/workspace", {
        method: "POST",
        body: JSON.stringify({
          action: "review_clause_mapping",
          clause_id: "CL-1",
          mapping_id: "MAP-1",
          status: "approved",
        }),
      }),
    );
    expect(res.status).toBe(200);
    const [url, init] = fetcher.mock.calls[0];
    expect(url).toContain(
      "/v1/enterprise/clauses/CL-1/mappings/MAP-1/review",
    );
    expect(init.method).toBe("PUT");
  });

  it("blocks DEMO_BANKING_V1 and strategy targets in customer coverage assessments", async () => {
    const fetcher = vi.fn();
    vi.stubGlobal("fetch", fetcher);

    const demoAttempt = await POST(
      new Request("http://localhost/api/workspace", {
        method: "POST",
        body: JSON.stringify({
          action: "assess_coverage",
          questionnaire_id: "DEMO_BANKING_V1",
          assessment_mode: "regulatory_only",
        }),
      }),
    );
    expect(demoAttempt.status).toBe(400);

    const packAttempt = await POST(
      new Request("http://localhost/api/workspace", {
        method: "POST",
        body: JSON.stringify({
          action: "assess_coverage",
          questionnaire_id: "QBANK-REAL123",
          questionnaire_pack: "DEMO_BANKING_V1",
          assessment_mode: "regulatory_only",
        }),
      }),
    );
    expect(packAttempt.status).toBe(400);

    const strategyAttempt = await POST(
      new Request("http://localhost/api/workspace", {
        method: "POST",
        body: JSON.stringify({
          action: "assess_coverage",
          questionnaire_id: "QBANK-REAL123",
          assessment_target_type: "strategy",
          assessment_mode: "regulatory_only",
        }),
      }),
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
        body: JSON.stringify({
          action: "list_questionnaires",
          padding: "x".repeat(1_000_050),
        }),
      }),
    );
    expect(res.status).toBe(413);
    expect(fetcher).not.toHaveBeenCalled();
  });
});
