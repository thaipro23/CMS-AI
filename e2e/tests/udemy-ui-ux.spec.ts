import { expect, test, type Page, type Route } from '@playwright/test'

const deliveryId = 'delivery-sof3032-su26-b2-poly'

const dashboardPayload = {
  delivery: {
    id: deliveryId,
    subject_id: 'subject-sof3032',
    subject_code: 'SOF3032',
    subject_name: 'Quản trị dự án phần mềm',
    term_id: 'term-su26',
    term_name: 'Summer 2026',
    block_id: 'block-2',
    block_name: 'Block 2',
    branch: 'poly',
    learning_platform: 'udemy',
  },
  summary: {
    subject_delivery_id: deliveryId,
    total_students: 2,
    matched_students: 2,
    outside_roster_students: 0,
    ambiguous_students: 0,
    unmatched_students: 0,
    late_students: 1,
    on_track_students: 1,
    no_plan_students: 0,
    average_progress_percent: 61,
    required_progress_percent: 60,
    current_plan_week: 4,
    current_deadline_date: '2026-08-10',
    last_imported_at: '2026-08-06T06:30:00Z',
    class_count: 1,
    scope_label: 'Toàn bộ delivery',
  },
  active_plan: {
    id: 'plan-sof3032-v2',
    version: 2,
    item_count: 120,
    source: 'manual',
    imported_at: '2026-08-01T03:00:00Z',
  },
  classes: [{ id: 'class-sof3032-01', class_code: 'SOF3032.01', class_name: 'SOF3032.01', campus: 'ph' }],
  recent_imports: [{
    id: 'batch-import-1',
    parent_job_id: 'job-import-previous',
    subject_delivery_id: deliveryId,
    subject_code: 'SOF3032',
    file_name: 'SOF3032_progress.xlsx',
    file_sha256: 'a'.repeat(64),
    parser_format: 'aggregate_7_columns',
    status: 'completed',
    force_reimport: false,
    total_rows: 2,
    processed_rows: 2,
    matched_rows: 2,
    outside_roster_rows: 0,
    unmatched_rows: 0,
    ambiguous_rows: 0,
    failed_rows: 0,
    requested_by: 'e2e-admin',
    result_json: {},
    error_report_available: false,
    started_at: '2026-08-06T06:29:00Z',
    finished_at: '2026-08-06T06:30:00Z',
    created_at: '2026-08-06T06:28:00Z',
    updated_at: '2026-08-06T06:30:00Z',
  }],
}

const students = [
  {
    id: 'progress-1',
    student_id: 'student-1',
    student_code: 'PH00001',
    student_username: 'PH00001',
    display_name: 'Nguyễn Văn Đạt',
    email: 'datnv@fpt.edu.vn',
    class_id: 'class-sof3032-01',
    class_code: 'SOF3032.01',
    class_name: 'SOF3032.01',
    campus: 'ph',
    teacher_names: ['Giảng viên A'],
    progress_percent: 72,
    required_progress_percent: 60,
    variance_percent: 12,
    is_late: false,
    status: 'on_track',
    status_label: 'Đạt tiến độ',
    match_status: 'matched_roster',
    current_plan_week: 4,
    current_deadline_date: '2026-08-10',
    last_import_batch_id: 'batch-import-1',
    source_format: 'aggregate_7_columns',
    last_imported_at: '2026-08-06T06:30:00Z',
    diagnostic: null,
  },
  {
    id: 'progress-2',
    student_id: 'student-2',
    student_code: 'PH00002',
    student_username: 'PH00002',
    display_name: 'Trần Văn Chậm',
    email: 'chamtv@fpt.edu.vn',
    class_id: 'class-sof3032-01',
    class_code: 'SOF3032.01',
    class_name: 'SOF3032.01',
    campus: 'ph',
    teacher_names: ['Giảng viên A'],
    progress_percent: 50,
    required_progress_percent: 60,
    variance_percent: -10,
    is_late: true,
    status: 'late',
    status_label: 'Chậm tiến độ',
    match_status: 'matched_roster',
    current_plan_week: 4,
    current_deadline_date: '2026-08-10',
    last_import_batch_id: 'batch-import-1',
    source_format: 'aggregate_7_columns',
    last_imported_at: '2026-08-06T06:30:00Z',
    diagnostic: 'Tiến độ thấp hơn mốc hiện tại 10%.',
  },
]

function runningJob(id: string, jobType: string) {
  return {
    id,
    job_type: jobType,
    status: 'running',
    requested_by: 'e2e-admin',
    progress_current: 35,
    progress_total: 100,
    progress_label: jobType.includes('import') ? 'Đang xử lý file tiến độ' : 'Đang tạo báo cáo Excel',
    request_json: { delivery_id: deliveryId },
    result_json: {},
    error_message: null,
    created_at: '2026-08-06T06:30:00Z',
    started_at: '2026-08-06T06:30:05Z',
    finished_at: null,
    updated_at: '2026-08-06T06:30:10Z',
  }
}

async function fulfillJson(route: Route, body: unknown, status = 200) {
  await route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) })
}

async function mockUdemyApp(page: Page, onStudentRequest?: (url: URL) => void) {
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
      await fulfillJson(route, {
        user_id: 'e2e-admin',
        effective_legacy_role: 'admin',
        is_system_admin: true,
        business_permissions: ['user.manage_all'],
        assignments: [],
      })
      return
    }
    if (url.pathname === `/api/academic/subject-deliveries/${deliveryId}/udemy-progress/dashboard`) {
      await fulfillJson(route, dashboardPayload)
      return
    }
    if (url.pathname === `/api/academic/subject-deliveries/${deliveryId}/udemy-progress/students`) {
      onStudentRequest?.(url)
      const status = url.searchParams.get('status')
      const items = status === 'alerts' || status === 'late' ? students.filter((item) => item.status === 'late') : students
      await fulfillJson(route, {
        items,
        total: items.length,
        page: 1,
        page_size: 50,
        total_pages: 1,
        has_next: false,
      })
      return
    }
    if (url.pathname.startsWith('/api/academic/bulk-operation-jobs/')) {
      const jobId = url.pathname.split('/').pop() || ''
      const type = jobId.includes('import') ? 'udemy_progress_import' : 'udemy_progress_export'
      await fulfillJson(route, runningJob(jobId, type))
      return
    }
    if (url.pathname === `/api/academic/subject-deliveries/${deliveryId}/udemy-progress/export-jobs` && route.request().method() === 'POST') {
      await fulfillJson(route, runningJob('job-export-new', 'udemy_progress_export'), 202)
      return
    }
    if (url.pathname === '/api/academic/udemy/progress/import/jobs' && route.request().method() === 'POST') {
      await fulfillJson(route, {
        ok: true,
        message: 'Đã xếp hàng import tiến độ Udemy.',
        job_id: 'job-import-new',
        status: 'queued',
        queued_count: 1,
        duplicate_count: 0,
        batches: [],
      }, 202)
      return
    }
    await fulfillJson(route, [])
  })
}

function luminance(rgb: string) {
  const values = rgb.match(/[\d.]+/g)?.slice(0, 3).map(Number) || [0, 0, 0]
  const channels = values.map((value) => {
    const normalized = value / 255
    return normalized <= 0.03928 ? normalized / 12.92 : ((normalized + 0.055) / 1.055) ** 2.4
  })
  return 0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2]
}

function contrastRatio(foreground: string, background: string) {
  const light = Math.max(luminance(foreground), luminance(background))
  const dark = Math.min(luminance(foreground), luminance(background))
  return (light + 0.05) / (dark + 0.05)
}

test.describe('Udemy Batch 35.1 UI/UX contract', () => {
  test('tabs, alert semantics and primary action contrast are correct @desktop', async ({ page }) => {
    const studentRequests: URL[] = []
    await mockUdemyApp(page, (url) => studentRequests.push(new URL(url.toString())))
    await page.goto(`/subject-management/${deliveryId}/udemy`)

    await expect(page.getByRole('heading', { level: 1, name: /SOF3032 · Tiến độ Udemy/ })).toBeVisible()
    const importButton = page.getByRole('button', { name: 'Import điểm Udemy' })
    await expect(importButton).toBeVisible()
    await expect(importButton).not.toHaveClass(/udemy-action/)
    const actionColors = await importButton.evaluate((element) => {
      const style = getComputedStyle(element)
      return { foreground: style.color, background: style.backgroundColor }
    })
    expect(contrastRatio(actionColors.foreground, actionColors.background)).toBeGreaterThanOrEqual(4.5)

    const overviewTab = page.getByRole('tab', { name: 'Tổng quan' })
    await expect(overviewTab).toHaveAttribute('aria-controls', 'udemy-progress-panel-overview')
    await expect(page.getByRole('tabpanel', { name: 'Tổng quan' })).toBeVisible()
    await overviewTab.focus()
    await page.keyboard.press('ArrowRight')
    await expect(page.getByRole('tab', { name: /Tiến độ sinh viên/ })).toBeFocused()

    await page.getByRole('combobox', { name: 'Trạng thái' }).selectOption('on_track')
    await page.getByRole('tab', { name: /Cảnh báo/ }).click()
    const alertStatus = page.getByRole('combobox', { name: 'Trạng thái' })
    await expect(alertStatus).toHaveValue('all')
    await expect(alertStatus.locator('option[value="on_track"]')).toHaveCount(0)
    await expect(page.getByText('Trần Văn Chậm', { exact: true })).toBeVisible()
    await expect(page.getByText('Nguyễn Văn Đạt', { exact: true })).toHaveCount(0)
    expect(studentRequests.some((url) => url.searchParams.get('status') === 'alerts')).toBeTruthy()

    const progress = page.getByRole('progressbar', { name: 'Tiến độ của Trần Văn Chậm' })
    await expect(progress).toHaveAttribute('aria-valuenow', '50')
  })

  test('import/export jobs resume after reload without exposing duplicate actions @desktop', async ({ page }) => {
    await mockUdemyApp(page)
    await page.addInitScript(({ delivery }) => {
      localStorage.setItem(`ai-server:udemy-import-job:${delivery}`, 'job-import-resume')
      localStorage.setItem(`ai-server:udemy-export-job:${delivery}`, 'job-export-resume')
    }, { delivery: deliveryId })
    await page.goto(`/subject-management/${deliveryId}/udemy`)

    await expect(page.getByText('Import tiến độ Udemy', { exact: true })).toBeVisible()
    await expect(page.getByText('Xuất báo cáo Udemy', { exact: true })).toBeVisible()
    await expect(page.getByRole('button', { name: /Đang xuất/ })).toBeDisabled()
    await expect(page.getByRole('button', { name: 'Import điểm Udemy' })).toBeDisabled()
    await expect(page.getByText(/Job tiếp tục chạy kể cả khi F5/)).toBeVisible()
  })

  test('required responsive widths keep overflow inside table viewport @desktop', async ({ page }) => {
    await mockUdemyApp(page)
    const viewports = [
      { width: 1440, height: 960 },
      { width: 1366, height: 900 },
      { width: 1024, height: 768 },
      { width: 768, height: 900 },
      { width: 390, height: 844 },
    ]

    for (const viewport of viewports) {
      await page.setViewportSize(viewport)
      await page.goto(`/subject-management/${deliveryId}/udemy`)
      await page.getByRole('tab', { name: /Tiến độ sinh viên/ }).click()
      await expect(page.getByRole('heading', { level: 2, name: 'Tiến độ sinh viên Udemy' })).toBeVisible()
      const layout = await page.evaluate(() => {
        const viewportElement = document.querySelector('.enterprise-table-scroll') as HTMLElement | null
        return {
          pageOverflow: document.documentElement.scrollWidth - document.documentElement.clientWidth,
          tableClientWidth: viewportElement?.clientWidth || 0,
          tableScrollWidth: viewportElement?.scrollWidth || 0,
        }
      })
      expect(layout.pageOverflow, `page overflow at ${viewport.width}px`).toBeLessThanOrEqual(1)
      if (viewport.width <= 768) expect(layout.tableScrollWidth).toBeGreaterThan(layout.tableClientWidth)
    }
  })

  test('mobile import dialog uses clear wording and accessible full-screen behavior @mobile', async ({ page }) => {
    await mockUdemyApp(page)
    await page.goto(`/subject-management/${deliveryId}/udemy`)
    await page.getByRole('button', { name: 'Import điểm Udemy' }).click()
    const dialog = page.getByRole('dialog', { name: /Import tiến độ Udemy/ })
    await expect(dialog).toBeVisible()
    await expect(dialog).toContainText('file tổng hợp tiến độ 7 cột')
    await expect(dialog).not.toContainText('file tổng hợp ACMS')
    await page.getByLabel('File Excel tiến độ').setInputFiles({
      name: 'SOF3032_progress.xlsx',
      mimeType: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
      buffer: Buffer.from('PK\u0003\u0004mock-xlsx'),
    })
    await page.getByRole('button', { name: 'Bắt đầu import' }).click()
    await expect(dialog).toBeVisible()
    await expect(dialog).toContainText('Đã xếp hàng import')
    await page.keyboard.press('Escape')
    await expect(dialog).toBeHidden()
  })
})
