import { afterEach, describe, expect, it, vi } from "vitest";
import { POST } from "../app/api/analysis/route";

afterEach(() => {
  vi.unstubAllGlobals();
  vi.unstubAllEnvs();
});

describe("public analysis gateway", () => {
  it("strips caller persistence and tenant references before forwarding", async () => {
    const fetcher = vi
      .fn()
      .mockResolvedValue(
        new Response(JSON.stringify({ assessment_id: "test-id" }), {
          status: 201,
        }),
      );
    vi.stubGlobal("fetch", fetcher);
    vi.stubEnv("CROSSWALK_API_KEY", "server-only-test-key");
    const response = await POST(
      new Request("http://localhost/api/analysis", {
        method: "POST",
        body: JSON.stringify({
          kind: "coverage",
          use_case: { apra_regulated: true },
          persist: true,
          use_case_id: "another-bank",
          routing_snapshot_id: "forged",
          tenant: "forged",
        }),
      }),
    );
    expect(response.status).toBe(200);
    const forwarded = JSON.parse(fetcher.mock.calls[0][1].body);
    expect(forwarded).toEqual({
      use_case: { apra_regulated: true },
      questionnaire_pack: "DEMO_BANKING_V1",
      persist: false,
    });
    expect(await response.text()).not.toContain("server-only-test-key");
  });
  it("returns authentication failures without generating sample results", async () => {
    vi.stubGlobal(
      "fetch",
      vi
        .fn()
        .mockResolvedValue(
          new Response("secret-backend-diagnostic", { status: 401 }),
        ),
    );
    const response = await POST(
      new Request("http://localhost/api/analysis", {
        method: "POST",
        body: JSON.stringify({ kind: "coverage", use_case: {} }),
      }),
    );
    expect(response.status).toBe(401);
    expect(await response.text()).not.toContain("secret-backend-diagnostic");
  });
  it("rejects a malformed request without contacting the API", async () => {
    const fetcher = vi.fn();
    vi.stubGlobal("fetch", fetcher);
    const response = await POST(
      new Request("http://localhost/api/analysis", {
        method: "POST",
        body: "{invalid",
      }),
    );
    expect(response.status).toBe(400);
    expect(fetcher).not.toHaveBeenCalled();
  });
  it("bounds actual public request bytes before parsing", async () => {
    const fetcher = vi.fn();
    vi.stubGlobal("fetch", fetcher);
    const response = await POST(
      new Request("http://localhost/api/analysis", {
        method: "POST",
        body: "x".repeat(1_000_001),
      }),
    );
    expect(response.status).toBe(413);
    expect(fetcher).not.toHaveBeenCalled();
  });
});
