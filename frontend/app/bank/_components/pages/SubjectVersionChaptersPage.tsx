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

export function SubjectVersionChaptersPage({ versionId }: { versionId: string }) {
  const { headers, can } = useBankData()
  const { message, busy, run } = useAsyncMessage()
  const [departments, setDepartments] = useState<Department[]>([])
  const [subjects, setSubjects] = useState<Subject[]>([])
  const [offerings, setOfferings] = useState<SubjectOffering[]>([])
  const [summaries, setSummaries] = useState<ChapterSummary[]>([])
  const [search, setSearch] = useState('')
  const [statusFilter, setStatusFilter] = useState<BankTableStatusFilter>('all')
  const [createOpen, setCreateOpen] = useState(false)
  const [chapterInput, setChapterInput] = useState('')
  const [editing, setEditing] = useState<SubjectChapter | null>(null)
  const [editLesson, setEditLesson] = useState('')
  const [deleteTarget, setDeleteTarget] = useState<SubjectChapter | null>(null)
  const [deleteBusy, setDeleteBusy] = useState(false)
  const [deleteError, setDeleteError] = useState('')

  const load = async () => {
    const offering = await getSubjectOffering(headers, versionId)
    const [subject, nextSummaries] = await Promise.all([
      getSubject(headers, offering.subject_id),
      getChapterSummaries(headers, versionId),
    ])
    const department = await getDepartment(headers, subject.department_id)
    setDepartments([department]); setSubjects([subject]); setOfferings([offering]); setSummaries(nextSummaries)
  }
  useEffect(() => { load().catch(() => null) }, [versionId]) // eslint-disable-line react-hooks/exhaustive-deps

  const offering = offerings.find((item) => item.id === versionId)
  const subject = subjects.find((item) => item.id === offering?.subject_id)
  const department = departments.find((item) => item.id === subject?.department_id)
  const visible = summaries.filter(({ chapter, stats }) => matchesSearch(chapterDisplayName(chapter), search) && bankStatusMatches(stats, statusFilter))

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
    <Breadcrumb items={[{ label: 'Ngân hàng câu hỏi', href: '/bank' }, { label: 'Bộ môn', href: '/bank/departments' }, { label: department?.name || 'Bộ môn', href: department ? `/bank/departments/${department.id}/subjects` : undefined }, { label: subject?.code || 'Môn', href: subject ? `/bank/subjects/${subject.id}/versions` : undefined }, { label: offering?.code || 'Version môn' }, { label: 'Bài' }]} />
    <QuickSearchBox compact />
    {message ? <div className="alert info">{message}</div> : null}
    <section className="card">
      <div className="section-head"><div><h2>{offering ? `Danh sách bài trong ${offering.code}` : 'Danh sách bài trong version môn'}</h2><p className="helper">Click vào bài là vào ngay workspace, không cần bấm bắt đầu.</p></div></div>
      <BankTableToolbar search={search} setSearch={setSearch} statusFilter={statusFilter} setStatusFilter={setStatusFilter} resultCount={visible.length} totalCount={summaries.length} placeholder="Tìm bài, Final test hoặc Assignment" action={can('subject.update') ? <button className="btn" onClick={() => setCreateOpen(true)}>+ Thêm bài</button> : undefined} />
      <div className="responsive-table-wrap bank-compact-table-wrap">
        <table className="ops-data-table bank-compact-data-table bank-production-table bank-chapter-table">
          <thead><tr><th>STT</th><th>Bài</th><th>Trạng thái</th><th>Tài liệu</th><th>Tổng câu</th><th>Đã duyệt</th><th>Chưa duyệt/lỗi</th><th>Bộ đề</th><th>Thao tác</th></tr></thead>
          <tbody>{visible.map(({ chapter, stats: rawStats }, index) => {
            const stats = rawStats || emptyReviewStats()
            const hasPublished = Boolean(stats.is_published || stats.release_status === 'published' || (stats.published_release_count || 0) > 0)
            return <tr key={chapter.id}>
              <td className="stt-cell">{index + 1}</td>
              <td><Link className="bank-table-link" href={`/bank/chapters/${chapter.id}`}><b>{chapterDisplayName(chapter)}</b><small>{chapter.title || chapterDisplayName(chapter)}</small></Link></td>
              <td><span className={`bank-row-status status-${hasPublished ? 'published' : (stats.status || 'empty')}`}>{hasPublished ? 'Đã đưa lên CMS' : reviewStatusText(stats.status)}</span></td>
              <td>{stats.material_count || 0}</td>
              <td>{stats.total_questions || 0}/{stats.question_limit || 100}</td>
              <td>{stats.approved_count || 0}</td>
              <td>{stats.unresolved_count || 0}</td>
              <td>{hasPublished ? 'Đã đưa lên CMS' : stats.ready_to_release ? 'Sẵn sàng chốt' : stats.release_count ? 'Đã chốt' : 'Chưa chốt'}</td>
              <td><EntityActions variant="inline" canManage={can('subject.update') && !hasPublished} lockedLabel={hasPublished ? 'Đã khóa' : 'Không có quyền'} onEdit={() => openEditChapter(chapter)} onDelete={() => setDeleteTarget(chapter)} /></td>
            </tr>
          })}{!visible.length ? <tr><td colSpan={9}><div className="empty-state">Chưa có bài phù hợp.</div></td></tr> : null}</tbody>
        </table>
      </div>
    </section>

    <Modal open={Boolean(editing)} title="Sửa bài" onClose={() => setEditing(null)}>
      <div className="mini-form">
        <label className="field-label" htmlFor="chapter-edit-lesson-input">Tên bài / Final test / Assignment:</label>
        <input id="chapter-edit-lesson-input" className="input" value={editLesson} onChange={(event) => setEditLesson(event.target.value)} placeholder="1, 2, 1.1, Final test, Assignment..." />
        <p className="helper">Nhập số sẽ tự lưu thành “Bài 1.2”. Nhập “Final test” hoặc “Assignment” sẽ giữ nguyên tên đặc biệt.</p>
        <div className="modal-actions">
          <button className="btn secondary" type="button" disabled={busy} onClick={() => setEditing(null)}>Hủy</button>
          <button className="btn" type="button" disabled={busy || !normalizeLessonInput(editLesson)} onClick={saveEditChapter}>Lưu thay đổi</button>
        </div>
      </div>
    </Modal>
    <ConfirmDialog
      open={Boolean(deleteTarget)}
      title={`Xóa ${deleteTarget ? chapterDisplayName(deleteTarget) : 'bài'}?`}
      description={<p>Chỉ xóa được khi bài chưa có tài liệu thật, câu hỏi, release, mapping hoặc quiz. Bank version rỗng do hệ thống tự tạo sẽ được dọn tự động.</p>}
      confirmLabel="Xác nhận xóa"
      danger
      busy={busy || deleteBusy}
      onClose={() => setDeleteTarget(null)}
      onConfirm={confirmDeleteChapter}
    />

    <Modal open={Boolean(deleteError)} title="Không thể xóa bài/chapter" onClose={() => setDeleteError('')}>
      <div className="mini-form">
        <div className="alert danger">{deleteError}</div>
        <p className="helper">Kiểm tra lại tài liệu, câu hỏi, release, mapping hoặc quiz đang liên kết với bài này.</p>
        <div className="modal-actions">
          <button className="btn" type="button" onClick={() => setDeleteError('')}>Đã hiểu</button>
        </div>
      </div>
    </Modal>

    <Modal open={createOpen} title="Thêm bài" onClose={() => setCreateOpen(false)}>
      <div className="mini-form">
        <label className="field-label" htmlFor="chapter-lesson-input">Tên bài / Final test / Assignment:</label>
        <input id="chapter-lesson-input" className="input" value={chapterInput} onChange={(event) => setChapterInput(event.target.value)} placeholder="1, 2, 1.1, Final test, Assignment..." />
        <p className="helper">Nhập số để tạo “Bài 1.2”. Nhập “Final test” hoặc “Assignment” để tạo đúng tên đặc biệt.</p>
        <div className="modal-actions">
          <button className="btn secondary" type="button" onClick={() => { setChapterInput(''); setCreateOpen(false) }}>Hủy</button>
          <button className="btn" type="button" disabled={busy || !offering || !normalizeLessonInput(chapterInput)} onClick={() => run(async () => {
            if (!offering) return
            const nextNo = (summaries.reduce((max, item) => Math.max(max, Number(item.chapter.sort_order || item.chapter.chapter_no || 0)), 0) || 0) + 1
            const title = buildChapterTitle(chapterInput)
            const created = await createSubjectChapter(headers, { subject_id: offering.subject_id, subject_offering_id: offering.id, title, sort_order: nextNo })
            setSummaries((current) => {
              const withoutDuplicate = current.filter((item) => item.chapter.id !== created.id)
              return [...withoutDuplicate, { chapter: created, stats: emptyReviewStats({ material_count: 0, bank_version_count: 0, release_count: 0, question_limit: 100 }) }].sort((a, b) => Number(a.chapter.sort_order || a.chapter.chapter_no || 0) - Number(b.chapter.sort_order || b.chapter.chapter_no || 0))
            })
            setChapterInput(''); setCreateOpen(false)
            await load()
            window.setTimeout(() => { load().catch(() => null) }, 500)
          }, 'Đã thêm bài')}>Tạo bài</button>
        </div>
      </div>
    </Modal>
  </div>
}

