import { test, expect } from "@playwright/test";

test("document-first authenticated workspace and isolated synthetic demo workflows", async ({
  page,
}) => {
  await page.goto("/");
  await page.screenshot({
    path: "test-results/home-desktop.png",
    fullPage: false,
  });
  await expect(page.getByRole("heading", { level: 1 })).toContainText(
    "your assessment misses",
  );
  await expect(
    page.getByRole("button", { name: "1. Assess a Document (Primary)" }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "2. Add Enterprise Policies (Optional)" }),
  ).toBeVisible();

  // 1. Verify Unauthenticated State: Sign-in prompt on private tabs
  await expect(
    page.getByRole("heading", { name: "Sign in to access private tenant documents" })
  ).toBeVisible();
  await expect(page.getByLabel("Workspace username")).toBeVisible();
  await expect(page.getByLabel("Workspace password")).toBeVisible();

  // 2. Verify Anonymous Synthetic Demo remains accessible without login
  await page
    .getByRole("button", {
      name: "Synthetic Demo Example (DEMO_BANKING_V1)",
    })
    .click();
  await page.getByRole("button", { name: "Load example" }).click();
  await page.getByRole("button", { name: "Run assessment" }).click();
  await expect(
    page.getByRole("heading", { name: "Traceable assessment results" }),
  ).toBeVisible();
  await expect(page.getByRole("button", { name: "Export JSON" })).toBeVisible();
  const firstObligation = page.locator("details").first();
  await firstObligation.locator("summary").click();
  await expect(firstObligation).toContainText("Approved mappings: none");
  await page.screenshot({
    path: "test-results/coverage-desktop.png",
    fullPage: true,
  });

  // 3. Authenticate into private workspace
  await page
    .getByRole("button", { name: "1. Assess a Document (Primary)" })
    .click();
  await page.getByLabel("Workspace username").fill("analyst");
  await page.getByLabel("Workspace password").fill("analyst-local-pass");
  await page.getByRole("button", { name: "Sign in to Workspace →" }).click();

  // Verify Session Badge and private workspace unlocked
  await expect(page.getByTestId("session-badge")).toContainText("analyst");
  await expect(page.getByRole("button", { name: "Sign out" })).toBeVisible();
  await expect(page.getByText("Upload Enterprise Questionnaire")).toBeVisible();

  // 4. Verify Strategy Target is clearly presented as Planned / Unavailable
  await page
    .getByRole("button", { name: "AI Governance Strategy (Planned)" })
    .click();
  await expect(
    page.getByText(/Planned \/ Unavailable in PR 2/i),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "AI Assurance Questionnaire (.xlsx)" })
    .click();

  // 5. Test sign out
  await page.getByRole("button", { name: "Sign out" }).click();
  await expect(
    page.getByRole("heading", { name: "Sign in to access private tenant documents" })
  ).toBeVisible();
  await expect(page.getByTestId("session-badge")).toContainText("Sign-In Required");
});

test("mobile context form fits the viewport and unknown facts are retained", async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/");
  await page
    .getByRole("button", {
      name: "Synthetic Demo Example (DEMO_BANKING_V1)",
    })
    .click();
  await expect(page.getByLabel("APRA-regulated entity")).toHaveValue("unknown");
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  await page.screenshot({
    path: "test-results/home-mobile.png",
    fullPage: true,
  });
});
