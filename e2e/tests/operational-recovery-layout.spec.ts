import { expect, test, type Page } from '@playwright/test'

const courseId = 'course-v1:FPL+MEC129+FA26'

async function mockApp(page: Page, respond: (path: string) => unknown) {
  await page.addInitScript(() => {
    sessionStorage.setItem('ai_openedx_session_token', JSON.stringify({ access_token: 'e2e-token', user_id: '29', role: 'admin' }))
    localStorage.setItem('ai_openedx_role', 'admin')
    localStorage.setItem('ai_openedx_user_id', '29')
  })
  await page.route('http://localhost:8000/api/**', async route => {
    const path = new URL(route.request().url()).pathname
    const body = path.endsWith('/rbac/me')
      ? { user_id: '29', effective_legacy_role: 'admin', is_system_admin: true, business_permissions: ['user.manage_all'], assignments: [] }
      : respond(path) ?? []
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(body) })
  })
}

test('import preview sections retain full height without overlapping @all', async ({ page }) => {
  await mockApp(page, path => path.endsWith('/import-quiz-cms-old/preview') ? {
    preview_token: 'preview-only', can_commit: true, workbook_count: 1, sheet_count: 8,
    question_count: 400, original_question_count: 400, invalid_question_count: 0,
    missing_image_question_count: 0, difficulty_counts: { easy: 320, medium: 80 },
    errors: [], warnings: [], skipped_invalid_questions: [], skipped_invalid_question_count: 0, can_skip_invalid_questions: false,
    target_term: 'SU26', type_counts: { single_select: 400 }, image_count: 0, message: 'Dữ liệu hợp lệ.',
    workbooks: [{ filename: 'MEC129 - Vật liệu cơ khí và Phân tích số.xlsx', subject_code: 'MEC129', subject_name: 'Vật liệu cơ khí và Phân tích số',
      sheet_count: 8, question_count: 400, type_counts: { single_select: 400 }, difficulty_counts: { easy: 320, medium: 80 },
      image_reference_count: 0, embedded_image_count: 0, warning_count: 0, error_count: 0,
      sheets: Array.from({ length: 8 }, (_, i) => ({ sheet_name: `Q${i + 1}`, chapter_no: i + 1, chapter_title: `Bài ${i + 1}`, question_count: 50,
        type_counts: { single_select: 50 }, difficulty_counts: { easy: 40, medium: 10 }, error_count: 0, warning_count: 0 })) }],
  } : undefined)
  await page.goto('/import-quiz-cms-old')
  await page.locator('input[type=file]').first().setInputFiles({ name: 'MEC129.xlsx', mimeType: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', buffer: Buffer.from('mock workbook') })
  await page.getByRole('button', { name: 'Kiểm tra file', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'Đối chiếu môn và bài' })).toBeVisible()
  const sections = await page.locator('main > .workspace-section, main > div:has(> .workspace-section)').evaluateAll(nodes => nodes.map(node => {
    const r = node.getBoundingClientRect()
    return { top: r.top, bottom: r.bottom, height: r.height }
  }))
  expect(sections.length).toBeGreaterThanOrEqual(4)
  for (let i = 1; i < sections.length; i++) expect(sections[i].top).toBeGreaterThan(sections[i - 1].bottom)
  // Content, not just card borders, must fit before the following section.
  const review = page.locator('.workspace-section').filter({ has: page.getByRole('heading', { name: 'Đối chiếu môn và bài' }) })
  const table = await review.locator('table').boundingBox()
  const card = await review.boundingBox()
  expect(table!.y + table!.height).toBeLessThanOrEqual(card!.y + card!.height)
  await page.getByRole('button', { name: 'Import vào SU26', exact: true }).scrollIntoViewIfNeeded()
  await expect(page.getByRole('button', { name: 'Import vào SU26', exact: true })).toBeInViewport()
  const overflow = await page.locator('main').evaluate(el => el.scrollWidth > el.clientWidth + 1)
  expect(overflow).toBe(false)
})

test('progress reminder scroll reaches the message and keeps footer accessible @all', async ({ page }) => {
  await mockApp(page, path => {
    if (path.endsWith('/classes/class-1')) return { id: 'class-1', class_code: 'HM21301', class_name: 'HM21301', campus_code: 'hn', subject_code: 'ACC1061', openedx_course_id: courseId, learning_platform: 'cms' }
    if (path.endsWith('/mapping-summary')) return { total_students: 25, mapped_students: 25, unmapped_students: 0 }
    if (path.endsWith('/learning-summary')) return { openedx_course_id: courseId, component_summaries: [] }
    if (path.endsWith('/students')) return { items: [], total: 0, page: 1, page_size: 50 }
    if (path.endsWith('/progress-email/preview')) return { mail_configured: true, roster_total: 25, candidate_count: 0, deliverable_count: 0,
      missing_email_count: 0, inactive_student_count: 0, max_recipients: 1000, recipients: [],
      default_subject: 'Nhắc tiến độ học tập', default_body_template: 'Xin chào {{maHs}},\nHãy hoàn thành các Quiz còn chậm tiến độ.' }
    return undefined
  })
  await page.goto('/student-management/classes/class-1?platform=cms')
  await page.getByRole('button', { name: 'Gửi nhắc tiến độ', exact: true }).click()
  const dialog = page.getByRole('dialog', { name: 'Gửi nhắc sinh viên chậm tiến độ' })
  const body = dialog.locator('.accessible-dialog-body')
  const textarea = dialog.getByLabel('Nội dung', { exact: true })
  await expect(textarea).toBeVisible()
  expect(await body.evaluate(el => el.scrollHeight - el.clientHeight)).toBeGreaterThan(0)
  await body.evaluate(el => { el.scrollTop = el.scrollHeight })
  await expect(textarea).toBeInViewport()
  const compose = await dialog.locator('.progress-email-compose').boundingBox()
  const area = await textarea.boundingBox()
  expect(area!.y + area!.height).toBeLessThanOrEqual(compose!.y + compose!.height)
  await expect(dialog.getByRole('button', { name: 'Hủy', exact: true })).toBeInViewport()
  await textarea.fill('Nội dung đã chỉnh sửa')
  await expect(textarea).toHaveValue('Nội dung đã chỉnh sửa')
  await dialog.getByRole('button', { name: 'Hủy', exact: true }).click()
  await expect(dialog).not.toBeVisible()
  await expect(page.locator('html')).not.toHaveAttribute('data-dialog-open', 'true')
})

test('failed final recovery stays actionable and feedback is visible when scrolled @all', async ({ page }) => {
  let status = 'rollback_manual_required'
  let attempts = 0
  const mappings = Array.from({ length: 9 }, (_, i) => ({ chapter_id: `chapter-${i}`, chapter_title: i === 8 ? 'Final test' : `Bài ${i + 1}`,
    action: i === 8 ? 'final_test' : 'quiz', ready: true, can_create: true, requires_quiz: true, release_id: 'release-1', release_code: 'MEC129-1',
    openedx_section_id: `section-${i}`, openedx_section_title: i === 8 ? 'Final test' : `Bài ${i + 1}`, course_chapter_mapping_id: `map-${i}`,
    source_release_ids: ['release-1'], status_label: 'Sẵn sàng', missing_requirements: [] }))
  await mockApp(page, path => {
    if (path.includes('/quiz/auto-map/')) return { ok: true, mode: path.endsWith('/apply') ? 'applied' : 'preview',
      openedx_course_id: courseId, offering: { id: 'offering', code: 'MEC129_SU26' }, mappings, warnings: [],
      summary: { matched_count: 9, chapter_count: 9, candidates: [{ offering_id: 'offering', offering_code: 'MEC129_SU26', ready_chapter_count: 9, chapter_count: 9 }] } }
    if (path.endsWith('/course-quiz-instances')) return mappings.map((item, i) => ({ id: `quiz-${i}`, openedx_course_id: courseId,
      chapter_id: item.chapter_id, bank_release_id: 'release-1', status: i === 8 ? status : 'created', created_at: '2026-09-06T06:52:31Z',
      metadata_json: { assessment_type: i === 8 ? 'final_test' : 'quiz', quiz_title: item.chapter_title } }))
    if (path.endsWith('/quiz-8/rollback')) {
      attempts++
      if (attempts === 1) return { ok: false, status, manual_cleanup_required: true, message: 'Chưa xác nhận được việc xóa bài kiểm tra trên CMS.' }
      status = 'rolled_back'
      return { ok: true, status, manual_cleanup_required: false, message: 'Đã xóa phần bài kiểm tra trên CMS. Bạn có thể tạo lại.' }
    }
    return undefined
  })
  await page.goto('/bank/quiz')
  await page.getByLabel('Khóa học ID', { exact: true }).fill(courseId)
  await page.getByRole('button', { name: 'Kiểm tra map', exact: true }).click()
  await page.getByRole('button', { name: 'Lưu cấu hình', exact: true }).first().click()
  const recover = page.getByRole('button', { name: 'Kiểm tra và khôi phục', exact: true }).last()
  await recover.click()
  const toast = page.getByRole('region', { name: 'Thông báo hệ thống' })
  await expect(toast.getByText('Chưa xác nhận được việc xóa bài kiểm tra trên CMS.', { exact: true })).toBeInViewport()
  await expect(page.getByRole('button', { name: 'Kiểm tra và khôi phục', exact: true }).first()).toBeEnabled()
  await recover.click()
  await expect(toast.getByText('Đã xóa phần bài kiểm tra trên CMS. Bạn có thể tạo lại.', { exact: true })).toBeInViewport()
  await expect(page.getByRole('button', { name: 'Tạo Final', exact: true })).toBeEnabled()
  await expect(page.getByRole('button', { name: 'Đã có Final test', exact: true })).toHaveCount(0)
})
