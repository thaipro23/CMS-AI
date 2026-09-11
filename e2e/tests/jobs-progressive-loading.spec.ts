import { expect, test, type Page, type Route } from '@playwright/test'

function gate() {
  let release!: () => void
  const promise = new Promise<void>(resolve => { release = resolve })
  return { promise, release }
}

function bankJob(id: string, status = 'running') {
  return { id, operation_type: 'legacy_quiz_import', status, progress_current: 1, progress_total: 2,
    progress_percent: 50, target_type: id, requested_by: '29', created_at: '2026-09-11T08:00:00Z' }
}

async function json(route: Route, body: unknown, status = 200) {
  await route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) })
}

async function mockJobs(page: Page, respond: (route: Route, url: URL) => Promise<boolean>) {
  await page.addInitScript(() => {
    sessionStorage.setItem('ai_openedx_session_token', JSON.stringify({ access_token: 'e2e-token', user_id: '29', role: 'admin' }))
    localStorage.setItem('ai_openedx_role', 'admin')
    localStorage.setItem('ai_openedx_user_id', '29')
  })
  await page.route('http://localhost:8000/api/**', async route => {
    const url = new URL(route.request().url())
    if (url.pathname.endsWith('/rbac/me')) {
      await json(route, { user_id: '29', effective_legacy_role: 'admin', is_system_admin: true,
        business_permissions: ['user.manage_all'], assignments: [] })
    } else if (!await respond(route, url)) {
      await json(route, url.pathname.endsWith('/analytics/ops/status') ? { ingest: {} } : [])
    }
  })
}

test('primary jobs render while supplemental APIs are pending and later populate independently @desktop', async ({ page }) => {
  const quiz = gate()
  const analytics = gate()
  await mockJobs(page, async (route, url) => {
    if (url.pathname.endsWith('/course-quiz-instances')) {
      await quiz.promise
      await json(route, [{ id: 'quiz-1', openedx_course_id: 'course-v1:FreshQuiz', status: 'created', metadata_json: {} }])
    } else if (url.pathname.endsWith('/analytics/ops/status')) {
      await analytics.promise
      await json(route, { ingest: { last_status: 'running', file_exists: true } })
    } else if (url.pathname.endsWith('/question-bank-v2/operation-jobs')) {
      await json(route, { items: [bankJob('Primary import')] })
    } else return false
    return true
  })
  try {
    await page.goto('/jobs')
    await expect(page.getByRole('button', { name: 'Tải lại', exact: true })).toBeEnabled()
    await expect(page.getByText('Primary import', { exact: true })).toBeVisible()
    await page.getByRole('button', { name: 'Quiz gần đây', exact: true }).click()
    const drawer = page.getByRole('dialog', { name: 'Quiz gần đây' })
    await expect(drawer.getByText('Chưa có Quiz trên CMS')).not.toBeVisible()
    quiz.release()
    await expect(drawer.getByText('course-v1:FreshQuiz', { exact: true })).toBeVisible()
    await page.keyboard.press('Escape')
    analytics.release()
    await expect(page.getByText('Ingest học online', { exact: true })).toBeVisible()
  } finally {
    quiz.release()
    analytics.release()
  }
})

test('one failed job source leaves successful jobs visible and reports a recoverable error @desktop', async ({ page }) => {
  await mockJobs(page, async (route, url) => {
    if (url.pathname.endsWith('/question-bank-v2/operation-jobs')) {
      await json(route, { items: [bankJob('Available import')] })
    } else if (url.pathname.endsWith('/report-jobs')) {
      await json(route, { detail: 'Không tải được báo cáo giáo viên.' }, 500)
    } else return false
    return true
  })
  await page.goto('/jobs')
  await expect(page.getByText('Available import', { exact: true })).toBeVisible()
  await expect(page.locator('.enterprise-action-message')).toContainText('báo cáo')
  await expect(page.getByRole('button', { name: 'Tải lại', exact: true })).toBeEnabled()
})

test('late primary responses cannot overwrite jobs from a newer status filter @desktop', async ({ page }) => {
  const old = gate()
  const requested = gate()
  await mockJobs(page, async (route, url) => {
    if (!url.pathname.endsWith('/question-bank-v2/operation-jobs')) return false
    if (url.searchParams.get('status_filter') !== 'running') {
      requested.release()
      await old.promise
      await json(route, { items: [bankJob('Obsolete import')] })
    } else await json(route, { items: [bankJob('Current import')] })
    return true
  })
  try {
    await page.goto('/jobs')
    await requested.promise
    await page.getByLabel('Trạng thái', { exact: true }).selectOption('running')
    await expect(page.getByText('Current import', { exact: true })).toBeVisible()
    const response = page.waitForResponse(r => r.url().includes('/question-bank-v2/operation-jobs?') && !r.url().includes('status_filter'))
    old.release()
    await response
    await page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))))
    await expect(page.getByText('Current import', { exact: true })).toBeVisible()
    await expect(page.getByText('Obsolete import', { exact: true })).not.toBeVisible()
  } finally { old.release() }
})

test('late supplemental responses and errors cannot replace refreshed data @desktop', async ({ page }) => {
  const old = gate()
  const requested = gate()
  let quizCalls = 0
  let analyticsCalls = 0
  await mockJobs(page, async (route, url) => {
    if (url.pathname.endsWith('/course-quiz-instances')) {
      if (++quizCalls === 1) {
        requested.release()
        await old.promise
        await json(route, [{ id: 'old', openedx_course_id: 'course-v1:ObsoleteQuiz', status: 'created', metadata_json: {} }])
      } else await json(route, [{ id: 'new', openedx_course_id: 'course-v1:CurrentQuiz', status: 'created', metadata_json: {} }])
    } else if (url.pathname.endsWith('/analytics/ops/status')) {
      if (++analyticsCalls === 1) {
        await old.promise
        await json(route, { detail: 'Obsolete analytics error' }, 500)
      } else await json(route, { ingest: { last_status: 'running', file_exists: true } })
    } else if (url.pathname.endsWith('/question-bank-v2/operation-jobs')) {
      await json(route, { items: [bankJob('Current import')] })
    } else return false
    return true
  })
  try {
    await page.goto('/jobs')
    await requested.promise
    await page.getByRole('button', { name: 'Tải lại', exact: true }).click()
    await expect(page.getByText('Ingest học online', { exact: true })).toBeVisible()
    await page.getByRole('button', { name: 'Quiz gần đây', exact: true }).click()
    await expect(page.getByText('course-v1:CurrentQuiz', { exact: true })).toBeVisible()
    const response = page.waitForResponse(r => r.url().includes('/analytics/ops/status') && r.status() === 500)
    old.release()
    await response
    await page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))))
    await expect(page.getByText('course-v1:CurrentQuiz', { exact: true })).toBeVisible()
    await expect(page.getByText('course-v1:ObsoleteQuiz', { exact: true })).not.toBeVisible()
    await expect(page.locator('.enterprise-action-message')).not.toBeVisible()
  } finally { old.release() }
})
