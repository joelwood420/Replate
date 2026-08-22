import { defineConfig, devices } from '@playwright/test';

// Target the deployed prod site (CloudFrontUrl) in CI; default to a local dev server for
// hand-runs. The full journey hits real Anthropic calls, so timeouts are generous and the
// suite runs serially against a single rate-limited demo user.
const baseURL = process.env.E2E_BASE_URL || 'http://localhost:5173';

export default defineConfig({
  testDir: './tests',
  timeout: 240_000,
  expect: { timeout: 15_000 },
  retries: process.env.CI ? 1 : 0,
  workers: 1,
  forbidOnly: !!process.env.CI,
  reporter: [['html', { open: 'never' }], ['list']],
  use: {
    baseURL,
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
    video: 'retain-on-failure',
    // The capture screen needs GPS; provide a fixed, restaurant-dense location so the
    // pipeline finds a restaurant to match against.
    permissions: ['geolocation'],
    geolocation: { latitude: 40.758, longitude: -73.9855 },
    locale: 'en-US',
  },
  projects: [
    {
      name: 'chromium',
      use: {
        ...devices['Desktop Chrome'],
        launchOptions: {
          // A fake camera so getUserMedia succeeds headless (the capture screen shows an
          // error and hides the flow otherwise), and auto-accept the media permission.
          args: ['--use-fake-ui-for-media-stream', '--use-fake-device-for-media-stream'],
        },
      },
    },
  ],
});
