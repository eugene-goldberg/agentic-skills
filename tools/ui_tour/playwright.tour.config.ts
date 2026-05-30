/**
 * Playwright config override for the UI tour: always-on full-page
 * screenshots, single worker, no retries.
 *
 * Mirrors the gate's playwright.config.ts pattern: spawn a vite dev
 * server inside the playwright container on localhost:5173 and target
 * that. This avoids the CORS issue that arises when the browser loads
 * `http://frontend:80` (not in BACKEND_CORS_ORIGINS) and tries to POST
 * to `http://backend:8000` — login silently fails, no error toast,
 * no redirect.
 *
 * Three projects:
 *  - "setup"       — runs auth.setup.ts to log in as firstSuperuser
 *  - "tour-public" — public routes; no setup dep (always runs)
 *  - "tour-authed" — authed routes; depends on setup, uses storageState
 */
import { defineConfig, devices } from "@playwright/test"
import "dotenv/config"

export default defineConfig({
  testDir: "./tests",
  fullyParallel: false,
  workers: 1,
  retries: 0,
  reporter: [["list"]],
  timeout: 90_000,
  use: {
    baseURL: "http://localhost:5173",
    screenshot: "on",
    trace: "off",
    video: "off",
    actionTimeout: 20_000,
    navigationTimeout: 45_000,
  },
  webServer: {
    command: "bun run dev",
    url: "http://localhost:5173",
    reuseExistingServer: false,
    timeout: 60_000,
  },
  projects: [
    {
      name: "setup",
      testMatch: /auth\.setup\.ts/,
    },
    {
      name: "tour-public",
      testMatch: /_ui_tour\.spec\.ts/,
      grep: /UI Tour — public routes/,
      use: { ...devices["Desktop Chrome"] },
    },
    {
      name: "tour-authed",
      testMatch: /_ui_tour\.spec\.ts/,
      grep: /UI Tour — authed routes/,
      use: {
        ...devices["Desktop Chrome"],
        storageState: "playwright/.auth/user.json",
      },
      dependencies: ["setup"],
    },
  ],
})
