import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  timeout: 45_000,
  expect: { timeout: 10_000 },
  fullyParallel: false,
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? [["html", {open: "never"}], ["list"]] : "list",
  use: {baseURL: process.env.PLAYWRIGHT_BASE_URL || "http://127.0.0.1:3000", trace: "retain-on-failure", screenshot: "only-on-failure", ...devices["Desktop Chrome"]},
});
