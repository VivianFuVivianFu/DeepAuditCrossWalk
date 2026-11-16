import { expect, test } from "@playwright/test";

const scenario = (process.env.E2E_SCENARIO || "").trim().toLowerCase();

test.describe("Scenario B — Authenticated Private Test Workspace (non-demo tenant, PostgreSQL)", () => {
  test.skip(
    scenario !== "private_workspace",
    `Skipping Scenario B private-workspace suite unless E2E_SCENARIO='private_workspace' (current='${scenario || "unset"}').`
  );

  test("enforces fail-closed auth, ephemeral CI sign-in, private document upload + DB persistence, and session revocation on logout", async ({
    page,
    context,
    baseURL,
  }) => {
    const username = (process.env.E2E_USERNAME || "").trim();
    const password = (process.env.E2E_PASSWORD || "").trim();
    const expectedTenant = (process.env.E2E_TENANT_ID || "").trim();

    expect(
      username.length > 0 && password.length > 0 && expectedTenant.length > 0,
      "E2E_USERNAME, E2E_PASSWORD, and E2E_TENANT_ID must be provisioned by CI/test runner"
    ).toBe(true);
    expect(expectedTenant.toLowerCase()).not.toBe("public-demo");

    const errors: string[] = [];
    page.on("pageerror", (err) => errors.push(err.message));

    // 1. Unauthenticated access shows Sign-In Required and private API rejects with 401
    await page.goto("/");
    await expect(page.getByTestId("session-badge")).toContainText(
      /Sign-In Required for Private Workspace/i
    );
    const bodyText = await page.locator("body").innerText();
    expect(bodyText).not.toContain("LOCAL DEVELOPMENT AUTH BYPASS ACTIVE");
    expect(bodyText).not.toContain("analyst-local-pass");

    const unauthGet = await page.request.get(`${baseURL}/api/workspace`);
    expect(unauthGet.status()).toBe(401);
    const unauthPost = await page.request.post(`${baseURL}/api/workspace`, {
      data: { action: "list_policies" },
    });
    expect(unauthPost.status()).toBe(401);

    // Wrong password must be rejected with 401
    const badLogin = await page.request.post(`${baseURL}/api/auth/login`, {
      data: {
        username,
        password: `${password}-wrong`,
        tenant_id: expectedTenant,
      },
    });
    expect(badLogin.status()).toBe(401);

    // 2. Sign in via UI with ephemeral CI-provisioned credentials
    await page.getByLabel("Workspace username").fill(username);
    await page.getByLabel("Workspace password").fill(password);
    await page.getByLabel("Tenant ID (optional)").fill(expectedTenant);
    await page.getByRole("button", { name: /Sign in to Workspace/i }).click();

    await expect(page.getByTestId("session-badge")).toContainText(expectedTenant, {
      timeout: 15_000,
    });
    await expect(page.getByTestId("session-badge")).toContainText(/reviewer/i);

    // Session token must be stored in an HttpOnly cookie, not leaked to JS-readable cookies or localStorage
    const cookies = await context.cookies();
    const sessionCookie = cookies.find((c) => c.name === "crosswalk_session");
    expect(sessionCookie).toBeDefined();
    expect(sessionCookie?.httpOnly).toBe(true);
    const capturedSessionCookieHeader = `crosswalk_session=${sessionCookie?.value}`;

    const docCookie = await page.evaluate(() => document.cookie);
    expect(docCookie).not.toContain("crosswalk_session");

    // 3. Private Document-First workspace controls become accessible
    await expect(
      page.getByLabel("Upload Enterprise Questionnaire (.xlsx)")
    ).toBeVisible();

    // Retrieve CSRF token from authenticated /api/auth/session
    const sessRes = await page.request.get(`${baseURL}/api/auth/session`);
    expect(sessRes.status()).toBe(200);
    const sessBody = await sessRes.json();
    expect(sessBody.authenticated).toBe(true);
    expect(sessBody.tenant_id).toBe(expectedTenant);
    const csrfToken = String(sessBody.csrf_token || "");
    expect(csrfToken.length).toBeGreaterThan(10);

    // POST /api/workspace without CSRF header must fail with 403
    const missingCsrf = await page.request.post(`${baseURL}/api/workspace`, {
      data: { action: "list_policies" },
    });
    expect(missingCsrf.status()).toBe(403);

    // Authenticated private policy import + list retrieval against PostgreSQL backend
    const uniqueName = `CI Private Policy ${Date.now()}`;
    const imported = await page.request.post(`${baseURL}/api/workspace`, {
      headers: { "X-CSRF-Token": csrfToken },
      data: {
        action: "import_policy_text",
        name: uniqueName,
        category: "ai_governance",
        authority_level: "enterprise_policy",
        text: "1.1 All production AI systems must assign an accountable owner and undergo independent review before deployment.",
      },
    });
    expect(imported.status()).toBe(200);
    const importedData = await imported.json();
    expect(importedData.name).toBe(uniqueName);
    expect(importedData.policy_id).toBeTruthy();

    const listed = await page.request.post(`${baseURL}/api/workspace`, {
      headers: { "X-CSRF-Token": csrfToken },
      data: { action: "list_policies" },
    });
    expect(listed.status()).toBe(200);
    const listedData = await listed.json();
    const policiesList = Array.isArray(listedData)
      ? listedData
      : listedData.policies || [];
    expect(
      policiesList.some(
        (p: { policy_id?: string; name?: string }) =>
          p.policy_id === importedData.policy_id || p.name === uniqueName
      )
    ).toBe(true);

    // 4. Logout via UI invalidates session AND rejects subsequent replay of old cookie (401)
    const [logoutRes] = await Promise.all([
      page.waitForResponse(
        (res) =>
          res.url().includes("/api/auth/logout") &&
          res.request().method() === "POST"
      ),
      page.getByRole("button", { name: /Sign out/i }).click(),
    ]);
    expect(logoutRes.status()).toBe(200);
    await expect(page.getByTestId("session-badge")).toContainText(
      /Sign-In Required for Private Workspace/i,
      { timeout: 15_000 }
    );

    const replayGet = await page.request.get(`${baseURL}/api/workspace`, {
      headers: { Cookie: capturedSessionCookieHeader },
    });
    expect(replayGet.status()).toBe(401);

    const replayPost = await page.request.post(`${baseURL}/api/workspace`, {
      headers: {
        Cookie: capturedSessionCookieHeader,
        "X-CSRF-Token": csrfToken,
      },
      data: { action: "list_policies" },
    });
    expect(replayPost.status()).toBe(401);

    expect(errors).toEqual([]);
  });
});
