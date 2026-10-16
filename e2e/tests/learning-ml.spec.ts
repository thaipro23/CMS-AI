import { expect, test } from '@playwright/test'
const row = { username: 'sv-ml', class_id: 'class-ml', course_id: 'course', classification: 'NORMAL',
  confidence_score: 80, real_learning_score: 60, idle_score: 0, suspicious_score: 0,
  human_readable_summary: 'Tóm tắt từ luật không thay đổi', reason_codes: [] }
const ml = { family: 'video', status: 'SCORED', reference_count: 55, outlier: true,
  anomaly_score: .65, reference_percentile: 95, calculated_at: '2026-10-16T08:00:00', reason_codes: [],
  deviations: [{ feature: 'watch_ratio', value: .2, reference_median: .8, difference: -.6 }] }
for (const status of ['SCORED', 'INSUFFICIENT_DATA', 'ERROR', 'DISABLED'] as const) {
  test(`learning ML drawer ${status} keeps rule evidence @desktop`, async ({ page }) => {
    const errors: string[] = []
    page.on('pageerror', error => errors.push(error.message))
    await page.addInitScript(() => {
      localStorage.setItem('ai_openedx_role', 'admin')
      localStorage.setItem('ai_openedx_user_id', 'e2e-admin')
      sessionStorage.setItem('ai_openedx_session_token', JSON.stringify({ access_token: 'e2e-token', user_id: 'e2e-admin', role: 'admin' }))
    })
    const analysis = { ...ml, status, outlier: status === 'SCORED' ? true : null,
      reference_percentile: status === 'SCORED' ? 95 : null,
      reason_codes: status === 'INSUFFICIENT_DATA' ? ['BASELINE_TOO_SMALL'] : [],
      deviations: status === 'SCORED' ? ml.deviations : [] }
    await page.route('http://localhost:8000/api/**', async route => {
      const path = new URL(route.request().url()).pathname
      let data: unknown = []
      if (path === '/api/rbac/me') data = { user_id: 'e2e-admin', effective_legacy_role: 'admin', is_system_admin: true, business_permissions: [], assignments: [] }
      else if (path === '/api/academic/terms') data = [{ id: 'term-ml', term_name: 'Fall 2026', active: true }]
      else if (path.endsWith('/teacher/subjects')) data = { items: [{ id: 'subject-ml', subject_code: 'SUB', subject_name: 'Môn thử', learning_platform: 'cms' }], total: 1, total_pages: 1 }
      else if (path.includes('/classes/learning-behavior/overview')) data = { items: [{ class_id: 'class-ml', class_code: 'ML01', student_count: 1, openedx_course_id: 'course' }], total: 1 }
      else if (path.endsWith('/workspace')) data = { rows: { items: [row], total: 1 }, summary: { roster_count: 1, normal_count: 1 } }
      else if (path.includes('/students/sv-ml/learning-behavior')) data = { behavior: { ...row, ml: analysis }, sessions: [], videos: [] }
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(data) })
    })
    await page.goto('/analytics/learning?step=results&branch=poly&term_id=term-ml&subject_id=subject-ml&class_id=class-ml')
    await page.getByRole('button', { name: 'Xem lý do kết quả của sv-ml' }).click()
    const dialog = page.getByRole('dialog', { name: 'Lý do ra kết quả' })
    await expect(dialog.getByText(row.human_readable_summary, { exact: true })).toBeVisible()
    const card = dialog.getByRole('region', { name: 'Phân tích học máy video' })
    if (status === 'DISABLED') await expect(card).toHaveCount(0)
    else {
      await expect(card).toBeVisible()
      if (status === 'SCORED') {
        await expect(card.getByText('Khác biệt so với nhóm tham chiếu', { exact: true })).toBeVisible()
        await expect(card.getByText('95.0/100')).toBeVisible()
        await expect(card.getByText('20.0%', { exact: true })).toBeVisible()
      } else if (status === 'INSUFFICIENT_DATA') await expect(card.getByText('Chưa đủ sinh viên có dữ liệu tương đương để đối chiếu.')).toBeVisible()
      else await expect(card.getByText('Chưa tính được kết quả', { exact: true })).toBeVisible()
    }
    expect(errors).toEqual([])
  })
}
