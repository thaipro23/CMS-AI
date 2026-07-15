import { expect, test, type Page } from '@playwright/test'

const dashboardPayload = {
  scope: { role: 'SYSTEM_ADMIN', label: 'Toàn hệ thống', scope_type: 'SYSTEM', scope_id: '*' },
  filters: { date_range: '30d', from_date: '2026-06-15', to_date: '2026-07-14' },
  kpis: {
    total_questions: { key: 'total_questions', label: 'Tổng câu hỏi', value: 40 },
    pending_review: { key: 'pending_review', label: 'Chờ duyệt', value: 20 },
    approved: { key: 'approved', label: 'Đã duyệt', value: 3 },
    rejected: { key: 'rejected', label: 'Bị loại', value: 17 },
  },
  charts: {
    question_status: { key: 'question_status', title: 'Trạng thái', type: 'donut', items: [] },
    new_questions_by_day: { key: 'new_questions_by_day', title: 'Câu hỏi mới', type: 'line', items: [] },
    questions_by_subject: { key: 'questions_by_subject', title: 'Theo môn', type: 'horizontal_bar', items: [] },
    difficulty_distribution: { key: 'difficulty_distribution', title: 'Độ khó', type: 'donut', items: [] },
    question_type_distribution: { key: 'question_type_distribution', title: 'Loại câu', type: 'donut', items: [] },
    term_comparison: { key: 'term_comparison', title: 'So sánh kỳ', type: 'grouped_bar', items: [] },
  },
  alerts: [{ id: 'alert-1', severity: 'warning', type: 'review', title: 'Có câu hỏi chờ duyệt', description: '20 câu cần xử lý.' }],
  activity_feed: [],
  meta: { departments_total: 1, subjects_total: 2, subject_versions_total: 2, chapters_total: 4 },
  generated_at: '2026-07-14T10:18:45Z',
  cache: { hit: true, ttl_seconds: 45 },
}

async function mockAuthenticatedApp(page: Page) {
  await page.addInitScript(() => {
    localStorage.setItem('ai_openedx_role', 'admin')
    localStorage.setItem('ai_openedx_user_id', 'e2e-admin')
    sessionStorage.setItem('ai_openedx_session_token', JSON.stringify({
      access_token: 'e2e-token',
      user_id: 'e2e-admin',
      role: 'admin',
    }))
  })
  await page.route('http://localhost:8000/api/**', async (route) => {
    const url = new URL(route.request().url())
    if (url.pathname === '/api/rbac/me') {
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({
        user_id: 'e2e-admin',
        effective_legacy_role: 'admin',
        is_system_admin: true,
        business_permissions: ['bank.view', 'jobs.view', 'audit.view', 'rbac.view'],
        assignments: [],
      }) })
      return
    }
    if (url.pathname === '/api/question-bank-v2/dashboard/analytics') {
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(dashboardPayload) })
      return
    }
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify([]) })
  })
}

test.describe('production UI smoke', () => {
  test.beforeEach(async ({ page }) => {
    await mockAuthenticatedApp(page)
  })

  test('desktop shell, dashboard and accessible modal work @desktop', async ({ page }) => {
    await page.goto('/bank')
    await expect(page.getByRole('heading', { level: 1, name: 'Tổng quan Ngân hàng câu hỏi' })).toBeVisible()
    await expect(page.getByRole('navigation', { name: 'Chức năng hệ thống' })).toBeVisible()
    await expect(page.getByText('Tổng câu hỏi')).toBeVisible()

    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)
    expect(overflow).toBeLessThanOrEqual(1)

    const alertButton = page.getByRole('button', { name: /Cảnh báo \(1\)/ })
    await alertButton.focus()
    await alertButton.click()
    const dialog = page.getByRole('dialog', { name: 'Cảnh báo cần xử lý' })
    await expect(dialog).toBeVisible()
    await page.keyboard.press('Escape')
    await expect(dialog).toBeHidden()
    await expect(alertButton).toBeFocused()
  })

  test('mobile sidebar is a keyboard-dismissable drawer @mobile', async ({ page }) => {
    await page.goto('/bank')
    const menuButton = page.getByRole('button', { name: 'Mở menu' })
    await menuButton.click()
    const drawer = page.getByRole('dialog', { name: 'Điều hướng chính' })
    await expect(drawer).toBeVisible()
    await page.keyboard.press('Escape')
    await expect(drawer).toBeHidden()
    await expect(menuButton).toBeFocused()
  })

  test('not-found boundary is useful @all', async ({ page }) => {
    await page.goto('/route-khong-ton-tai-e2e')
    await expect(page.getByText(/không tìm thấy/i)).toBeVisible()
    await expect(page.getByRole('link').first()).toBeVisible()
  })
})
