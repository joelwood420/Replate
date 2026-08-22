import { test, expect, type Page } from '@playwright/test';

const EMAIL = process.env.E2E_USER_EMAIL;
const PASSWORD = process.env.E2E_USER_PASSWORD;

async function signIn(page: Page, email: string, password: string) {
  await page.goto('/signin');
  await page.getByLabel('Email').fill(email);
  await page.getByLabel('Password').fill(password);
  await page.getByRole('button', { name: 'Log in' }).click();
}

// The one happy path that spends Anthropic money: sign in, scan a dish, wait for stage-1
// identification, reverse-engineer it, and confirm the structured recipe view renders.
test('full journey: sign in, scan, identify, reverse-engineer, see recipe', async ({ page }) => {
  test.skip(!EMAIL || !PASSWORD, 'E2E_USER_EMAIL / E2E_USER_PASSWORD are not set');

  await signIn(page, EMAIL!, PASSWORD!);
  await expect(page).toHaveURL(/\/home$/, { timeout: 30_000 });

  await page.getByRole('button', { name: 'Open Camera' }).click();
  await expect(page).toHaveURL(/\/capture$/);

  // Live mode: the shutter enables once geolocation arrives. Also wait for the fake camera
  // to produce frames, or capturePhoto() would return null.
  const shutter = page.getByRole('button', { name: 'Capture photo' });
  await expect(shutter).toBeEnabled({ timeout: 30_000 });
  await expect
    .poll(() => page.evaluate(() => document.querySelector('video')?.videoWidth ?? 0), {
      timeout: 15_000,
    })
    .toBeGreaterThan(0);
  await shutter.click();

  // Stage 1 runs (restaurant lookup + menu fetch + vision + match). When it reaches the
  // terminal Identified state, the reverse-engineer button appears.
  await expect(page).toHaveURL(/\/jobs\//, { timeout: 30_000 });
  const reverseButton = page.getByRole('button', { name: 'Reverse engineer this dish' });
  await expect(reverseButton).toBeVisible({ timeout: 180_000 });

  // Stage 2: the heaviest call. On completion the result view renders its three sections.
  await reverseButton.click();
  await expect(page.getByText('The Components', { exact: true })).toBeVisible({ timeout: 180_000 });
  await expect(page.getByText('Ingredients', { exact: true })).toBeVisible();
  await expect(page.getByText('Method', { exact: true })).toBeVisible();
});

// Cheap failure paths (no Anthropic cost, no demo-user quota consumed).

test('unauthenticated access redirects to sign in', async ({ page }) => {
  await page.goto('/home');
  await expect(page).toHaveURL(/\/signin$/, { timeout: 30_000 });
});

test('a wrong password is rejected and stays on the sign-in screen', async ({ page }) => {
  // A bogus account, so this never touches the real demo user.
  await signIn(page, 'no-such-e2e-user@example.com', 'definitely-the-wrong-password-1');

  // The button returns from "Signing in…" to "Log in" on failure, and we do not navigate.
  await expect(page.getByRole('button', { name: 'Log in' })).toBeVisible({ timeout: 30_000 });
  await expect(page).toHaveURL(/\/signin$/);
});
