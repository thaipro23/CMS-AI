import { mkdirSync } from 'node:fs'
import path from 'node:path'
import { expect, test, type Page } from '@playwright/test'

const runtimePageErrors = new WeakMap<Page, string[]>()

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

const departmentPayload = [
  {
    department: {
      id: 'dep-cntt',
      code: 'CNTT',
      name: 'Công nghệ thông tin',
      description: 'Khối ngành công nghệ thông tin',
      status: 'active',
      created_at: '2026-06-01T00:00:00Z',
      updated_at: '2026-07-14T00:00:00Z',
    },
    stats: {
      total_questions: 80,
      approved_count: 50,
      pending_review_count: 20,
      draft_error_count: 0,
      unresolved_count: 2,
      rejected_count: 10,
      is_review_done: false,
      status: 'needs_fix',
      subject_count: 3,
      review_done_subject_count: 1,
      review_not_done_subject_count: 2,
      ready_to_release_chapter_count: 1,
    },
  },
  {
    department: {
      id: 'dep-kt',
      code: 'KT',
      name: 'Kinh tế',
      description: 'Khối ngành kinh tế',
      status: 'active',
      created_at: '2026-06-01T00:00:00Z',
      updated_at: '2026-07-14T00:00:00Z',
    },
    stats: {
      total_questions: 60,
      approved_count: 60,
      pending_review_count: 0,
      draft_error_count: 0,
      unresolved_count: 0,
      rejected_count: 0,
      is_review_done: true,
      status: 'ready',
      subject_count: 2,
      review_done_subject_count: 2,
      review_not_done_subject_count: 0,
      ready_to_release_chapter_count: 3,
    },
  },
]

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
    if (url.pathname === '/api/question-bank-v2/departments/summary') {
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(departmentPayload) })
      return
    }
    if (url.pathname === '/api/question-bank-v2/departments' && route.request().method() === 'POST') {
      await route.fulfill({ status: 201, contentType: 'application/json', body: JSON.stringify(departmentPayload[0].department) })
      return
    }
    if (url.pathname.startsWith('/api/question-bank-v2/departments/') && ['PATCH', 'DELETE'].includes(route.request().method())) {
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(route.request().method() === 'DELETE' ? { ok: true, deleted: true, message: 'Đã xóa' } : departmentPayload[0].department) })
      return
    }
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify([]) })
  })
}

test.describe('production UI smoke', () => {
  test.beforeEach(async ({ page }) => {
    const errors: string[] = []
    runtimePageErrors.set(page, errors)
    page.on('pageerror', (error) => errors.push(error.stack || error.message))
    await mockAuthenticatedApp(page)
  })

  test.afterEach(async ({ page }) => {
    expect(runtimePageErrors.get(page) || [], 'browser runtime errors').toEqual([])
  })

  test('desktop shell, dashboard and accessible modal work @desktop', async ({ page }) => {
    await page.goto('/bank')
    await expect(page.getByRole('heading', { level: 1, name: 'Tổng quan' })).toBeVisible()
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

  test('department list applies the batch-one shell and table contract @desktop', async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 960 })
    await page.goto('/bank/departments')

    await expect(page.getByRole('heading', { level: 1, name: 'Bộ môn' })).toBeVisible()
    await expect(page.getByRole('heading', { level: 2, name: 'Danh sách bộ môn' })).toBeVisible()
    await expect(page.getByRole('link', { name: /Công nghệ thông tin/ })).toBeVisible()
    await expect(page.getByText('Kinh tế', { exact: true })).toBeVisible()

    const activeItems = page.locator('.enterprise-nav-link.active')
    await expect(activeItems).toHaveCount(1)
    await expect(activeItems.first()).toContainText('Ngân hàng đề')

    const layout = await page.evaluate(() => ({
      documentOverflow: document.documentElement.scrollWidth - document.documentElement.clientWidth,
      bodyOverflow: document.body.scrollWidth - document.body.clientWidth,
      bodyOverflowY: getComputedStyle(document.body).overflowY,
      contentOverflowY: getComputedStyle(document.querySelector('.enterprise-content') as HTMLElement).overflowY,
    }))
    expect(layout.documentOverflow).toBeLessThanOrEqual(1)
    expect(layout.bodyOverflow).toBeLessThanOrEqual(1)
    expect(layout.bodyOverflowY).toBe('hidden')
    expect(layout.contentOverflowY).toBe('auto')

    const createButton = page.getByRole('button', { name: 'Thêm bộ môn' }).first()
    await createButton.focus()
    await createButton.click()
    const dialog = page.getByRole('dialog', { name: 'Thêm bộ môn' })
    await expect(dialog).toBeVisible()
    await expect(page.getByLabel('Mã bộ môn *')).toBeFocused()
    if (process.env.BANK_UI_EVIDENCE_DIR) {
      const evidenceDir = path.resolve(process.env.BANK_UI_EVIDENCE_DIR)
      mkdirSync(evidenceDir, { recursive: true })
      await page.screenshot({ path: path.join(evidenceDir, 'bank-departments-create-dialog-1440.png'), fullPage: false })
    }
    await page.keyboard.press('Escape')
    await expect(dialog).toBeHidden()
    await expect(createButton).toBeFocused()
  })

  test('department page remains usable at required responsive widths @desktop', async ({ page }) => {
    const evidenceDir = process.env.BANK_UI_EVIDENCE_DIR
      ? path.resolve(process.env.BANK_UI_EVIDENCE_DIR)
      : null
    if (evidenceDir) mkdirSync(evidenceDir, { recursive: true })

    const viewports = [
      { width: 1440, height: 960, name: '1440' },
      { width: 1366, height: 900, name: '1366' },
      { width: 1024, height: 768, name: '1024' },
      { width: 768, height: 900, name: '768' },
      { width: 390, height: 844, name: '390' },
    ]

    for (const viewport of viewports) {
      await page.setViewportSize({ width: viewport.width, height: viewport.height })
      await page.goto('/bank/departments')
      await expect(page.getByRole('heading', { level: 1, name: 'Bộ môn' })).toBeVisible()
      await expect(page.getByRole('button', { name: 'Thêm bộ môn' }).first()).toBeVisible()
      const responsiveLayout = await page.evaluate(() => {
        const statusCell = document.querySelector('.enterprise-data-table td.enterprise-kind-status') as HTMLElement | null
        const tableScroll = document.querySelector('.enterprise-table-scroll') as HTMLElement | null
        return {
          pageOverflow: document.documentElement.scrollWidth - document.documentElement.clientWidth,
          statusDisplay: statusCell ? getComputedStyle(statusCell).display : null,
          tableClientWidth: tableScroll?.clientWidth || 0,
          tableScrollWidth: tableScroll?.scrollWidth || 0,
          sectionHeight: (document.querySelector('.bank-list-section') as HTMLElement | null)?.getBoundingClientRect().height || 0,
        }
      })
      expect(responsiveLayout.pageOverflow, `horizontal page overflow at ${viewport.name}px`).toBeLessThanOrEqual(1)
      expect(responsiveLayout.statusDisplay, `status visibility at ${viewport.name}px`).toBe('table-cell')
      if (viewport.width >= 1024) {
        expect(responsiveLayout.sectionHeight, `content-sized table section at ${viewport.name}px`).toBeLessThan(viewport.height - 160)
      }
      if (viewport.width <= 768) expect(responsiveLayout.tableScrollWidth).toBeGreaterThan(responsiveLayout.tableClientWidth)
      if (evidenceDir) {
        await page.screenshot({ path: path.join(evidenceDir, `bank-departments-${viewport.name}.png`), fullPage: false })
      }
    }

    await page.setViewportSize({ width: 390, height: 844 })
    const menuButton = page.getByRole('button', { name: 'Mở menu' })
    await menuButton.click()
    await expect(page.getByRole('dialog', { name: 'Điều hướng chính' })).toBeVisible()
    await page.waitForTimeout(250)
    if (evidenceDir) {
      await page.screenshot({ path: path.join(evidenceDir, 'bank-departments-390-drawer.png'), fullPage: false })
    }
    await page.keyboard.press('Escape')
    await expect(page.getByRole('dialog', { name: 'Điều hướng chính' })).toBeHidden()
    await page.getByRole('button', { name: 'Thêm bộ môn' }).first().click()
    await expect(page.getByRole('dialog', { name: 'Thêm bộ môn' })).toBeVisible()
    if (evidenceDir) {
      await page.screenshot({ path: path.join(evidenceDir, 'bank-departments-create-dialog-390.png'), fullPage: false })
    }
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
