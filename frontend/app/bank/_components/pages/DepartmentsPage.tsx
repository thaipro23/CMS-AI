'use client'

import Link from 'next/link'
import { useRouter } from 'next/navigation'
import { useEffect, useMemo, useRef, useState } from 'react'
import { useAppContext } from '../../../../context/AppContext'
import { EnterpriseDataTable, type EnterpriseTableColumn } from '../../../../components/table/EnterpriseDataTable'
import { useUrlTableState } from '../../../../hooks/useUrlTableState'
import {
  BankRelease,
  BankDashboardOverview,
  BankSearchResult,
  DepartmentSummary,
  SubjectSummary,
  SubjectVersionSummary,
  ChapterSummary,
  BankGeneratePreview,
  BankReleaseReadiness,
  BankVersion,
  BankVersionDiffPreview,
  BankVersionQuestion,
  CourseQuizInstance,
  AuditLogRow,
  Job,
  Department,
  MaterialChunk,
  MaterialVersion,
  Subject,
  SubjectChapter,
  SubjectOffering,
} from '../../../../types'
import {
  bulkReviewBankQuestions,
  createBankRelease,
  createBankVersion,
  createDepartment,
  createSubject,
  createSubjectChapter,
  createSubjectOffering,
  deleteDepartment,
  deleteSubject,
  deleteSubjectChapter,
  deleteSubjectOffering,
  deleteMaterialVersion,
  generateFromBankVersion,
  getBankDashboardOverview,
  getAuditLogs,
  getJobs,
  searchBankDashboard,
  getDepartmentSummaries,
  getSubjectSummaries,
  getSubjectVersionSummaries,
  getChapterSummaries,
  getBankMaterialChunks,
  getBankReleaseReadiness,
  getBankReleases,
  getBankVersionQuestion,
  getBankVersionQuestionPage,
  getBankVersions,
  getCourseQuizInstances,
  getDepartments,
  getMaterialVersions,
  getSubjectChapters,
  getSubjectOfferings,
  getSubjects,
  markBankDiffResolved,
  previewBankVersionDiff,
  previewGenerateFromBankVersion,
  publishBankRelease,
  reviewBankQuestion,
  rollbackCourseQuizInstance,
  uploadBankMaterial,
  updateBankQuestion,
  updateDepartment,
  updateSubject,
  updateSubjectChapter,
  updateSubjectOffering,
} from '../../../../lib/api'
import {
  TERMS,
  chapterDisplayName,
  normalizeLessonInput,
  buildChapterTitle,
  statusLabel,
  statusClass,
  useBankData,
  useAsyncMessage,
  Breadcrumb,
  Toolbar,
  SearchActionBar,
  BankTableToolbar,
  BankTableStatusFilter,
  bankStatusMatches,
  Modal,
  ConfirmDialog,
  EntityActions,
  matchesSearch,
  reviewStatusText,
  reviewStatusClass,
  emptyReviewStats,
  StatLine,
  QuickSearchBox,
  questionStats,
  nextReleaseText,
  bankAnswerRows,
  bankQuestionErrorMessage,
  isQuestionWaitingForReview,
  BankQuestionEditForm,
  BankChartRow,
  toBankQuestionEditForm,
  BankBarChart,
  BankStackedChart,
  countRows,
  auditActionText,
} from '../shared'

export function DepartmentsPage() {
  const { headers, can } = useBankData()
  const { message, busy, busyLabel, run } = useAsyncMessage()
  const [summaries, setSummaries] = useState<DepartmentSummary[]>([])
  const { state: tableState, update: updateTableState } = useUrlTableState({ status: 'all', pageSize: 20, density: 'compact' })
  const search = tableState.q
  const statusFilter = tableState.status as BankTableStatusFilter
  const [createOpen, setCreateOpen] = useState(false)
  const [code, setCode] = useState('')
  const [name, setName] = useState('')
  const [editing, setEditing] = useState<Department | null>(null)
  const [editCode, setEditCode] = useState('')
  const [editName, setEditName] = useState('')
  const [deleteTarget, setDeleteTarget] = useState<Department | null>(null)

  const load = async () => { setSummaries(await getDepartmentSummaries(headers)) }
  useEffect(() => { load().catch(() => null) }, []) // eslint-disable-line react-hooks/exhaustive-deps

  const visible = summaries.filter(({ department, stats }) => matchesSearch(`${department.code} ${department.name}`, search) && bankStatusMatches(stats, statusFilter))
  const totalPages = Math.max(1, Math.ceil(visible.length / tableState.pageSize))
  const safePage = Math.min(tableState.page, totalPages)
  const pageRows = visible.slice((safePage - 1) * tableState.pageSize, safePage * tableState.pageSize)

  const openEditDepartment = (department: Department) => {
    setEditing(department)
    setEditCode(department.code || '')
    setEditName(department.name || '')
  }
  const saveEditDepartment = () => {
    if (!editing) return
    run(async () => {
      await updateDepartment(headers, editing.id, { code: editCode, name: editName })
      setEditing(null)
    }, 'Đã sửa bộ môn', load)
  }
  const confirmDeleteDepartment = () => {
    if (!deleteTarget) return
    run(async () => {
      await deleteDepartment(headers, deleteTarget.id)
      setDeleteTarget(null)
    }, 'Đã xóa bộ môn', load)
  }

  const columns = useMemo<EnterpriseTableColumn<DepartmentSummary>[]>(() => [
    { key: 'stt', header: 'STT', width: 64, minWidth: 64, sticky: 'left', stickyOffset: 0, hideable: false, className: 'stt-cell', render: (_row, index) => (safePage - 1) * tableState.pageSize + index + 1 },
    { key: 'department', header: 'Bộ môn', minWidth: 240, sticky: 'left', stickyOffset: 64, hideable: false, render: ({ department }) => <Link className="bank-table-link" href={`/bank/departments/${department.id}/subjects`}><b>{department.name}</b><small>{department.code}</small></Link> },
    { key: 'status', header: 'Trạng thái', minWidth: 150, hideable: true, render: ({ stats: rawStats }) => { const stats = rawStats || emptyReviewStats(); return <span className={`bank-row-status status-${stats.status || 'empty'}`}>{reviewStatusText(stats.status)}</span> } },
    { key: 'subjects', header: 'Môn', align: 'right', hideable: true, render: ({ stats }) => stats?.subject_count || 0 },
    { key: 'approved', header: 'Đã duyệt', align: 'right', hideable: true, render: ({ stats }) => stats?.review_done_subject_count || 0 },
    { key: 'pending', header: 'Chưa duyệt', align: 'right', hideable: true, render: ({ stats }) => stats?.review_not_done_subject_count || 0 },
    { key: 'unresolved', header: 'Cần xử lý', align: 'right', hideable: true, render: ({ stats }) => stats?.unresolved_count || 0 },
    { key: 'ready', header: 'Sẵn sàng chốt', align: 'right', hideable: true, render: ({ stats }) => stats?.ready_to_release_chapter_count || 0 },
    { key: 'actions', header: 'Thao tác', minWidth: 150, sticky: 'right', stickyOffset: 0, hideable: false, render: ({ department }) => <EntityActions variant="inline" canManage={can('manage_settings')} lockedLabel="Không có quyền" onEdit={() => openEditDepartment(department)} onDelete={() => setDeleteTarget(department)} /> },
  ], [can, safePage, tableState.pageSize])

  return <div className="page-stack bank-multipage">
    <Breadcrumb items={[{ label: 'Ngân hàng câu hỏi', href: '/bank' }, { label: 'Bộ môn' }]} />
    <QuickSearchBox compact />
    {message ? <div className="alert info">{message}</div> : null}
    {busy ? <div className="inline-system-status" role="status" aria-live="polite"><span className="spinner tiny" aria-hidden="true" />{busyLabel || 'Hệ thống đang xử lý. Bạn có thể tiếp tục xem dữ liệu hiện có.'}</div> : null}
    <section className="card">
      <div className="section-head"><div><h2>Danh sách bộ môn</h2><p className="helper">Cấu trúc chuẩn: Bộ môn → Môn học → Phiên bản môn theo học kỳ → Bài/Chapter → Câu hỏi. Release và Quiz là thao tác đầu ra, không phải cấp trong cây.</p></div></div>
      <BankTableToolbar search={search} setSearch={(value) => updateTableState({ q: value })} statusFilter={statusFilter} setStatusFilter={(value) => updateTableState({ status: value })} resultCount={visible.length} totalCount={summaries.length} placeholder="Tìm bộ môn" action={can('manage_settings') ? <button className="btn" onClick={() => setCreateOpen(true)}>+ Thêm bộ môn</button> : undefined} />
      <div className="bank-status-legend bank-status-legend-compact" aria-label="Chú giải trạng thái">
        <span><i className="dot-empty" />Chưa có dữ liệu</span><span><i className="dot-incomplete" />Cần hoàn thiện</span><span><i className="dot-published" />Đã đưa lên CMS</span>
      </div>
      <EnterpriseDataTable
        tableId="bank-departments"
        caption="Danh sách bộ môn"
        rows={pageRows}
        columns={columns}
        rowKey={({ department }) => department.id}
        density={tableState.density}
        onDensityChange={(density) => updateTableState({ density }, { resetPage: false })}
        page={safePage}
        pageSize={tableState.pageSize}
        total={visible.length}
        totalPages={totalPages}
        onPageChange={(page) => updateTableState({ page }, { resetPage: false })}
        onPageSizeChange={(pageSize) => updateTableState({ pageSize, page: 1 }, { resetPage: false })}
        label="bộ môn"
        emptyTitle={search || statusFilter !== 'all' ? 'Không có kết quả phù hợp' : 'Chưa có bộ môn'}
        emptyDescription={search || statusFilter !== 'all' ? 'Xóa bộ lọc hoặc thử từ khóa khác.' : 'Thêm bộ môn đầu tiên để bắt đầu cấu trúc Ngân hàng câu hỏi.'}
      />
    </section>

    <Modal open={Boolean(editing)} title="Sửa bộ môn" onClose={() => setEditing(null)}>
      <div className="mini-form">
        <label className="field-label">Mã bộ môn</label>
        <input className="input" value={editCode} onChange={(event) => setEditCode(event.target.value)} placeholder="Mã bộ môn" />
        <label className="field-label">Tên bộ môn</label>
        <input className="input" value={editName} onChange={(event) => setEditName(event.target.value)} placeholder="Tên bộ môn" />
        <div className="modal-actions">
          <button className="btn secondary" type="button" disabled={busy} onClick={() => setEditing(null)}>Hủy</button>
          <button className="btn" type="button" disabled={busy || !editCode.trim() || !editName.trim()} onClick={saveEditDepartment}>{busy ? <span className="inline-busy-label"><span className="spinner tiny" aria-hidden="true" />Đang lưu</span> : 'Lưu thay đổi'}</button>
        </div>
      </div>
    </Modal>
    <ConfirmDialog
      open={Boolean(deleteTarget)}
      title={`Xóa bộ môn ${deleteTarget?.name || ''}?`}
      description={<p>Chỉ xóa được khi bộ môn chưa có môn bên trong. Thao tác này dùng popup xác nhận của hệ thống, không dùng confirm của trình duyệt.</p>}
      confirmLabel="Xác nhận xóa"
      danger
      busy={busy}
      onClose={() => setDeleteTarget(null)}
      onConfirm={confirmDeleteDepartment}
    />

    <Modal open={createOpen} title="Thêm bộ môn" onClose={() => setCreateOpen(false)}>
      <div className="mini-form">
        <input className="input" value={code} onChange={(event) => setCode(event.target.value)} placeholder="Mã bộ môn, ví dụ CNTT" />
        <input className="input" value={name} onChange={(event) => setName(event.target.value)} placeholder="Tên bộ môn, ví dụ Công nghệ thông tin" />
        <button className="btn" type="button" disabled={busy || !code.trim() || !name.trim()} onClick={() => run(async () => {
          const created = await createDepartment(headers, { code, name })
          setSummaries((current) => {
            const withoutDuplicate = current.filter((item) => item.department.id !== created.id)
            return [...withoutDuplicate, { department: created, stats: emptyReviewStats({ subject_count: 0, review_done_subject_count: 0, review_not_done_subject_count: 0 }) }].sort((a, b) => String(a.department.code || '').localeCompare(String(b.department.code || '')))
          })
          setCode(''); setName(''); setCreateOpen(false)
          await load()
          window.setTimeout(() => { load().catch(() => null) }, 500)
        }, 'Đã thêm bộ môn')}>{busy ? <span className="inline-busy-label"><span className="spinner tiny" aria-hidden="true" />Đang lưu</span> : 'Lưu bộ môn'}</button>
      </div>
    </Modal>
  </div>
}

