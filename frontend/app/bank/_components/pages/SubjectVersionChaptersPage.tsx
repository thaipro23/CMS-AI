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
  const [editing, setEditing] = useState<SubjectChapter | null>(null)
  const [editLesson, setEditLesson] = useState('')
  const [deleteTarget, setDeleteTarget] = useState<SubjectChapter | null>(null)
  const [deleteBusy, setDeleteBusy] = useState(false)
  const [deleteError, setDeleteError] = useState('')

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

  const openEditChapter = (chapter: SubjectChapter) => {
    setEditing(chapter)
    setEditLesson(normalizeLessonInput(chapterDisplayName(chapter)))
  }
  const saveEditChapter = () => {
    if (!editing) return
    const nextTitle = buildChapterTitle(editLesson) || editLesson.trim()
    run(async () => {
      await updateSubjectChapter(headers, editing.id, { title: nextTitle })
      setEditing(null)
    }, 'Đã sửa bài', load)
  }
  const confirmDeleteChapter = async () => {
    if (!deleteTarget) return
    setDeleteBusy(true)
    setDeleteError('')
    try {
      await deleteSubjectChapter(headers, deleteTarget.id)
      setDeleteTarget(null)
      await load()
      // One extra refresh avoids a stale summary/cache row right after delete.
      window.setTimeout(() => { load().catch(() => null) }, 250)
    } catch (error) {
      setDeleteTarget(null)
      setDeleteError(error instanceof Error ? error.message : 'Không thể xóa bài/chapter')
    } finally {
      setDeleteBusy(false)
    }
  }

  return <div className="page-stack bank-multipage">
    <Breadcrumb items={[{ label: 'Ngân hàng đề', href: '/bank' }, { label: 'Bộ môn', href: '/bank/departments' }, { label: department?.name || 'Bộ môn', href: department ? `/bank/departments/${department.id}/subjects` : undefined }, { label: subject?.code || 'Môn', href: subject ? `/bank/subjects/${subject.id}/versions` : undefined }, { label: offering?.code || 'Version môn' }, { label: 'Bài' }]} />
    <QuickSearchBox compact />
    {message ? <div className="alert info">{message}</div> : null}
    <section className="card">
      <div className="section-head"><div><h2>{offering ? `Danh sách bài trong ${offering.code}` : 'Danh sách bài trong version môn'}</h2><p className="helper">Click vào bài là vào ngay workspace, không cần bấm bắt đầu.</p></div></div>
      <SearchActionBar search={search} setSearch={setSearch} placeholder="Tìm bài" action={<button className="btn" disabled={!can('subject.update')} onClick={() => setCreateOpen(true)}>+ Thêm bài</button>} />
      <div className="entity-list horizontal multipage-list">
        {visible.map(({ chapter, stats }) => {
          const hasPublished = Boolean(stats.is_published || stats.release_status === 'published' || (stats.published_release_count || 0) > 0)
          return <Link key={chapter.id} href={`/bank/chapters/${chapter.id}`} className={`entity-card link-card ${reviewStatusClass(hasPublished ? 'published' : stats.status)}`}>
            <EntityActions canManage={can('subject.update') && !hasPublished} onEdit={() => openEditChapter(chapter)} onDelete={() => setDeleteTarget(chapter)} />
            <div className="entity-card-head"><b>{chapterDisplayName(chapter)}</b><span className="status-pill">{hasPublished ? 'Đã publish' : reviewStatusText(stats.status)}</span></div>
            <StatLine label="Tài liệu" value={stats.material_count || 0} />
            <StatLine label="Tổng câu" value={`${stats.total_questions || 0}/${stats.question_limit || 100}`} />
            <StatLine label="Đã duyệt" value={stats.approved_count || 0} />
            <StatLine label="Chưa duyệt/lỗi" value={stats.unresolved_count || 0} />
            <StatLine label="Release" value={hasPublished ? 'Đã publish' : stats.ready_to_release ? 'Sẵn sàng chốt' : stats.release_count ? 'Đã chốt' : 'Chưa chốt'} />
            {hasPublished ? <span className="status success">Đã khóa chỉnh sửa</span> : stats.ready_to_release ? <span className="status success">Sẵn sàng chốt bộ đề</span> : null}
          </Link>
        })}
      </div>
      {!visible.length ? <div className="empty-state">Chưa có bài phù hợp.</div> : null}
    </section>

    <Modal open={Boolean(editing)} title="Sửa bài" onClose={() => setEditing(null)}>
      <div className="mini-form">
        <label className="field-label" htmlFor="chapter-edit-lesson-input">Bài:</label>
        <div className="chapter-input-row">
          <span className="input-prefix">Bài</span>
          <input id="chapter-edit-lesson-input" className="input" value={editLesson} onChange={(event) => setEditLesson(event.target.value)} placeholder="1, 2, 1.1, 1.2..." />
        </div>
        <p className="helper">Ví dụ nhập 1.2, hệ thống tự lưu thành “Bài 1.2”.</p>
        <div className="modal-actions">
          <button className="btn secondary" type="button" disabled={busy} onClick={() => setEditing(null)}>Hủy</button>
          <button className="btn" type="button" disabled={busy || !normalizeLessonInput(editLesson)} onClick={saveEditChapter}>Lưu thay đổi</button>
        </div>
      </div>
    </Modal>
    <ConfirmDialog
      open={Boolean(deleteTarget)}
      title={`Xóa ${deleteTarget ? chapterDisplayName(deleteTarget) : 'bài'}?`}
      description={<p>Chỉ xóa được khi bài chưa có tài liệu/câu hỏi/release/mapping. Nếu bài chỉ có bank version rỗng do vừa mở workspace, hệ thống sẽ tự dọn và vẫn cho xóa.</p>}
      confirmLabel="Xác nhận xóa"
      danger
      busy={busy || deleteBusy}
      onClose={() => setDeleteTarget(null)}
      onConfirm={confirmDeleteChapter}
    />

    <Modal open={Boolean(deleteError)} title="Không thể xóa bài/chapter" onClose={() => setDeleteError('')}>
      <div className="mini-form">
        <div className="alert danger">{deleteError}</div>
        <p className="helper">Bài chỉ xóa được khi không còn tài liệu thật, câu hỏi, release, mapping hoặc quiz. Các bản ghi rỗng/đã xóa sẽ được backend tự dọn.</p>
        <div className="modal-actions">
          <button className="btn" type="button" onClick={() => setDeleteError('')}>Đã hiểu</button>
        </div>
      </div>
    </Modal>

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

