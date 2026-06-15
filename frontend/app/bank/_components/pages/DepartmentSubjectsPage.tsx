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

export function DepartmentSubjectsPage({ departmentId }: { departmentId: string }) {
  const { headers, can } = useBankData()
  const { message, busy, run } = useAsyncMessage()
  const [departments, setDepartments] = useState<Department[]>([])
  const [summaries, setSummaries] = useState<SubjectSummary[]>([])
  const [search, setSearch] = useState('')
  const [createOpen, setCreateOpen] = useState(false)
  const [code, setCode] = useState('')
  const [name, setName] = useState('')

  const load = async () => {
    const [nextDepartments, nextSummaries] = await Promise.all([getDepartments(headers), getSubjectSummaries(headers, departmentId)])
    setDepartments(nextDepartments); setSummaries(nextSummaries)
  }
  useEffect(() => { load().catch(() => null) }, [departmentId]) // eslint-disable-line react-hooks/exhaustive-deps

  const department = departments.find((item) => item.id === departmentId)
  const visible = summaries.filter(({ subject }) => matchesSearch(`${subject.code} ${subject.name}`, search))

  const editSubject = (subject: Subject) => {
    const nextCode = promptText('Sửa mã môn', subject.code)
    if (nextCode === null) return
    const nextName = promptText('Sửa tên môn', subject.name)
    if (nextName === null) return
    run(async () => { await updateSubject(headers, subject.id, { code: nextCode, name: nextName }) }, 'Đã sửa môn', load)
  }
  const removeSubject = (subject: Subject) => {
    if (!window.confirm(`Chỉ xóa được khi môn chưa có version/bài/câu hỏi bên trong. Xóa ${subject.code}?`)) return
    run(async () => { await deleteSubject(headers, subject.id) }, 'Đã xóa môn', load)
  }

  return <div className="page-stack bank-multipage">
    <Breadcrumb items={[{ label: 'Ngân hàng đề', href: '/bank' }, { label: 'Bộ môn', href: '/bank/departments' }, { label: department?.name || 'Bộ môn' }, { label: 'Môn' }]} />
    <QuickSearchBox compact />
    {message ? <div className="alert info">{message}</div> : null}
    <section className="card">
      <div className="section-head"><div><h2>{department ? `Danh sách môn trong ${department.name}` : 'Danh sách môn trong bộ môn'}</h2><p className="helper">Click vào môn để quản lý các phiên bản theo kỳ.</p></div></div>
      <SearchActionBar search={search} setSearch={setSearch} placeholder="Tìm môn" action={<button className="btn" disabled={!can('subject.create')} onClick={() => setCreateOpen(true)}>+ Thêm môn</button>} />
      <div className="entity-list horizontal multipage-list">
        {visible.map(({ subject, stats }) => <Link key={subject.id} href={`/bank/subjects/${subject.id}/versions`} className={`entity-card link-card ${reviewStatusClass(stats.status)}`}>
          <EntityActions canManage={can('subject.update')} onEdit={() => editSubject(subject)} onDelete={() => removeSubject(subject)} />
          <div className="entity-card-head"><b>{subject.code} - {subject.name}</b><span className="status-pill">{reviewStatusText(stats.status)}</span></div>
          <StatLine label="Phiên bản môn" value={stats.subject_version_count || 0} />
          <StatLine label="Đã duyệt xong" value={`${stats.review_done_version_count || 0} version`} />
          <StatLine label="Chưa duyệt xong" value={`${stats.review_not_done_version_count || 0} version`} />
          <StatLine label="Tổng câu" value={stats.total_questions || 0} />
          <StatLine label="Câu chờ xử lý" value={stats.unresolved_count || 0} />
          <StatLine label="Bài sẵn sàng chốt" value={stats.ready_to_release_chapter_count || 0} />
        </Link>)}
      </div>
      {!visible.length ? <div className="empty-state">Chưa có môn phù hợp.</div> : null}
    </section>
    <Modal open={createOpen} title="Thêm môn" onClose={() => setCreateOpen(false)}>
      <div className="mini-form">
        <input className="input" value={code} onChange={(event) => setCode(event.target.value)} placeholder="Mã môn, ví dụ WEB107" />
        <input className="input" value={name} onChange={(event) => setName(event.target.value)} placeholder="Tên môn, ví dụ Thiết kế trang web" />
        <button className="btn" type="button" disabled={busy || !code.trim() || !name.trim()} onClick={() => run(async () => {
          await createSubject(headers, { department_id: departmentId, code, name })
          setCode(''); setName(''); setCreateOpen(false)
        }, 'Đã thêm môn', load)}>Lưu môn</button>
      </div>
    </Modal>
  </div>
}

