import { expect, test } from "@playwright/test";

const scenario = (process.env.E2E_SCENARIO || "public_demo").trim().toLowerCase();

test.describe("Scenario A — Production Public Demo (ENV=production, tenant=public-demo)", () => {
  test.skip(
    scenario !== "public_demo",
    `Skipping Scenario A public-demo suite because E2E_SCENARIO='${scenario}'.`
  );

  test("anonymous synthetic demo executes cleanly while private workspace & fixture creds stay locked", async ({
    page,
    baseURL,
  }) => {
    const errors: string[] = [];
    page.on("pageerror", (err) => errors.push(err.message));

    await page.goto("/");

    // 1. Public landing page renders with Sign-In Required badge and NO dev fixture password leaks
    await expect(
      page.getByRole("heading", { name: /Find the requirements/i })
    ).toBeVisible();
    await expect(page.getByTestId("session-badge")).toContainText(
      /Sign-In Required for Private Workspace/i
    );
    const bodyText = await page.locator("body").innerText();
    expect(bodyText).not.toContain("LOCAL DEVELOPMENT AUTH BYPASS ACTIVE");
    expect(bodyText).not.toContain("analyst-local-pass");
    expect(bodyText).not.toContain("reviewer-local-pass");

    // 2. Private workspace APIs reject unauthenticated / public-demo calls
    const wsGet = await page.request.get(`${baseURL}/api/workspace`);
    expect([403, 503]).toContain(wsGet.status());

    const wsPostList = await page.request.post(`${baseURL}/api/workspace`, {
      data: { action: "list_questionnaires" },
    });
    expect([403, 503]).toContain(wsPostList.status());

    const wsPostUpload = await page.request.post(`${baseURL}/api/workspace`, {
      data: {
        action: "import_policy_text",
        name: "Unauthorized Upload",
        text: "1.1 Must not persist into public-demo",
      },
    });
    expect([403, 503]).toContain(wsPostUpload.status());

    // 3. Dev fixture accounts must NEVER authenticate in ENV=production public-demo mode
    const devLogin = await page.request.post(`${baseURL}/api/auth/login`, {
      data: {
        username: "analyst",
        password: ["analyst", "local", "pass"].join("-"),
      },
    });
    expect([401, 403, 503]).toContain(devLogin.status());
    const devLoginBody = await devLogin.json().catch(() => ({}));
    expect(devLoginBody.authenticated).not.toBe(true);

    // 4. Synthetic Demo tab works anonymously end-to-end without signing in
    await page
      .getByRole("button", { name: /Synthetic Demo Example/i })
      .click();
    await expect(
      page.getByText(/Isolated Synthetic Demonstration \(DEMO_BANKING_V1\)/i)
    ).toBeVisible();

    await page.getByRole("button", { name: /Load example/i }).click();
    await page.getByRole("button", { name: /Run assessment/i }).click();

    await expect(
      page.getByRole("heading", { name: /Traceable assessment results/i })
    ).toBeVisible({ timeout: 20_000 });
    await expect(
      page.getByText(/Regulatory pack/i)
    ).toBeVisible();

    expect(errors).toEqual([]);
  });
});
