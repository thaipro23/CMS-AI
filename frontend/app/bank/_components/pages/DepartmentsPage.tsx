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
  EntityActions,
  promptText,
  matchesSearch,
  reviewStatusText,
  reviewStatusClass,
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

  const load = async () => { setSummaries(await getDepartmentSummaries(headers)) }
  useEffect(() => { load().catch(() => null) }, []) // eslint-disable-line react-hooks/exhaustive-deps

  const visible = summaries.filter(({ department }) => matchesSearch(`${department.code} ${department.name}`, search))

  const editDepartment = (department: Department) => {
    const nextCode = promptText('Sửa mã bộ môn', department.code)
    if (nextCode === null) return
    const nextName = promptText('Sửa tên bộ môn', department.name)
    if (nextName === null) return
    run(async () => { await updateDepartment(headers, department.id, { code: nextCode, name: nextName }) }, 'Đã sửa bộ môn', load)
  }
  const removeDepartment = (department: Department) => {
    if (!window.confirm(`Chỉ xóa được khi bộ môn chưa có môn bên trong. Xóa ${department.name}?`)) return
    run(async () => { await deleteDepartment(headers, department.id) }, 'Đã xóa bộ môn', load)
  }

  return <div className="page-stack bank-multipage">
    {busy ? <div className="bank-loading-overlay"><div className="bank-loading-card"><div className="spinner" /><b>{busyLabel}</b><small>Không tắt trang trong lúc hệ thống đang xử lý.</small></div></div> : null}
    <Breadcrumb items={[{ label: 'Ngân hàng đề', href: '/bank' }, { label: 'Bộ môn' }]} />
    <QuickSearchBox compact />
    {message ? <div className="alert info">{message}</div> : null}
    <section className="card">
      <div className="section-head"><div><h2>Danh sách bộ môn</h2><p className="helper">Click vào bộ môn để xem các môn bên trong.</p></div></div>
      <SearchActionBar search={search} setSearch={setSearch} placeholder="Tìm bộ môn" action={<button className="btn" disabled={!can('manage_settings')} onClick={() => setCreateOpen(true)}>+ Thêm bộ môn</button>} />
      <div className="entity-list horizontal multipage-list">
        {visible.map(({ department, stats }) => <Link key={department.id} href={`/bank/departments/${department.id}/subjects`} className={`entity-card link-card ${reviewStatusClass(stats.status)}`}>
          <EntityActions canManage={can('manage_settings')} onEdit={() => editDepartment(department)} onDelete={() => removeDepartment(department)} />
          <div className="entity-card-head"><b>{department.name}</b><span className="status-pill">{reviewStatusText(stats.status)}</span></div>
          <small>{department.code}</small>
          <StatLine label="Môn" value={stats.subject_count || 0} />
          <StatLine label="Đã duyệt xong" value={`${stats.review_done_subject_count || 0} môn`} />
          <StatLine label="Chưa duyệt xong" value={`${stats.review_not_done_subject_count || 0} môn`} />
          <StatLine label="Câu chờ xử lý" value={stats.unresolved_count || 0} />
          <StatLine label="Bài sẵn sàng chốt" value={stats.ready_to_release_chapter_count || 0} />
        </Link>)}
      </div>
      {!visible.length ? <div className="empty-state">Chưa có bộ môn phù hợp.</div> : null}
    </section>
    <Modal open={createOpen} title="Thêm bộ môn" onClose={() => setCreateOpen(false)}>
      <div className="mini-form">
        <input className="input" value={code} onChange={(event) => setCode(event.target.value)} placeholder="Mã bộ môn, ví dụ CNTT" />
        <input className="input" value={name} onChange={(event) => setName(event.target.value)} placeholder="Tên bộ môn, ví dụ Công nghệ thông tin" />
        <button className="btn" type="button" disabled={busy || !code.trim() || !name.trim()} onClick={() => run(async () => {
          await createDepartment(headers, { code, name })
          setCode(''); setName(''); setCreateOpen(false)
        }, 'Đã thêm bộ môn', load)}>Lưu bộ môn</button>
      </div>
    </Modal>
  </div>
}

