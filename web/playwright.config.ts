import { defineConfig, devices } from "@playwright/test";
import { e2eHome, e2ePort, fakeLlmDir } from "./e2e/home";

const baseURL = `http://127.0.0.1:${e2ePort}`;

export default defineConfig({
  testDir: "./e2e",
  timeout: 240_000,
  expect: { timeout: 120_000 },
  fullyParallel: false,
  workers: 1,
  retries: 0,
  globalSetup: "./e2e/global-setup.ts",
  use: {
    baseURL,
    trace: "retain-on-failure",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: {
    command: `npx next dev --hostname 127.0.0.1 --port ${e2ePort}`,
    url: `${baseURL}/toolbox`,
    timeout: 120_000,
    reuseExistingServer: false,
    env: {
      ...process.env,
      GTJOB_HOME: e2eHome,
      GTJOB_FAKE_LLM: fakeLlmDir,
      GTJOB_NEXT_DIST: ".next-e2e",
    },
  },
});
