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

export function SubjectVersionsPage({ subjectId }: { subjectId: string }) {
  const { headers, can } = useBankData()
  const { message, busy, run } = useAsyncMessage()
  const router = useRouter()
  const [departments, setDepartments] = useState<Department[]>([])
  const [subjects, setSubjects] = useState<Subject[]>([])
  const [summaries, setSummaries] = useState<SubjectVersionSummary[]>([])
  const [search, setSearch] = useState('')
  const [createOpen, setCreateOpen] = useState(false)
  const [term, setTerm] = useState('SU25')
  const [mode, setMode] = useState<'blank' | 'clone'>('clone')
  const [cloneFromId, setCloneFromId] = useState('')

  const load = async () => {
    const [nextDepartments, nextSubjects, nextSummaries] = await Promise.all([
      getDepartments(headers), getSubjects(headers), getSubjectVersionSummaries(headers, subjectId),
    ])
    setDepartments(nextDepartments); setSubjects(nextSubjects); setSummaries(nextSummaries)
    if (!cloneFromId && nextSummaries.length) setCloneFromId(nextSummaries[0].subject_version.id)
  }
  useEffect(() => { load().catch(() => null) }, [subjectId]) // eslint-disable-line react-hooks/exhaustive-deps

  const subject = subjects.find((item) => item.id === subjectId)
  const department = departments.find((item) => item.id === subject?.department_id)
  const visible = summaries.filter(({ subject_version }) => matchesSearch(`${subject_version.code} ${subject_version.name} ${subject_version.term || ''}`, search))

  const editSubjectVersion = (subjectVersion: SubjectOffering) => {
    const nextCode = promptText('Sửa mã version môn', subjectVersion.code)
    if (nextCode === null) return
    const nextName = promptText('Sửa tên version môn', subjectVersion.name || '')
    if (nextName === null) return
    run(async () => { await updateSubjectOffering(headers, subjectVersion.id, { code: nextCode, name: nextName }) }, 'Đã sửa version môn', load)
  }
  const removeSubjectVersion = (subjectVersion: SubjectOffering) => {
    if (!window.confirm(`Chỉ xóa được khi version môn chưa có bài/tài liệu/câu hỏi/release. Xóa ${subjectVersion.code}?`)) return
    run(async () => { await deleteSubjectOffering(headers, subjectVersion.id) }, 'Đã xóa version môn', load)
  }

  return <div className="page-stack bank-multipage">
    <Breadcrumb items={[{ label: 'Ngân hàng đề', href: '/bank' }, { label: 'Bộ môn', href: '/bank/departments' }, { label: department?.name || 'Bộ môn', href: department ? `/bank/departments/${department.id}/subjects` : undefined }, { label: subject?.code || 'Môn' }, { label: 'Phiên bản môn' }]} />
    <QuickSearchBox compact />
    {message ? <div className="alert info">{message}</div> : null}
    <section className="card">
      <div className="section-head"><div><h2>{subject ? `Danh sách version của ${subject.code}` : 'Danh sách version môn'}</h2><p className="helper">Tạo version mới trống hoặc clone 100% bản làm việc từ kỳ cũ.</p></div></div>
      <SearchActionBar search={search} setSearch={setSearch} placeholder="Tìm version môn" action={<button className="btn" disabled={!can('subject.update')} onClick={() => setCreateOpen(true)}>+ Tạo version môn</button>} />
      <div className="entity-list horizontal multipage-list">
        {visible.map(({ subject_version, stats }) => <Link key={subject_version.id} href={`/bank/subject-versions/${subject_version.id}/chapters`} className={`entity-card link-card ${reviewStatusClass(stats.status)}`}>
          <EntityActions canManage={can('subject.update')} onEdit={() => editSubjectVersion(subject_version)} onDelete={() => removeSubjectVersion(subject_version)} />
          <div className="entity-card-head"><b>{subject_version.code}</b><span className="status-pill">{reviewStatusText(stats.status)}</span></div>
          <small>{subject_version.name || subject_version.term || 'Version môn'}</small>
          <StatLine label="Bài" value={stats.chapter_count || 0} />
          <StatLine label="Tổng câu" value={`${stats.total_questions || 0}/${stats.question_capacity || ((stats.chapter_count || 0) * (stats.chapter_question_limit || 100))}`} />
          <StatLine label="Đã duyệt" value={stats.approved_count || 0} />
          <StatLine label="Chưa duyệt/lỗi" value={stats.unresolved_count || 0} />
          <StatLine label="Release đã publish" value={`${stats.published_release_count || 0}/${stats.chapter_count || 0} bài`} />
        </Link>)}
      </div>
      {!visible.length ? <div className="empty-state">Chưa có version phù hợp.</div> : null}
    </section>
    <Modal open={createOpen} title="Tạo version môn" onClose={() => setCreateOpen(false)}>
      <div className="mini-form">
        <div className="button-row"><button className={mode === 'clone' ? 'btn' : 'btn secondary'} onClick={() => setMode('clone')}>Clone từ version khác</button><button className={mode === 'blank' ? 'btn' : 'btn secondary'} onClick={() => setMode('blank')}>Tạo mới trống</button></div>
        <select className="input" value={term} onChange={(event) => setTerm(event.target.value)}>{TERMS.map(([value, label]) => <option value={value} key={value}>{value} - {label}</option>)}</select>
        {mode === 'clone' ? <select className="input" value={cloneFromId} onChange={(event) => setCloneFromId(event.target.value)}>{summaries.map(({ subject_version }) => <option value={subject_version.id} key={subject_version.id}>Clone từ {subject_version.code}</option>)}</select> : null}
        <p className="helper">Clone 100% bản làm việc: bài, tài liệu, bank version, câu hỏi approved. Không clone Release/Open edX Library và không chạy diff khi clone.</p>
        <div className="modal-actions"><button className="btn secondary" onClick={() => setCreateOpen(false)}>Hủy</button><button className="btn" disabled={busy || !term || (mode === 'clone' && !cloneFromId)} onClick={() => run(async () => {
          const created = await createSubjectOffering(headers, { subject_id: subjectId, term, clone_from_offering_id: mode === 'clone' ? cloneFromId : null, version_code: term, clone_chapters: true, clone_materials: true, clone_questions: true })
          setCreateOpen(false)
          router.push(`/bank/subject-versions/${created.id}/chapters`)
        }, 'Đã tạo version môn', load)}>Tạo version</button></div>
      </div>
    </Modal>
  </div>
}

