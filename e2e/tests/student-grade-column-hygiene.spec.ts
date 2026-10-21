import { expect, test, type Page } from '@playwright/test'

import {
  canonicalAssessmentColumns,
  canonicalAssessmentIdentity,
} from '../../frontend/lib/academicAssessments'


async function mockAcademicClass(page: Page, readinessCases = false) {
  const structuralRows = [
    { key: 'demo-a', name: 'Demo', category: 'quiz', quiz_number: 2, planned: true },
    { key: 'demo-b', name: 'Demo', category: 'subsection', percent: 90 },
    ...Array.from({ length: 16 }, (_, index) => ({
      key: `part-${index + 1}`,
      name: `Phần ${(index % 4) + 1}`,
      percent: 100,
    })),
  ]
  const components = [
    { key: 'quiz-one', name: 'Quiz 1', percent: 80 },
    ...structuralRows,
    { key: 'final', name: 'Final test', assessment_type: 'final_test', percent: 70 },
  ]
  await page.addInitScript(() => {
    sessionStorage.setItem('ai_openedx_session_token', JSON.stringify({ access_token: 'e2e-token', user_id: '29', role: 'admin' }))
    localStorage.setItem('ai_openedx_role', 'admin')
    localStorage.setItem('ai_openedx_user_id', '29')
  })
  await page.route('http://localhost:8000/api/**', async (route) => {
    const path = new URL(route.request().url()).pathname
    let body: unknown = []
    if (path.endsWith('/rbac/me')) {
      body = { user_id: '29', effective_legacy_role: 'admin', is_system_admin: true, business_permissions: ['user.manage_all'], assignments: [] }
    } else if (path.endsWith('/classes/class-1')) {
      body = { id: 'class-1', class_code: 'DOM1021.01', class_name: 'DOM1021.01', branch: 'poly', campus: 'hn', learning_platform: 'cms' }
    } else if (path.endsWith('/mapping-summary')) {
      body = { total: 1, counts: { matched: 1 } }
    } else if (path.endsWith('/learning-summary')) {
      body = { openedx_course_id: 'course-v1:FPL+DOM1021+FA26', component_summaries: components, counts: { matched: 1 } }
    } else if (path.endsWith('/students')) {
      body = {
        items: readinessCases ? [
          { id: 'incomplete', username: 'PH00002', student_code: 'PH00002', full_name: 'Chưa đủ Quiz',
            match_status: 'matched', learning_enrollment_status: 'enrolled', learning_status: 'good',
            learning_progress_percent: 100, learning_grade_percent: 99.99,
            exam_status: 'eligible', exam_eligible: true, exam_status_label: 'Chưa bị cấm thi',
            training_policy: { quiz_total: 8, all_quizzes_eligible: false } },
          { id: 'ready', username: 'PH00003', student_code: 'PH00003', full_name: 'Đủ điểm Quiz',
            match_status: 'matched', learning_enrollment_status: 'enrolled', learning_status: 'in_progress',
            learning_progress_percent: 98, learning_grade_percent: 90,
            exam_status: 'eligible', exam_eligible: true,
            training_policy: { quiz_total: 8, all_quizzes_eligible: true } },
          { id: 'missing', username: 'PH00004', student_code: 'PH00004', full_name: 'Thiếu dữ liệu',
            learning_progress_percent: null, learning_grade_percent: null, exam_status: 'insufficient_data' },
        ] : [{
          id: 'student-1', student_code: 'PH00001', username: 'ph00001', full_name: 'Sinh viên Một',
          match_status: 'matched', learning_enrollment_status: 'enrolled', learning_status: 'in_progress',
          learning_component_scores: components,
        }],
        total: readinessCases ? 3 : 1,
        page: 1,
        page_size: 50,
      }
    }
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(body) })
  })
}


test('student table renders only canonical dynamic assessment headers @all', async ({ page }) => {
  await mockAcademicClass(page)
  await page.goto('/student-management/classes/class-1?platform=cms')

  await expect(page.getByRole('columnheader', { name: 'Quiz 1', exact: true })).toHaveCount(1)
  await expect(page.getByRole('columnheader', { name: 'Final test', exact: true })).toHaveCount(1)
  await expect(page.getByRole('columnheader', { name: /^Demo/ })).toHaveCount(0)
  await expect(page.getByRole('columnheader', { name: /^Phần [1-4]$/ })).toHaveCount(0)
})


test('dynamic grade columns contain only Quiz N and Final test @all', () => {
  const columns = canonicalAssessmentColumns([
    { key: 'quiz-real', name: 'Quiz 1', percent: 80 },
    { key: 'demo', name: 'Demo', category: 'quiz', quiz_number: 2, planned: true },
    { key: 'demo-lesson', name: 'Demo bài 1', percent: 100 },
    { key: 'part-1', name: 'Phần 1', percent: 90 },
    { key: 'final', name: 'Final test', percent: 70 },
  ])

  expect(columns.map(({ key, name }) => ({ key, name }))).toEqual([
    { key: 'quiz:1', name: 'Quiz 1' },
    { key: 'final_test', name: 'Final test' },
  ])
})


test('explicit assessment contract is accepted but positional metadata alone is rejected @all', () => {
  expect(canonicalAssessmentIdentity({
    key: 'opaque',
    name: 'Checkpoint',
    assessment_type: 'quiz',
    quiz_number: 4,
  })).toBe('quiz:4')
  expect(canonicalAssessmentIdentity({
    key: 'opaque-demo',
    name: 'Demo',
    category: 'quiz',
    quiz_number: 4,
  })).toBeNull()
  expect(canonicalAssessmentIdentity({
    key: 'block@quiz-12-random',
    name: 'Demo',
  })).toBeNull()
})


test('duplicate quiz labels collapse and retain deadline metadata @all', () => {
  const columns = canonicalAssessmentColumns([
    { key: 'outline', name: 'Quiz 2', planned: true, deadline_date: '2026-10-10' },
    { key: 'score', name: 'Learning Check 2', percent: 95 },
  ])

  expect(columns).toEqual([
    expect.objectContaining({
      key: 'quiz:2',
      name: 'Quiz 2',
      quizNumber: 2,
      deadlineDate: '2026-10-10',
    }),
  ])
})


test('progress distinguishes completion from exam readiness with equally prominent total grade @all', async ({ page }) => {
  await mockAcademicClass(page, true)
  await page.goto('/student-management/classes/class-1?platform=cms')
  const incomplete = page.getByRole('row').filter({ hasText: 'PH00002' })
  const ready = page.getByRole('row').filter({ hasText: 'PH00003' })
  const missing = page.getByRole('row').filter({ hasText: 'PH00004' })
  await expect(incomplete.getByText('Xem video và Quiz: 100%', { exact: true })).toBeVisible()
  // Rounded 10/10 is still not proof that every Quiz is 100%.
  await expect(incomplete.getByText('Điểm tổng: 10/10', { exact: true })).toBeVisible()
  await expect(incomplete.getByText('Chưa đủ điều kiện thi', { exact: true })).toHaveCount(2)
  await expect(incomplete.getByText('Đủ điều kiện thi', { exact: true })).toHaveCount(0)
  await expect(ready.getByText('Đủ điều kiện thi', { exact: true })).toHaveCount(2)
  await expect(missing.getByText('Chưa đủ điều kiện thi', { exact: true })).toHaveCount(2)
  await expect(missing.getByText('Điểm tổng: N/A', { exact: true })).toBeVisible()
  const progress = incomplete.locator('.learning-progress-cell')
  const typography = await progress.locator(':scope > b').evaluateAll(nodes => nodes.map(node => {
    const style = getComputedStyle(node)
    const bounds = node.getBoundingClientRect()
    return { size: style.fontSize, weight: style.fontWeight, top: bounds.top, bottom: bounds.bottom }
  }))
  expect(typography).toHaveLength(2)
  expect(typography[0].size).toEqual(typography[1].size)
  expect(typography[0].weight).toEqual(typography[1].weight)
  expect(typography[1].top).toBeGreaterThanOrEqual(typography[0].bottom)
  expect(Number(typography[1].weight)).toBeGreaterThanOrEqual(700)
  await expect(progress.getByText('Điểm thấp', { exact: true })).toHaveCount(0)
  await progress.scrollIntoViewIfNeeded()
  await page.screenshot({ path: test.info().outputPath('student-exam-readiness.png'), fullPage: true })
})
