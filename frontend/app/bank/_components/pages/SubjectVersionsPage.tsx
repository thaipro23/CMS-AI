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
  BankStatusLegend,
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
  const [editing, setEditing] = useState<SubjectOffering | null>(null)
  const [editCode, setEditCode] = useState('')
  const [editName, setEditName] = useState('')
  const [deleteTarget, setDeleteTarget] = useState<SubjectOffering | null>(null)

  const load = async () => {
    const subject = await getSubject(headers, subjectId)
    const [department, nextSummaries] = await Promise.all([
      getDepartment(headers, subject.department_id),
      getSubjectVersionSummaries(headers, subjectId),
    ])
    setDepartments([department]); setSubjects([subject]); setSummaries(nextSummaries)
    if (!cloneFromId && nextSummaries.length) setCloneFromId(nextSummaries[0].subject_version.id)
  }
  useEffect(() => { load().catch(() => null) }, [subjectId]) // eslint-disable-line react-hooks/exhaustive-deps

  const subject = subjects.find((item) => item.id === subjectId)
  const department = departments.find((item) => item.id === subject?.department_id)
  const visible = summaries.filter(({ subject_version }) => matchesSearch(`${subject_version.code} ${subject_version.name} ${subject_version.term || ''}`, search))

  const openEditSubjectVersion = (subjectVersion: SubjectOffering) => {
    setEditing(subjectVersion)
    setEditCode(subjectVersion.code || '')
    setEditName(subjectVersion.name || '')
  }
  const saveEditSubjectVersion = () => {
    if (!editing) return
    run(async () => {
      await updateSubjectOffering(headers, editing.id, { code: editCode, name: editName })
      setEditing(null)
    }, 'Đã sửa phiên bản môn', load)
  }
  const confirmDeleteSubjectVersion = () => {
    if (!deleteTarget) return
    run(async () => {
      await deleteSubjectOffering(headers, deleteTarget.id)
      setDeleteTarget(null)
    }, 'Đã xóa phiên bản môn', load)
  }

  return <div className="page-stack bank-multipage">
    <Breadcrumb items={[{ label: 'Ngân hàng đề', href: '/bank' }, { label: 'Bộ môn', href: '/bank/departments' }, { label: department?.name || 'Bộ môn', href: department ? `/bank/departments/${department.id}/subjects` : undefined }, { label: subject?.code || 'Môn' }, { label: 'Phiên bản môn' }]} />
    <QuickSearchBox compact />
    {message ? <div className="alert info">{message}</div> : null}
    <section className="card">
      <div className="section-head"><div><h2>{subject ? `Danh sách phiên bản của ${subject.code}` : 'Danh sách phiên bản môn'}</h2><p className="helper">Tạo mới hoàn toàn hoặc tạo từ phiên bản cũ của môn.</p></div></div>
      <SearchActionBar search={search} setSearch={setSearch} placeholder="Tìm phiên bản môn" action={<button className="btn" disabled={!can('subject.update')} onClick={() => setCreateOpen(true)}>+ Tạo phiên bản môn</button>} />
      <BankStatusLegend />
      <div className="entity-list horizontal multipage-list">
        {visible.map(({ subject_version, stats: rawStats }) => {
          const stats = rawStats || emptyReviewStats()
          const hasPublished = Boolean(stats.is_published || (stats.published_release_count || 0) > 0 || stats.status === 'published')
          return <Link key={subject_version.id} href={`/bank/subject-versions/${subject_version.id}/chapters`} className={`entity-card link-card ${reviewStatusClass(hasPublished ? 'published' : stats.status)}`}>
            <EntityActions canManage={can('subject.update') && !hasPublished} onEdit={() => openEditSubjectVersion(subject_version)} onDelete={() => setDeleteTarget(subject_version)} />
            <div className="entity-card-head"><b>{subject_version.code}</b><span className="status-pill">{hasPublished ? 'Đã public thư viện' : reviewStatusText(stats.status)}</span></div>
            <small>{subject_version.name || subject_version.term || 'Phiên bản môn'}</small>
            <StatLine label="Bài" value={stats.chapter_count || 0} />
            <StatLine label="Tổng câu" value={`${stats.total_questions || 0}/${stats.question_capacity || ((stats.chapter_count || 0) * (stats.chapter_question_limit || 100))}`} />
            <StatLine label="Đã duyệt" value={stats.approved_count || 0} />
            <StatLine label="Chưa duyệt/lỗi" value={stats.unresolved_count || 0} />
            <StatLine label="Bộ đề đã đưa lên CMS" value={`${stats.published_release_count || 0}/${stats.chapter_count || 0} bài`} />
            {hasPublished ? <span className="status success">Đã khóa chỉnh sửa</span> : null}
          </Link>
        })}
      </div>
      {!visible.length ? <div className="empty-state">Chưa có version phù hợp.</div> : null}
    </section>

    <Modal open={Boolean(editing)} title="Sửa phiên bản môn" onClose={() => setEditing(null)}>
      <div className="mini-form">
        <label className="field-label">Mã phiên bản môn</label>
        <input className="input" value={editCode} onChange={(event) => setEditCode(event.target.value)} placeholder="Mã phiên bản môn" />
        <label className="field-label">Tên phiên bản môn</label>
        <input className="input" value={editName} onChange={(event) => setEditName(event.target.value)} placeholder="Tên phiên bản môn" />
        <div className="modal-actions">
          <button className="btn secondary" type="button" disabled={busy} onClick={() => setEditing(null)}>Hủy</button>
          <button className="btn" type="button" disabled={busy || !editCode.trim()} onClick={saveEditSubjectVersion}>Lưu thay đổi</button>
        </div>
      </div>
    </Modal>
    <ConfirmDialog
      open={Boolean(deleteTarget)}
      title={`Xóa phiên bản môn ${deleteTarget?.code || ''}?`}
      description={<p>Chỉ xóa được khi phiên bản môn chưa có bài, tài liệu, câu hỏi hoặc bộ đề đã chốt.</p>}
      confirmLabel="Xác nhận xóa"
      danger
      busy={busy}
      onClose={() => setDeleteTarget(null)}
      onConfirm={confirmDeleteSubjectVersion}
    />

    <Modal open={createOpen} title="Tạo phiên bản môn" onClose={() => setCreateOpen(false)}>
      <div className="mini-form">
        <div className="button-row"><button className={mode === 'clone' ? 'btn' : 'btn secondary'} onClick={() => setMode('clone')}>Tạo từ phiên bản cũ</button><button className={mode === 'blank' ? 'btn' : 'btn secondary'} onClick={() => setMode('blank')}>Tạo mới hoàn toàn</button></div>
        <select className="input" value={term} onChange={(event) => setTerm(event.target.value)}>{TERMS.map(([value, label]) => <option value={value} key={value}>{value} - {label}</option>)}</select>
        {mode === 'clone' ? <select className="input" value={cloneFromId} onChange={(event) => setCloneFromId(event.target.value)}>{summaries.map(({ subject_version }) => <option value={subject_version.id} key={subject_version.id}>Tạo từ {subject_version.code}</option>)}</select> : null}
        <p className="helper">Hệ thống sao chép bài, tài liệu và câu hỏi đã duyệt từ phiên bản cũ. Nếu sau đó thay tài liệu, hệ thống tự loại các câu không còn nằm trong bộ tài liệu hiện tại.</p>
        <div className="modal-actions"><button className="btn secondary" onClick={() => setCreateOpen(false)}>Hủy</button><button className="btn" disabled={busy || !term || (mode === 'clone' && !cloneFromId)} onClick={() => run(async () => {
          const created = await createSubjectOffering(headers, { subject_id: subjectId, term, clone_from_offering_id: mode === 'clone' ? cloneFromId : null, version_code: term, clone_chapters: true, clone_materials: true, clone_questions: true })
          setSummaries((current) => {
            const withoutDuplicate = current.filter((item) => item.subject_version.id !== created.id)
            return [...withoutDuplicate, { subject_version: created, stats: emptyReviewStats({ chapter_count: 0, review_done_chapter_count: 0, review_not_done_chapter_count: 0 }) }].sort((a, b) => String(a.subject_version.code || '').localeCompare(String(b.subject_version.code || '')))
          })
          setTerm(''); setCloneFromId(''); setCreateOpen(false)
          router.push(`/bank/subject-versions/${created.id}/chapters`)
        }, 'Đã tạo phiên bản môn')}>Tạo phiên bản</button></div>
      </div>
    </Modal>
  </div>
}

