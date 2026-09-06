import { expect, test, type Page, type Route } from '@playwright/test'

const termId = 'term-su26'
const delivery1 = 'delivery-sof3032-b1'
const delivery2 = 'delivery-sof3032-b2'

async function fulfillJson(route: Route, body: unknown, status = 200) {
  await route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) })
}

async function mockSubjectManagement(page: Page, onBulkUpdate?: (body: any) => void) {
  await page.addInitScript(() => {
    localStorage.setItem('ai_openedx_role', 'admin')
    localStorage.setItem('ai_openedx_user_id', 'e2e-admin')
    sessionStorage.setItem('ai_openedx_session_token', JSON.stringify({ access_token: 'e2e-token', user_id: 'e2e-admin', role: 'admin' }))
  })

  await page.route('http://localhost:8000/api/**', async (route) => {
    const url = new URL(route.request().url())
    if (url.pathname === '/api/rbac/me') {
      await fulfillJson(route, { user_id: 'e2e-admin', effective_legacy_role: 'admin', is_system_admin: true, business_permissions: ['user.manage_all'], assignments: [] })
      return
    }
    if (url.pathname === '/api/academic/terms') {
      await fulfillJson(route, [{ id: termId, term_code: 'SU26', term_name: 'Summer 2026', branch: 'poly', active: true }])
      return
    }
    if (url.pathname === '/api/academic/subject-deliveries' && route.request().method() === 'GET') {
      expect(url.searchParams.get('management_scope')).toBe('term')
      expect(url.searchParams.has('block_id')).toBeFalsy()
      await fulfillJson(route, {
        items: [{
          id: delivery1,
          subject_id: 'subject-sof3032',
          subject_code: 'SOF3032',
          subject_name: 'Java nâng cao',
          term_id: termId,
          term_name: 'Summer 2026',
          block_id: 'block-1',
          block_name: 'Block 1, Block 2',
          branch: 'poly',
          learning_platform: null,
          active: true,
          configuration_source: 'term_management',
          class_count: 4,
          campus_count: 1,
          has_udemy_plan: true,
          delivery_ids: [delivery1, delivery2],
          block_count: 2,
          block_names: ['Block 1', 'Block 2'],
          platform_consistent: false,
          platform_values: ['cms', 'udemy'],
          management_scope: 'term',
          block_deliveries: [
            { id: delivery1, block_id: 'block-1', block_name: 'Block 1', learning_platform: 'cms', class_count: 2, campus_count: 1, has_udemy_plan: false },
            { id: delivery2, block_id: 'block-2', block_name: 'Block 2', learning_platform: 'udemy', class_count: 2, campus_count: 1, has_udemy_plan: true, udemy_plan_version: 1 },
          ],
        }],
        total: 1,
        page: 1,
        page_size: 50,
        total_pages: 1,
        has_next: false,
        summary: { total: 1, cms_count: 0, udemy_count: 0, unassigned_count: 0, mixed_count: 1, class_count: 4, scope_label: 'Theo học kỳ' },
      })
      return
    }
    if (url.pathname === '/api/academic/bulk-operation-jobs') {
      await fulfillJson(route, [])
      return
    }
    if (url.pathname === '/api/academic/subject-deliveries/platform/bulk' && route.request().method() === 'POST') {
      const body = route.request().postDataJSON()
      onBulkUpdate?.(body)
      await fulfillJson(route, { ok: true, message: 'Đã cập nhật.', updated: 2, items: [] })
      return
    }
    await fulfillJson(route, [])
  })
}

test.describe('Subject Management Batch 35.2 term scope', () => {
  test('manages platform once per term and keeps Block operations visible', async ({ page }) => {
    let bulkBody: any = null
    await mockSubjectManagement(page, (body) => { bulkBody = body })
    await page.goto('/subject-management')

    await expect(page.getByRole('heading', { level: 1, name: 'Quản lý môn học' })).toBeVisible()
    await expect(page.getByText(/Kỳ mới kế thừa lựa chọn CMS\/Udemy nhất quán/)).toHaveCount(0)
    await expect(page.getByRole('combobox', { name: 'Block' })).toHaveCount(0)
    await expect(page.getByText('Khác nhau giữa các Block')).toBeVisible()
    await expect(page.getByText('2 Block', { exact: true })).toBeVisible()

    await page.getByRole('radio', { name: 'Udemy' }).click()
    await expect.poll(() => bulkBody).not.toBeNull()
    expect(bulkBody.delivery_ids).toEqual([delivery1, delivery2])
    expect(bulkBody.learning_platform).toBe('udemy')

    await page.getByText('2 Block · mở chi tiết').click()
    await expect(page.getByRole('link', { name: 'Xem tiến độ' })).toHaveAttribute('href', `/subject-management/${delivery2}/udemy`)
  })

  test('mobile layout does not introduce page-level horizontal overflow', async ({ page }) => {
    await mockSubjectManagement(page)
    await page.setViewportSize({ width: 390, height: 844 })
    await page.goto('/subject-management')
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)
    expect(overflow).toBeLessThanOrEqual(1)
  })
})
