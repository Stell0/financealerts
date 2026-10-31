import { defineConfig } from "@playwright/test";
import { existsSync } from "node:fs";

const localChrome = ["/usr/bin/chromium", "/opt/google/chrome/chrome"].find(
  existsSync,
);
export default defineConfig({
  testDir: "./tests",
  fullyParallel: true,
  workers: 2,
  timeout: 30000,
  use: {
    baseURL: "http://127.0.0.1:4173/financealerts/",
    headless: true,
    launchOptions: localChrome ? { executablePath: localChrome } : {},
  },
  webServer: {
    command: "node serve.mjs",
    url: "http://127.0.0.1:4173/financealerts/",
    reuseExistingServer: !process.env.CI,
  },
  reporter: "list",
});
