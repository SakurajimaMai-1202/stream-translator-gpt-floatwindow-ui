import { test, expect } from '@playwright/test';
import fs from 'node:fs';

test('新增詞條後重新載入可搜尋並保留譯法', async ({ page }) => {
  const original = 'すいちゃんE2E';
  const translated = '水星測試詞條';
  await page.goto('/settings?tab=terminology');
  await page.getByPlaceholder('例如：すいちゃん', { exact: true }).fill(original);
  await page.getByPlaceholder('留空＝只修正辨識', { exact: true }).fill(translated);
  await page.getByRole('button', { name: '新增', exact: true }).click();
  await expect(page.getByText('✓ 已自動儲存', { exact: true })).toBeVisible();
  const readConfig = () => fs.readFileSync(process.env.E2E_CONFIG_FILE!, 'utf8');
  await expect.poll(readConfig).toContain(original);
  await page.reload();
  await page.getByRole('textbox', { name: '搜尋詞條', exact: true }).fill(original);
  const row = page.locator('.term-row').filter({
    has: page.locator(`input[value="${original}"]`),
  });
  await expect(row.getByRole('textbox', { name: '譯法', exact: true })).toHaveValue(translated);
  await expect.poll(readConfig).toContain(original);
});
