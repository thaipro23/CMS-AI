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
  getDepartment,
  getMaterialVersions,
  getSubjectChapter,
  getSubjectChapters,
  getSubjectOffering,
  getSubjectOfferings,
  getSubject,
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

export function DepartmentSubjectsPage({ departmentId }: { departmentId: string }) {
  const { headers, can } = useBankData()
  const { message, busy, run } = useAsyncMessage()
  const [departments, setDepartments] = useState<Department[]>([])
  const [summaries, setSummaries] = useState<SubjectSummary[]>([])
  const [search, setSearch] = useState('')
  const [createOpen, setCreateOpen] = useState(false)
  const [code, setCode] = useState('')
  const [name, setName] = useState('')
  const [editing, setEditing] = useState<Subject | null>(null)
  const [editCode, setEditCode] = useState('')
  const [editName, setEditName] = useState('')
  const [deleteTarget, setDeleteTarget] = useState<Subject | null>(null)

  const load = async () => {
    const [department, nextSummaries] = await Promise.all([
      getDepartment(headers, departmentId),
      getSubjectSummaries(headers, departmentId),
    ])
    setDepartments([department]); setSummaries(nextSummaries)
  }
  useEffect(() => { load().catch(() => null) }, [departmentId]) // eslint-disable-line react-hooks/exhaustive-deps

  const department = departments.find((item) => item.id === departmentId)
  const visible = summaries.filter(({ subject }) => matchesSearch(`${subject.code} ${subject.name}`, search))

  const openEditSubject = (subject: Subject) => {
    setEditing(subject)
    setEditCode(subject.code || '')
    setEditName(subject.name || '')
  }
  const saveEditSubject = () => {
    if (!editing) return
    run(async () => {
      await updateSubject(headers, editing.id, { code: editCode, name: editName })
      setEditing(null)
    }, 'Đã sửa môn', load)
  }
  const confirmDeleteSubject = () => {
    if (!deleteTarget) return
    run(async () => {
      await deleteSubject(headers, deleteTarget.id)
      setDeleteTarget(null)
    }, 'Đã xóa môn', load)
  }

  return <div className="page-stack bank-multipage">
    <Breadcrumb items={[{ label: 'Ngân hàng đề', href: '/bank' }, { label: 'Bộ môn', href: '/bank/departments' }, { label: department?.name || 'Bộ môn' }, { label: 'Môn' }]} />
    <QuickSearchBox compact />
    {message ? <div className="alert info">{message}</div> : null}
    <section className="card">
      <div className="section-head"><div><h2>{department ? `Danh sách môn trong ${department.name}` : 'Danh sách môn trong bộ môn'}</h2><p className="helper">Click vào môn để quản lý các phiên bản theo kỳ.</p></div></div>
      <SearchActionBar search={search} setSearch={setSearch} placeholder="Tìm môn" action={can('subject.create') ? <button className="btn" onClick={() => setCreateOpen(true)}>+ Thêm môn</button> : undefined} />
      <div className="responsive-table-wrap bank-compact-table-wrap">
        <table className="ops-data-table bank-compact-data-table bank-subject-table">
          <thead><tr><th>STT</th><th>Môn</th><th>Trạng thái</th><th>Phiên bản</th><th>Đã duyệt</th><th>Chưa duyệt</th><th>Tổng câu</th><th>Cần xử lý</th><th>Sẵn sàng chốt</th><th>Thao tác</th></tr></thead>
          <tbody>{visible.map(({ subject, stats: rawStats }, index) => {
            const stats = rawStats || emptyReviewStats()
            return <tr key={subject.id}>
              <td className="stt-cell">{index + 1}</td>
              <td><Link className="bank-table-link" href={`/bank/subjects/${subject.id}/versions`}><b>{subject.code}</b><small>{subject.name}</small></Link></td>
              <td><span className={`bank-row-status status-${stats.status || 'empty'}`}>{reviewStatusText(stats.status)}</span></td>
              <td>{stats.subject_version_count || 0}</td>
              <td>{stats.review_done_version_count || 0}</td>
              <td>{stats.review_not_done_version_count || 0}</td>
              <td>{stats.total_questions || 0}</td>
              <td>{stats.unresolved_count || 0}</td>
              <td>{stats.ready_to_release_chapter_count || 0}</td>
              <td><EntityActions canManage={can('subject.update')} onEdit={() => openEditSubject(subject)} onDelete={() => setDeleteTarget(subject)} /></td>
            </tr>
          })}{!visible.length ? <tr><td colSpan={10}><div className="empty-state">Chưa có môn phù hợp.</div></td></tr> : null}</tbody>
        </table>
      </div>
    </section>

    <Modal open={Boolean(editing)} title="Sửa môn" onClose={() => setEditing(null)}>
      <div className="mini-form">
        <label className="field-label">Mã môn</label>
        <input className="input" value={editCode} onChange={(event) => setEditCode(event.target.value)} placeholder="Mã môn" />
        <label className="field-label">Tên môn</label>
        <input className="input" value={editName} onChange={(event) => setEditName(event.target.value)} placeholder="Tên môn" />
        <div className="modal-actions">
          <button className="btn secondary" type="button" disabled={busy} onClick={() => setEditing(null)}>Hủy</button>
          <button className="btn" type="button" disabled={busy || !editCode.trim() || !editName.trim()} onClick={saveEditSubject}>Lưu thay đổi</button>
        </div>
      </div>
    </Modal>
    <ConfirmDialog
      open={Boolean(deleteTarget)}
      title={`Xóa môn ${deleteTarget?.code || ''}?`}
      description={<p>Chỉ xóa được khi môn chưa có version/bài/câu hỏi bên trong.</p>}
      confirmLabel="Xác nhận xóa"
      danger
      busy={busy}
      onClose={() => setDeleteTarget(null)}
      onConfirm={confirmDeleteSubject}
    />

    <Modal open={createOpen} title="Thêm môn" onClose={() => setCreateOpen(false)}>
      <div className="mini-form">
        <input className="input" value={code} onChange={(event) => setCode(event.target.value)} placeholder="Mã môn, ví dụ WEB107" />
        <input className="input" value={name} onChange={(event) => setName(event.target.value)} placeholder="Tên môn, ví dụ Thiết kế trang web" />
        <button className="btn" type="button" disabled={busy || !code.trim() || !name.trim()} onClick={() => run(async () => {
          const created = await createSubject(headers, { department_id: departmentId, code, name })
          setSummaries((current) => {
            const withoutDuplicate = current.filter((item) => item.subject.id !== created.id)
            return [...withoutDuplicate, { subject: created, stats: emptyReviewStats({ subject_version_count: 0, review_done_version_count: 0, review_not_done_version_count: 0 }) }].sort((a, b) => String(a.subject.code || '').localeCompare(String(b.subject.code || '')))
          })
          setCode(''); setName(''); setCreateOpen(false)
          await load()
          window.setTimeout(() => { load().catch(() => null) }, 500)
        }, 'Đã thêm môn')}>Lưu môn</button>
      </div>
    </Modal>
  </div>
}

