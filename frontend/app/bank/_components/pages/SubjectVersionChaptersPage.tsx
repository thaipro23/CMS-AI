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

export function SubjectVersionChaptersPage({ versionId }: { versionId: string }) {
  const { headers, can } = useBankData()
  const { message, busy, run } = useAsyncMessage()
  const [departments, setDepartments] = useState<Department[]>([])
  const [subjects, setSubjects] = useState<Subject[]>([])
  const [offerings, setOfferings] = useState<SubjectOffering[]>([])
  const [summaries, setSummaries] = useState<ChapterSummary[]>([])
  const [search, setSearch] = useState('')
  const [createOpen, setCreateOpen] = useState(false)
  const [chapterInput, setChapterInput] = useState('')

  const load = async () => {
    const [nextDepartments, nextSubjects, nextOfferings, nextSummaries] = await Promise.all([
      getDepartments(headers), getSubjects(headers), getSubjectOfferings(headers), getChapterSummaries(headers, versionId),
    ])
    setDepartments(nextDepartments); setSubjects(nextSubjects); setOfferings(nextOfferings); setSummaries(nextSummaries)
  }
  useEffect(() => { load().catch(() => null) }, [versionId]) // eslint-disable-line react-hooks/exhaustive-deps

  const offering = offerings.find((item) => item.id === versionId)
  const subject = subjects.find((item) => item.id === offering?.subject_id)
  const department = departments.find((item) => item.id === subject?.department_id)
  const visible = summaries.filter(({ chapter }) => matchesSearch(chapterDisplayName(chapter), search))

  const editChapter = (chapter: SubjectChapter) => {
    const current = normalizeLessonInput(chapterDisplayName(chapter))
    const nextLesson = promptText('Sửa bài, ví dụ 1, 2, 1.1, 1.2', current)
    if (nextLesson === null) return
    const nextTitle = buildChapterTitle(nextLesson) || nextLesson
    run(async () => { await updateSubjectChapter(headers, chapter.id, { title: nextTitle }) }, 'Đã sửa bài', load)
  }
  const removeChapter = (chapter: SubjectChapter) => {
    if (!window.confirm(`Chỉ xóa được khi bài chưa có tài liệu/câu hỏi/release/mapping. Xóa ${chapterDisplayName(chapter)}?`)) return
    run(async () => { await deleteSubjectChapter(headers, chapter.id) }, 'Đã xóa bài', load)
  }

  return <div className="page-stack bank-multipage">
    <Breadcrumb items={[{ label: 'Ngân hàng đề', href: '/bank' }, { label: 'Bộ môn', href: '/bank/departments' }, { label: department?.name || 'Bộ môn', href: department ? `/bank/departments/${department.id}/subjects` : undefined }, { label: subject?.code || 'Môn', href: subject ? `/bank/subjects/${subject.id}/versions` : undefined }, { label: offering?.code || 'Version môn' }, { label: 'Bài' }]} />
    <QuickSearchBox compact />
    {message ? <div className="alert info">{message}</div> : null}
    <section className="card">
      <div className="section-head"><div><h2>{offering ? `Danh sách bài trong ${offering.code}` : 'Danh sách bài trong version môn'}</h2><p className="helper">Click vào bài là vào ngay workspace, không cần bấm bắt đầu.</p></div></div>
      <SearchActionBar search={search} setSearch={setSearch} placeholder="Tìm bài" action={<button className="btn" disabled={!can('subject.update')} onClick={() => setCreateOpen(true)}>+ Thêm bài</button>} />
      <div className="entity-list horizontal multipage-list">
        {visible.map(({ chapter, stats }) => <Link key={chapter.id} href={`/bank/chapters/${chapter.id}`} className={`entity-card link-card ${reviewStatusClass(stats.status)}`}>
          <EntityActions canManage={can('subject.update')} onEdit={() => editChapter(chapter)} onDelete={() => removeChapter(chapter)} />
          <div className="entity-card-head"><b>{chapterDisplayName(chapter)}</b><span className="status-pill">{reviewStatusText(stats.status)}</span></div>
          <StatLine label="Tài liệu" value={stats.material_count || 0} />
          <StatLine label="Tổng câu" value={`${stats.total_questions || 0}/${stats.question_limit || 100}`} />
          <StatLine label="Đã duyệt" value={stats.approved_count || 0} />
          <StatLine label="Chưa duyệt/lỗi" value={stats.unresolved_count || 0} />
          <StatLine label="Release" value={stats.release_status === 'published' ? 'Đã publish' : stats.ready_to_release ? 'Sẵn sàng chốt' : stats.release_count ? 'Đã chốt' : 'Chưa chốt'} />
          {stats.ready_to_release ? <span className="status success">Sẵn sàng chốt bộ đề</span> : null}
        </Link>)}
      </div>
      {!visible.length ? <div className="empty-state">Chưa có bài phù hợp.</div> : null}
    </section>
    <Modal open={createOpen} title="Thêm bài" onClose={() => setCreateOpen(false)}>
      <div className="mini-form">
        <label className="field-label" htmlFor="chapter-lesson-input">Bài:</label>
        <div className="chapter-input-row">
          <span className="input-prefix">Bài</span>
          <input id="chapter-lesson-input" className="input" value={chapterInput} onChange={(event) => setChapterInput(event.target.value)} placeholder="1, 2, 1.1, 1.2..." />
        </div>
        <p className="helper">Ví dụ nhập 1.2, hệ thống tự tạo tên “Bài 1.2”. ID do hệ thống tự sinh.</p>
        <div className="modal-actions">
          <button className="btn secondary" type="button" onClick={() => { setChapterInput(''); setCreateOpen(false) }}>Hủy</button>
          <button className="btn" type="button" disabled={busy || !offering || !normalizeLessonInput(chapterInput)} onClick={() => run(async () => {
            if (!offering) return
            const nextNo = (summaries.reduce((max, item) => Math.max(max, Number(item.chapter.sort_order || item.chapter.chapter_no || 0)), 0) || 0) + 1
            const title = buildChapterTitle(chapterInput)
            await createSubjectChapter(headers, { subject_id: offering.subject_id, subject_offering_id: offering.id, title, sort_order: nextNo })
            setChapterInput(''); setCreateOpen(false)
          }, 'Đã thêm bài', load)}>Tạo bài</button>
        </div>
      </div>
    </Modal>
  </div>
}

