import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false,
  timeout: 45_000,
  use: {
    baseURL: process.env.SMOKE_WEB_URL || "http://127.0.0.1:3000",
    channel: process.env.PLAYWRIGHT_CHANNEL || undefined,
    headless: true,
    trace: "retain-on-failure",
  },
});
