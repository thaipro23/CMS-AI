'use client'

import { useEffect, useMemo, useState } from 'react'
import { PageHeader, PageRoot } from '../../../../components/layout/PageHeader'
import { VisualIcon } from '../../../../components/ui/VisualIcon'
import { OperationsKpiStrip } from '../../../../components/operations/OperationsWorkspace'
import { EnterpriseDataTable, type EnterpriseTableColumn } from '../../../../components/table/EnterpriseDataTable'
import { useUrlTableState } from '../../../../hooks/useUrlTableState'
import { formatVNDateTime } from '../../../../lib/time'
import { getBankReleases, getCourseQuizInstances, rollbackCourseQuizInstance } from '../../../../lib/api'
import type { BankRelease, CourseQuizInstance } from '../../../../types'
import { useBankData, useAsyncMessage, statusClass, statusLabel } from '../shared'
import { BankPageIdentity, BankSection } from '../BankDesignContract'

function dateText(value?: string | null) {
  try { return value ? formatVNDateTime(value) : '—' } catch { return value || '—' }
}

function releaseTitle(item: BankRelease) {
  return item.release_code || item.title || item.id
}

export function BankHistoryPage() {
  const { headers, can } = useBankData()
  const { message, busy, run } = useAsyncMessage()
  const { state, update } = useUrlTableState({ status: 'all', sort: 'quiz', pageSize: 20, density: 'compact' })
  const [quizHistory, setQuizHistory] = useState<CourseQuizInstance[]>([])
  const [releases, setReleases] = useState<BankRelease[]>([])
  const [loading, setLoading] = useState(true)
  const activeView = state.sort === 'release' ? 'release' : 'quiz'

  const load = async () => {
    setLoading(true)
    try {
      const [quizRows, releaseRows] = await Promise.all([
        getCourseQuizInstances(headers, { limit: 100 }),
        getBankReleases(headers),
      ])
      setQuizHistory(quizRows)
      setReleases(releaseRows)
    } finally {
      setLoading(false)
    }
  }
  useEffect(() => { load().catch(() => setLoading(false)) }, []) // eslint-disable-line react-hooks/exhaustive-deps

  const filteredQuiz = useMemo(() => {
    const needle = state.q.trim().toLowerCase()
    return quizHistory.filter((item) => {
      const passStatus = state.status === 'all' || item.status === state.status
      const passText = !needle || [item.openedx_course_id, item.openedx_unit_node_id, item.bank_release_id, item.metadata_json?.quiz_title].filter(Boolean).some((value) => String(value).toLowerCase().includes(needle))
      return passStatus && passText
    })
  }, [quizHistory, state.q, state.status])

  const filteredReleases = useMemo(() => {
    const needle = state.q.trim().toLowerCase()
    return releases.filter((item) => {
      const passStatus = state.status === 'all' || item.status === state.status
      const passText = !needle || [item.id, item.release_code, item.title, item.bank_version_id, item.openedx_library_key].filter(Boolean).some((value) => String(value).toLowerCase().includes(needle))
      return passStatus && passText
    })
  }, [releases, state.q, state.status])

  const quizTotalPages = Math.max(1, Math.ceil(filteredQuiz.length / state.pageSize))
  const releaseTotalPages = Math.max(1, Math.ceil(filteredReleases.length / state.pageSize))
  const totalPages = activeView === 'quiz' ? quizTotalPages : releaseTotalPages
  const safePage = Math.min(state.page, totalPages)
  const quizRows = filteredQuiz.slice((safePage - 1) * state.pageSize, safePage * state.pageSize)
  const releaseRows = filteredReleases.slice((safePage - 1) * state.pageSize, safePage * state.pageSize)

  const quizColumns = useMemo<EnterpriseTableColumn<CourseQuizInstance>[]>(() => [
    { key: 'stt', header: 'STT', kind: 'index', width: 52, hideable: false, render: (_row, index) => (safePage - 1) * state.pageSize + index + 1 },
    { key: 'quiz', header: 'Bài kiểm tra', kind: 'identity', minWidth: 250, hideable: false, render: (item) => <div className="quiz-history-identity"><b>{item.metadata_json?.quiz_title || 'Quiz trên CMS'}</b><small>{item.openedx_course_id}</small></div> },
    { key: 'status', header: 'Trạng thái', kind: 'status', width: 122, priority: 'important', hideable: true, render: (item) => <span className={statusClass(item.status)}>{statusLabel(item.status)}</span> },
    { key: 'type', header: 'Loại', kind: 'status', width: 108, priority: 'important', hideable: true, render: (item) => item.metadata_json?.assessment_type === 'final_test' ? 'Final test' : 'Quiz' },
    { key: 'node', header: 'Node Open edX', kind: 'text', minWidth: 170, priority: 'optional', hideable: true, defaultVisible: false, render: (item) => item.openedx_unit_node_id || '—' },
    { key: 'created', header: 'Ngày tạo', kind: 'date', width: 142, priority: 'important', hideable: true, render: (item) => dateText(item.created_at) },
    { key: 'actions', header: 'Thao tác', kind: 'actions', width: 116, sticky: 'right', hideable: false, render: (item) => can('publish_questions') && item.status !== 'rolled_back' ? <button className="btn small secondary" disabled={busy} onClick={() => run(async () => { await rollbackCourseQuizInstance(headers, item.id, { mode: 'safe', note: 'Khôi phục từ trang lịch sử Quiz' }) }, 'Đã gửi yêu cầu khôi phục Quiz', load)}>Khôi phục</button> : <span className="muted">—</span> },
  ], [busy, can, headers, run, safePage, state.pageSize])

  const releaseColumns = useMemo<EnterpriseTableColumn<BankRelease>[]>(() => [
    { key: 'stt', header: 'STT', kind: 'index', width: 52, hideable: false, render: (_row, index) => (safePage - 1) * state.pageSize + index + 1 },
    { key: 'release', header: 'Bộ đề', kind: 'identity', minWidth: 270, hideable: false, render: (item) => <div className="quiz-history-identity"><b>{releaseTitle(item)}</b><small>{item.openedx_library_key || 'Chưa có Library CMS'}</small></div> },
    { key: 'status', header: 'Trạng thái', kind: 'status', width: 122, priority: 'important', hideable: true, render: (item) => <span className={statusClass(item.status)}>{statusLabel(item.status)}</span> },
    { key: 'questions', header: 'Số câu', kind: 'number', width: 82, priority: 'important', hideable: true, render: (item) => item.approved_question_count || 0 },
    { key: 'version', header: 'Phiên bản câu hỏi', kind: 'text', minWidth: 170, priority: 'optional', hideable: true, defaultVisible: false, render: (item) => item.bank_version_id },
    { key: 'created', header: 'Ngày tạo', kind: 'date', width: 142, priority: 'important', hideable: true, render: (item) => dateText(item.created_at) },
  ], [safePage, state.pageSize])

  const created = quizHistory.filter((item) => item.status !== 'rolled_back' && item.status !== 'failed').length
  const rolledBack = quizHistory.filter((item) => item.status === 'rolled_back').length
  const failed = quizHistory.filter((item) => item.status === 'failed').length

  return <PageRoot className="page-stack bank-multipage bank-contract-page history-console bank-history-page">
    <PageHeader eyebrow="Ngân hàng đề" title="Lịch sử bộ đề và Quiz" icon="audit" breadcrumbs={[{ label: 'Ngân hàng đề', href: '/bank/departments' }, { label: 'Lịch sử Quiz' }]} />

    <BankPageIdentity
      title="Lịch sử bộ đề và Quiz"
      description="Theo dõi Release đã chốt, Quiz đã tạo trên CMS, trạng thái khôi phục và các lỗi cần kiểm tra."
      icon="audit"
      tone="slate"
      actions={<button className="btn secondary" type="button" disabled={loading} onClick={() => load()}>{loading ? 'Đang tải...' : 'Làm mới dữ liệu'}</button>}
    />

    {message ? <div className="academic-inline-notice info" role="status" aria-live="polite"><VisualIcon icon="info" tone="blue" label="Thông báo" size={18} className="notice-visual-icon" /><div className="notice-copy"><b>Thông báo thao tác</b><span>{message}</span></div></div> : null}

    <OperationsKpiStrip ariaLabel="Tổng quan lịch sử bộ đề" items={[
      { label: 'Bộ đề đã chốt', value: releases.length, icon: 'release', tone: 'info' },
      { label: 'Quiz hiệu lực', value: created, icon: 'quiz', tone: 'success' },
      { label: 'Đã khôi phục', value: rolledBack, icon: 'sync', tone: 'neutral' },
      { label: 'Lỗi cần kiểm tra', value: failed, icon: 'alert', tone: failed ? 'danger' : 'success' },
    ]} />

    <BankSection
      title="Danh sách lịch sử"
      description="Chuyển giữa Quiz trên CMS và snapshot Release đã chốt; bộ lọc được giữ trong URL."
      icon="audit"
      tone="slate"
      meta={<span className="status pending">{activeView === 'quiz' ? `${filteredQuiz.length} Quiz` : `${filteredReleases.length} bộ đề`}</span>}
      className="history-workspace bank-history-section"
      bodyClassName="bank-history-section__body"
    >
      <div className="history-view-tabs" role="tablist" aria-label="Loại lịch sử">
        <button role="tab" aria-selected={activeView === 'quiz'} className={activeView === 'quiz' ? 'is-active' : ''} onClick={() => update({ sort: 'quiz', page: 1 }, { resetPage: false })}><span>Quiz trên CMS</span><b>{quizHistory.length}</b></button>
        <button role="tab" aria-selected={activeView === 'release'} className={activeView === 'release' ? 'is-active' : ''} onClick={() => update({ sort: 'release', page: 1 }, { resetPage: false })}><span>Bộ đề đã chốt</span><b>{releases.length}</b></button>
      </div>
      <div className="history-filter-bar bank-contract-filter-toolbar">
        <label className="bank-contract-filter-field"><span>Tìm kiếm</span><input className="input" value={state.q} onChange={(event) => update({ q: event.target.value })} placeholder={activeView === 'quiz' ? 'Course ID, tên Quiz, Release...' : 'Mã Release, Library CMS...'} /></label>
        <label className="bank-contract-filter-field"><span>Trạng thái</span><select className="input" value={state.status} onChange={(event) => update({ status: event.target.value })}><option value="all">Tất cả</option><option value="created">Đã tạo</option><option value="published">Đã đưa lên CMS</option><option value="rolled_back">Đã khôi phục</option><option value="failed">Thất bại</option></select></label>
        <button className="btn secondary" type="button" disabled={loading} onClick={() => load()}>{loading ? 'Đang tải...' : 'Làm mới'}</button>
      </div>
      {activeView === 'quiz' ? <EnterpriseDataTable tableId="bank-history-quizzes" caption="Quiz trên CMS" rows={quizRows} columns={quizColumns} rowKey={(item) => item.id} density={state.density} onDensityChange={(density) => update({ density }, { resetPage: false })} loading={loading} page={safePage} pageSize={state.pageSize} total={filteredQuiz.length} totalPages={quizTotalPages} onPageChange={(page) => update({ page }, { resetPage: false })} onPageSizeChange={(pageSize) => update({ pageSize, page: 1 }, { resetPage: false })} label="Quiz" emptyTitle="Chưa có Quiz phù hợp" emptyDescription="Thử xóa bộ lọc hoặc tạo Quiz từ Release đã chốt." /> : <EnterpriseDataTable tableId="bank-history-releases" caption="Bộ đề đã chốt" rows={releaseRows} columns={releaseColumns} rowKey={(item) => item.id} density={state.density} onDensityChange={(density) => update({ density }, { resetPage: false })} loading={loading} page={safePage} pageSize={state.pageSize} total={filteredReleases.length} totalPages={releaseTotalPages} onPageChange={(page) => update({ page }, { resetPage: false })} onPageSizeChange={(pageSize) => update({ pageSize, page: 1 }, { resetPage: false })} label="bộ đề" emptyTitle="Chưa có bộ đề phù hợp" emptyDescription="Thử xóa bộ lọc hoặc chốt Release từ workspace của bài." />}
    </BankSection>
  </PageRoot>
}
