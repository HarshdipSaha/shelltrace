import { defineConfig, devices } from '@playwright/test';

const port = process.env.ST_UI_PORT ?? '5173';
const origin = `http://127.0.0.1:${port}`;

export default defineConfig({
  testDir: './e2e',
  fullyParallel: true,
  // These flows share the demo workspace and a single loopback MCP backend.
  workers: 1,
  // A three-pack playbook performs several sequential MCP round trips.
  expect: { timeout: 15_000 },
  reporter: 'list',
  use: {
    baseURL: origin,
    trace: 'retain-on-failure',
    ...devices['Desktop Chrome'],
  },
  webServer: {
    command: 'npm run dev -- --host 127.0.0.1',
    url: origin,
    reuseExistingServer: !process.env.CI,
    timeout: 30_000,
  },
});
