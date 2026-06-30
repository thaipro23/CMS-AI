'use client'

import Link from 'next/link'
import { useRouter } from 'next/navigation'
import { useEffect, useMemo, useRef, useState } from 'react'
import { useAppContext } from '../../../../context/AppContext'
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
  const [search, setSearch] = useState('')
  const [createOpen, setCreateOpen] = useState(false)
  const [code, setCode] = useState('')
  const [name, setName] = useState('')
  const [editing, setEditing] = useState<Department | null>(null)
  const [editCode, setEditCode] = useState('')
  const [editName, setEditName] = useState('')
  const [deleteTarget, setDeleteTarget] = useState<Department | null>(null)

  const load = async () => { setSummaries(await getDepartmentSummaries(headers)) }
  useEffect(() => { load().catch(() => null) }, []) // eslint-disable-line react-hooks/exhaustive-deps

  const visible = summaries.filter(({ department }) => matchesSearch(`${department.code} ${department.name}`, search))

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

  return <div className="page-stack bank-multipage">
    <Breadcrumb items={[{ label: 'Ngân hàng đề', href: '/bank' }, { label: 'Bộ môn' }]} />
    <QuickSearchBox compact />
    {message ? <div className="alert info">{message}</div> : null}
    {busy ? <div className="inline-system-status" role="status" aria-live="polite"><span className="spinner tiny" aria-hidden="true" />{busyLabel || 'Hệ thống đang xử lý. Bạn có thể tiếp tục xem dữ liệu hiện có.'}</div> : null}
    <section className="card">
      <div className="section-head"><div><h2>Danh sách bộ môn</h2><p className="helper">Click vào bộ môn để xem các môn bên trong.</p></div></div>
      <SearchActionBar search={search} setSearch={setSearch} placeholder="Tìm bộ môn" action={can('manage_settings') ? <button className="btn" onClick={() => setCreateOpen(true)}>+ Thêm bộ môn</button> : undefined} />
      <div className="bank-status-legend" aria-label="Chú giải trạng thái">
        <span><i className="dot-empty" />Chưa làm</span><span><i className="dot-incomplete" />Chưa làm hết</span><span><i className="dot-published" />Đã public thư viện</span>
      </div>
      <div className="entity-list horizontal multipage-list">
        {visible.map(({ department, stats: rawStats }) => {
          const stats = rawStats || emptyReviewStats()
          return <Link key={department.id} href={`/bank/departments/${department.id}/subjects`} className={`entity-card link-card ${reviewStatusClass(stats.status)}`}>
          <EntityActions canManage={can('manage_settings')} onEdit={() => openEditDepartment(department)} onDelete={() => setDeleteTarget(department)} />
          <div className="entity-card-head"><b>{department.name}</b><span className="status-pill">{reviewStatusText(stats.status)}</span></div>
          <small>{department.code}</small>
          <StatLine label="Môn" value={stats.subject_count || 0} />
          <StatLine label="Đã duyệt xong" value={`${stats.review_done_subject_count || 0} môn`} />
          <StatLine label="Chưa duyệt xong" value={`${stats.review_not_done_subject_count || 0} môn`} />
          <StatLine label="Câu chờ xử lý" value={stats.unresolved_count || 0} />
          <StatLine label="Bài sẵn sàng chốt" value={stats.ready_to_release_chapter_count || 0} />
        </Link>
        })}
      </div>
      {!visible.length ? <div className="empty-state">Chưa có bộ môn phù hợp.</div> : null}
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

