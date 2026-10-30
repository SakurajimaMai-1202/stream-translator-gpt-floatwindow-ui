import { defineConfig } from '@playwright/test';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';

// Workers evaluate this file again; inherit the runner's isolated config.
if (!process.env.E2E_CONFIG_FILE) {
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), 'fw-e2e-'));
  process.env.E2E_CONFIG_FILE = path.join(directory, 'config.yaml');
  fs.writeFileSync(process.env.E2E_CONFIG_FILE, 'interface:\n  mode: advanced\nserver:\n  public_port: 18765\n', 'utf8');
}

export default defineConfig({
  testDir: './e2e',
  workers: 1,
  fullyParallel: false,
  retries: 0,
  use: {
    browserName: 'chromium',
    baseURL: 'http://localhost:5181',
    locale: 'zh-TW',
    launchOptions: {
      executablePath: process.env.PLAYWRIGHT_CHROMIUM_PATH || undefined,
    },
  },
  webServer: [
    {
      command: `"${process.env.E2E_PYTHON || 'python'}" -m uvicorn backend.main:app --port 8011 --log-level warning`,
      cwd: '../',
      url: 'http://127.0.0.1:8011/api/health',
      env: {
        STREAM_TRANSLATOR_CONFIG_FILE: process.env.E2E_CONFIG_FILE!,
        FLOATWINDOW_SKIP_RUNTIME_WARMUP: '1',
        FLOATWINDOW_ADMIN_TOKEN: '',
      },
      reuseExistingServer: false,
    },
    {
      command: 'npx vite --port 5181 --strictPort',
      url: 'http://localhost:5181',
      env: { FLOATWINDOW_BACKEND_PORT: '8011' },
      reuseExistingServer: false,
    },
  ],
});
