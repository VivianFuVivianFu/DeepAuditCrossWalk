import { test, expect } from "@playwright/test";

test("document-first two-upload workspace and isolated synthetic demo workflows", async ({
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
  await expect(
    page.getByLabel("Entity-specific IDR duty confirmed"),
  ).toHaveValue("unknown");

  // Verify Strategy target is clearly presented as Planned / Unavailable
  await page
    .getByRole("button", { name: "AI Governance Strategy (Planned)" })
    .click();
  await expect(
    page.getByText(/Planned \/ Unavailable in PR 2/i),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "AI Assurance Questionnaire (.xlsx)" })
    .click();

  // Verify Synthetic Demo Example tab remains isolated and functional
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
  await page.getByRole("button", { name: "Enterprise policy gaps" }).click();
  await page.getByRole("button", { name: "Run assessment" }).click();
  await expect(
    page.getByRole("heading", { name: "Traceable assessment results" }),
  ).toBeVisible();
  const download = page.waitForEvent("download");
  await page.getByRole("button", { name: "Export JSON" }).click();
  expect((await download).suggestedFilename()).toMatch(/^crosswalk-.+\.json$/);
});

test("mobile context form fits the viewport and unknown facts are retained", async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/");
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
