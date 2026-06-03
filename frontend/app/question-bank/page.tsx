'use client'

import { useEffect, useState } from 'react'
import { useRouter } from 'next/navigation'
import { changeQuestionStatus, deleteQuestion, getQuestionOlx, getQuestionsPage, getQuestionStats, transitionQuestion, updateQuestion, publishQuestionToOpenEdx, repairDraftError, keepDraftErrorAnyway, getQuestionDiversityReport } from '../../lib/api'
import { EditQuestionForm, Question, QuestionFilters, QuestionStats, toEditForm } from '../../types'
import { useAppContext } from '../../context/AppContext'
import { DEFAULT_FILTERS, QuestionFiltersBar } from '../../components/questions/QuestionFilters'
import { QuestionTable } from '../../components/questions/QuestionTable'
import { QuestionEditPanel } from '../../components/questions/QuestionEditPanel'
import { ActionMessage, ActionMessageData, toUserError } from '../../components/ui/ActionMessage'
import { LoadingButton } from '../../components/ui/LoadingButton'
import { DiversityReportPanel } from '../../components/questions/DiversityReportPanel'
import { PaginationControls } from '../../components/ui/PaginationControls'

export default function QuestionBankPage() {
  const router = useRouter()
  const { courseId, authHeaders, can } = useAppContext()
  const [filters, setFilters] = useState<QuestionFilters>(DEFAULT_FILTERS)
  const [questions, setQuestions] = useState<Question[]>([])
  const [stats, setStats] = useState<QuestionStats | null>(null)
  const [editingQuestion, setEditingQuestion] = useState<Question | null>(null)
  const [editForm, setEditForm] = useState<EditQuestionForm | null>(null)
  const [message, setMessage] = useState<ActionMessageData | null>(null)
  const [diversity, setDiversity] = useState<any>(null)
  const [loading, setLoading] = useState(false)
  const [loadingDiversity, setLoadingDiversity] = useState(false)
  const [actionLoading, setActionLoading] = useState<string | null>(null)
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(20)
  const [total, setTotal] = useState(0)
  const [totalPages, setTotalPages] = useState(1)

  async function load(nextFilters: QuestionFilters = filters, nextPage = page, nextPageSize = pageSize) {
    setLoading(true)
    try {
      setMessage(null)
      const [pageData, statsData] = await Promise.all([
        getQuestionsPage(courseId, nextFilters, authHeaders(), nextPage, nextPageSize),
        getQuestionStats(courseId, authHeaders()),
      ])
      setQuestions(pageData.items)
      setTotal(pageData.total)
      setPage(pageData.page)
      setPageSize(pageData.page_size)
      setTotalPages(pageData.total_pages)
      setStats(statsData)
    } catch (error) {
      setMessage(toUserError(error))
    } finally {
      setLoading(false)
    }
  }

  async function loadDiversity() {
    setLoadingDiversity(true)
    try {
      const data = await getQuestionDiversityReport(courseId, authHeaders())
      setDiversity(data)
      setMessage({ type: 'success', title: 'Đã tạo báo cáo diversity', body: 'Báo cáo đã được hiển thị bên dưới bằng dạng dễ đọc thay vì JSON thô.' })
    } catch (error) {
      setMessage(toUserError(error))
    } finally {
      setLoadingDiversity(false)
    }
  }

  useEffect(() => {
    setFilters(DEFAULT_FILTERS)
    setDiversity(null)
    setPage(1)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [courseId])

  useEffect(() => {
    const timer = window.setTimeout(() => load(filters, page, pageSize), filters.search ? 350 : 0)
    return () => window.clearTimeout(timer)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [courseId, filters, page, pageSize])

  function updateFilters(nextFilters: QuestionFilters) {
    setPage(1)
    setFilters(nextFilters)
  }

  function resetFilters() {
    setPage(1)
    setFilters(DEFAULT_FILTERS)
  }

  function changePageSize(nextPageSize: number) {
    setPageSize(nextPageSize)
    setPage(1)
  }

  function startEdit(question: Question) {
    setEditingQuestion(question)
    setEditForm(toEditForm(question))
  }

  function updateEdit<K extends keyof EditQuestionForm>(key: K, value: EditQuestionForm[K]) {
    if (!editForm) return
    setEditForm({ ...editForm, [key]: value })
  }

  async function runQuestionAction(questionId: string, action: string, callback: () => Promise<void>, successBody?: string) {
    setActionLoading(`${questionId}:${action}`)
    try {
      await callback()
      if (successBody) setMessage({ type: 'success', body: successBody })
      await load(filters, page, pageSize)
    } catch (error) {
      setMessage(toUserError(error))
    } finally {
      setActionLoading(null)
    }
  }

  async function saveEdit() {
    if (!editingQuestion || !editForm) return
    setActionLoading(`${editingQuestion.id}:edit`)
    try {
      const updated = await updateQuestion(editingQuestion.id, editForm, authHeaders(true))
      if (editForm.target_status !== updated.status && updated.status !== 'draft_error') {
        await changeQuestionStatus(editingQuestion.id, editForm.target_status, 'Giáo viên đổi trạng thái trong form chỉnh sửa', authHeaders(true))
      }
      setEditingQuestion(null)
      setEditForm(null)
      setMessage({ type: 'success', body: 'Đã lưu câu hỏi.' })
      await load(filters, page, pageSize)
    } catch (error) {
      setMessage(toUserError(error))
    } finally {
      setActionLoading(null)
    }
  }

  async function transition(id: string, action: 'approve' | 'reject' | 'publish') {
    const label = action === 'approve' ? 'Đã duyệt câu hỏi.' : action === 'reject' ? 'Đã từ chối câu hỏi.' : 'Đã publish câu hỏi sang Open edX.'
    await runQuestionAction(id, action, async () => {
      if (action === 'publish') await publishQuestionToOpenEdx(id, authHeaders(true))
      else await transitionQuestion(id, action, authHeaders(true))
    }, label)
  }

  async function handleChangeStatus(id: string, status: string, note: string) {
    const action = status === 'pending_review' ? 'undo' : status
    await runQuestionAction(id, action, async () => {
      await changeQuestionStatus(id, status, note, authHeaders(true))
    }, 'Đã cập nhật trạng thái câu hỏi.')
  }

  async function previewOlx(id: string) {
    setActionLoading(`${id}:olx`)
    try {
      const data = await getQuestionOlx(id, authHeaders())
      window.localStorage.setItem('ai_openedx_olx_preview', data.olx)
      router.push('/export')
    } catch (error) {
      setMessage(toUserError(error))
      setActionLoading(null)
    }
  }

  async function handleRepair(question: Question) {
    await runQuestionAction(question.id, 'repair', async () => {
      const updated = await repairDraftError(question.id, authHeaders(true))
      if (updated.status === 'draft_error') {
        setMessage({ type: 'warning', title: 'Repair chưa hết lỗi', body: `Câu hỏi vẫn còn lỗi: ${updated.draft_error_reason || 'unknown'}` })
      }
    }, 'Đã repair câu hỏi và chuyển về hàng chờ duyệt nếu hợp lệ.')
  }

  async function handleKeepAnyway(question: Question) {
    await runQuestionAction(question.id, 'keep', async () => {
      await keepDraftErrorAnyway(question.id, authHeaders(true))
    }, 'Đã giữ câu hỏi và chuyển về pending_review để giáo viên duyệt.')
  }

  async function handleDelete(question: Question) {
    if (!window.confirm(`Xóa câu hỏi này khỏi AI Server?\n\n${question.question_text.slice(0, 120)}${question.question_text.length > 120 ? '...' : ''}`)) return
    await runQuestionAction(question.id, 'delete', async () => {
      await deleteQuestion(question.id, authHeaders(true))
    }, 'Đã xóa câu hỏi khỏi AI Server.')
  }

  return <div className="page-stack">
    <section className="card page-intro">
      <div><h2>Ngân hàng câu hỏi</h2><p className="helper">Ngân hàng câu hỏi theo course, có filter/search/sort và phân trang. Filter tự load, không dùng JSON thô.</p></div>
      <div className="button-row compact">
        <LoadingButton className="btn secondary" loading={loadingDiversity} loadingLabel="Đang phân tích..." onClick={loadDiversity}>Diversity</LoadingButton>
        <LoadingButton className="btn secondary" loading={loading} loadingLabel="Đang tải..." onClick={() => load(filters, page, pageSize)}>Refresh</LoadingButton>
      </div>
    </section>
    {stats && <section className="summary-grid"><div><span>Tổng</span><b>{stats.total}</b></div><div><span>Chờ duyệt</span><b>{stats.pending_review}</b></div><div><span>Đã duyệt</span><b>{stats.approved}</b></div><div><span>Đã từ chối</span><b>{stats.rejected}</b></div><div><span>Đã publish</span><b>{stats.published}</b></div><div><span>Lỗi draft</span><b>{stats.draft_error}</b></div></section>}
    <QuestionFiltersBar filters={filters} onChange={updateFilters} onReset={resetFilters} loading={loading} />
    <ActionMessage message={message} onClose={() => setMessage(null)} />
    <DiversityReportPanel report={diversity} />
    <section className={loading ? 'card loading-overlay' : 'card'}>
      <PaginationControls page={page} pageSize={pageSize} total={total} totalPages={totalPages} onPageChange={setPage} onPageSizeChange={changePageSize} loading={loading} label="câu hỏi" />
      {loading && <div className="inline-loading"><span className="spinner" />Đang tải danh sách câu hỏi...</div>}
      <QuestionTable questions={questions} startIndex={(page - 1) * pageSize} canEdit={can('edit_questions')} canReview={can('review_questions')} canPublish={can('publish_to_openedx')} canDelete={can('delete_questions')} onEdit={startEdit} onApprove={(id) => transition(id, 'approve')} onReject={(id) => transition(id, 'reject')} onPublish={(id) => transition(id, 'publish')} onChangeStatus={handleChangeStatus} onPreviewOlx={previewOlx} onDelete={handleDelete} onRepair={handleRepair} onKeepAnyway={handleKeepAnyway} actionLoading={actionLoading} />
      <PaginationControls page={page} pageSize={pageSize} total={total} totalPages={totalPages} onPageChange={setPage} onPageSizeChange={changePageSize} loading={loading} label="câu hỏi" />
    </section>
    {editingQuestion && editForm && <QuestionEditPanel question={editingQuestion} form={editForm} canEdit={can('edit_questions')} onChange={updateEdit} onSave={saveEdit} onCancel={() => { setEditingQuestion(null); setEditForm(null) }} />}
  </div>
}
