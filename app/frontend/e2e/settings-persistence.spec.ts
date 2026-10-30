import { test, expect, type Page } from '@playwright/test';
import fs from 'node:fs';

const readConfig = () => fs.readFileSync(process.env.E2E_CONFIG_FILE!, 'utf8');
const minimumAudio = (page: Page) => page.locator('label')
  .filter({ hasText: '最小音訊長度' })
  .locator('xpath=following::input[1]');

async function saveMinimumAudio(page: Page) {
  await page.goto('/settings?tab=audio_vad');
  const input = minimumAudio(page);
  await expect(input).toBeVisible();
  // Force an edit even when another test has already saved 0.9.
  await input.fill('0.8');
  await input.fill('0.9');
  await expect(page.getByText('✓ 已自動儲存', { exact: true })).toBeVisible();
  await expect.poll(readConfig).toMatch(/min_audio_length: 0\.9\s/);
}

test('最小音訊長度儲存後重新載入仍保留', async ({ page }) => {
  await saveMinimumAudio(page);
  await page.reload();
  await expect(minimumAudio(page)).toHaveValue('0.9');
  await expect.poll(readConfig).toMatch(/min_audio_length: 0\.9\s/);
});

test('超過上限的最小音訊長度不會寫入設定', async ({ page }) => {
  await saveMinimumAudio(page);
  await minimumAudio(page).fill('99');
  await expect(page.getByRole('alert').filter({ hasText: '不可大於' })).toBeVisible();
  await page.reload();
  await expect(minimumAudio(page)).toHaveValue('0.9');
  await expect.poll(readConfig).toMatch(/min_audio_length: 0\.9\s/);
  await expect.poll(readConfig).not.toMatch(/min_audio_length: 99/);
});
