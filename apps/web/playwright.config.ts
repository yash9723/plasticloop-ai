import { defineConfig, devices } from "@playwright/test";

// Runs against a production build (service worker enabled), e.g. the docker compose stack.
const baseURL = process.env.E2E_BASE_URL ?? "http://localhost:3000";

export default defineConfig({
  testDir: "tests/e2e",
  timeout: 90_000,
  expect: { timeout: 15_000 },
  retries: 0,
  workers: 1, // tests share one seeded demo database
  reporter: [["list"], ["html", { open: "never" }]],
  use: { baseURL, trace: "retain-on-failure", screenshot: "only-on-failure" },
  // Service workers need a secure context: run against http://localhost:<port> (or HTTPS), not another hostname.
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
});
