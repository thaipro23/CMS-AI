import { defineConfig, devices } from '@playwright/test'

const systemChromium = process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH

export default defineConfig({
  testDir: './tests',
  timeout: 45_000,
  expect: { timeout: 10_000 },
  fullyParallel: true,
  forbidOnly: Boolean(process.env.CI),
  retries: process.env.CI ? 2 : 0,
  workers: process.env.CI ? 2 : undefined,
  reporter: process.env.CI ? [['line'], ['html', { open: 'never', outputFolder: 'playwright-report' }]] : 'list',
  use: {
    launchOptions: systemChromium ? { executablePath: systemChromium } : undefined,
    baseURL: 'http://localhost:3100',
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
    video: systemChromium ? 'off' : 'retain-on-failure',
    locale: 'vi-VN',
  },
  projects: [
    { name: 'chromium-desktop', grep: /@desktop|@all/, use: { ...devices['Desktop Chrome'] } },
    { name: 'chromium-mobile', grep: /@mobile|@all/, use: { ...devices['Pixel 5'] } },
  ],
  webServer: {
    command: 'NEXT_PUBLIC_APP_ENV=e2e NEXT_PUBLIC_AUTO_CMS_SESSION_LOGIN=false NEXT_PUBLIC_API_BASE_URL=http://localhost:8000 npm --prefix ../frontend run dev -- -p 3100',
    url: 'http://localhost:3100/auth/logged-out',
    reuseExistingServer: !process.env.CI,
    timeout: 120_000,
    stdout: 'pipe',
    stderr: 'pipe',
  },
})
