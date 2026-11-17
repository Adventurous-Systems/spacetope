// SPDX-License-Identifier: AGPL-3.0-or-later
// SPDX-FileCopyrightText: 2026 Adventurous Systems

import { defineConfig } from '@playwright/test';

export default defineConfig({
  testDir: './tests',
  timeout: 120_000,
  retries: 0,
  workers: 1,   // tests share one backend and generation is CPU-bound; parallel runs distort the timing checks
  use: { baseURL: process.env.BASE_URL || 'http://localhost:5273', headless: true, viewport: { width: 1400, height: 900 } },
  reporter: [['list'], ['html', { open: 'never' }]],
});
