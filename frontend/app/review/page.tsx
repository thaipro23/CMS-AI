'use client'

import { useEffect, useMemo, useState } from 'react'
import { useRouter } from 'next/navigation'
import { bulkApprove, changeQuestionStatus, deleteQuestion, getQuestionOlx,
  getQuestionSourceTrace, getQuestionsPage, transitionQuestion, updateQuestion, publishQuestionToOpenEdx, repairDraftError, keepDraftErrorAnyway } from '../../lib/api'
import { EditQuestionForm, Question, QuestionFilters, SourceTrace, toEditForm } from '../../types'
import { useAppContext } from '../../context/AppContext'
import { QuestionTable } from '../../components/questions/QuestionTable'
import { QuestionEditPanel } from '../../components/questions/QuestionEditPanel'
import { ActionMessage, ActionMessageData, toUserError } from '../../components/ui/ActionMessage'
import { LoadingButton } from '../../components/ui/LoadingButton'
import { PaginationControls } from '../../components/ui/PaginationControls'

const filters: QuestionFilters = { status: 'all', difficulty: 'all', nodeId: 'all', sourceType: 'all', search: '', sortBy: 'created_at', sortDir: 'desc' }

export default function ReviewPage() {
  const router = useRouter()
  const { courseId, authHeaders, can } = useAppContext()
  const [questions, setQuestions] = useState<Question[]>([])
  const [selectedIds, setSelectedIds] = useState<string[]>([])
  const [editingQuestion, setEditingQuestion] = useState<Question | null>(null)
  const [editForm, setEditForm] = useState<EditQuestionForm | null>(null)
  const [message, setMessage] = useState<ActionMessageData | null>(null)
  const [loading, setLoading] = useState(false)
  const [bulkLoading, setBulkLoading] = useState<string | null>(null)
  const [actionLoading, setActionLoading] = useState<string | null>(null)
  const [sourceTrace, setSourceTrace] = useState<SourceTrace | null>(null)
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(20)
  const [total, setTotal] = useState(0)
  const [totalPages, setTotalPages] = useState(1)
  const pendingQuestions = useMemo(() => questions.filter((question) => question.status === 'pending_review' || question.status === 'needs_review'), [questions])

  async function load(nextPage = page, nextPageSize = pageSize) {
    setLoading(true)
    try {
      const data = await getQuestionsPage(courseId, filters, authHeaders(), nextPage, nextPageSize)
      setQuestions(data.items)
      setTotal(data.total)
      setPage(data.page)
      setPageSize(data.page_size)
      setTotalPages(data.total_pages)
      // Không clear selectedIds khi đổi trang. Selection được giữ theo question id.
    } catch (error) {
      setMessage(toUserError(error))
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    setPage(1)
    setSelectedIds([])
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [courseId])

  useEffect(() => { load(page, pageSize) }, [courseId, page, pageSize])

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
      await load(page, pageSize)
    } catch (error) {
      setMessage(toUserError(error))
    } finally {
      setActionLoading(null)
    }
  }

  async function approveSelected() {
    setBulkLoading('selected')
    try {
      const data: any = await bulkApprove({ note: 'Duyệt các câu đã chọn', question_ids: selectedIds }, authHeaders(true))
      const count = data?.updated_count ?? data?.approved_count ?? selectedIds.length
      setMessage({ type: 'success', body: `Đã duyệt ${count} câu hỏi đã chọn.` })
      setSelectedIds([])
      await load(page, pageSize)
    } catch (error) {
      setMessage(toUserError(error))
    } finally {
      setBulkLoading(null)
    }
  }

  async function approveAllPending() {
    setBulkLoading('all')
    try {
      const data: any = await bulkApprove({ note: 'Duyệt tất cả câu đang chờ trong khóa học', course_id: courseId, approve_all_pending: true }, authHeaders(true))
      const count = data?.updated_count ?? data?.approved_count ?? pendingQuestions.length
      setMessage({ type: 'success', body: `Đã duyệt ${count} câu hỏi đang chờ trong khóa học.` })
      setSelectedIds([])
      await load(page, pageSize)
    } catch (error) {
      setMessage(toUserError(error))
    } finally {
      setBulkLoading(null)
    }
  }

  async function runQuestionAction(questionId: string, action: string, callback: () => Promise<void>, successBody?: string) {
    setActionLoading(`${questionId}:${action}`)
    try {
      await callback()
      if (successBody) setMessage({ type: 'success', body: successBody })
      await load(page, pageSize)
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

  async function showSourceTrace(question: Question) {
    setActionLoading(`${question.id}:source`)
    try {
      const data = await getQuestionSourceTrace(question.id, authHeaders())
      setSourceTrace(data)
    } catch (error) {
      setMessage(toUserError(error))
    } finally {
      setActionLoading(null)
    }
  }

  async function handleRepair(question: Question) {
    await runQuestionAction(question.id, 'repair', async () => {
      const updated = await repairDraftError(question.id, authHeaders(true))
      if (updated.status === 'draft_error') setMessage({ type: 'warning', body: `Repair xong nhưng vẫn lỗi: ${updated.draft_error_reason || 'unknown'}` })
    }, 'Đã repair câu hỏi.')
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
      <div><h2>Hàng chờ duyệt câu hỏi</h2><p className="helper">Chỉ hiển thị câu hỏi đang chờ duyệt. Có thể tick để duyệt nhanh hoặc chỉnh từng câu.</p></div>
      <div className="button-row compact">
        <button className="btn secondary" disabled={loading || Boolean(bulkLoading)} onClick={() => setSelectedIds(Array.from(new Set([...selectedIds, ...pendingQuestions.map((question) => question.id)])))}>Chọn câu đang hiển thị</button>
        <button className="btn secondary" disabled={loading || Boolean(bulkLoading) || !selectedIds.length} onClick={() => setSelectedIds([])}>Bỏ chọn</button>
        <LoadingButton className="btn" loading={bulkLoading === 'selected'} disabled={!selectedIds.length || !can('review_questions') || Boolean(bulkLoading)} onClick={approveSelected}>Duyệt câu đã chọn ({selectedIds.length})</LoadingButton>
        <LoadingButton className="btn secondary" loading={bulkLoading === 'all'} disabled={!can('review_questions') || Boolean(bulkLoading)} onClick={approveAllPending}>Duyệt tất cả câu đang chờ</LoadingButton>
      </div>
    </section>
    <ActionMessage message={message} onClose={() => setMessage(null)} />
    <section className={loading ? 'card loading-overlay' : 'card'}>
      <PaginationControls page={page} pageSize={pageSize} total={total} totalPages={totalPages} onPageChange={setPage} onPageSizeChange={changePageSize} loading={loading} label="câu pending" />
      <div className="selection-summary">Đã chọn <b>{selectedIds.length}</b> câu · <span className="muted">{pendingQuestions.filter((q) => selectedIds.includes(q.id)).length} đang hiển thị, {Math.max(0, selectedIds.length - pendingQuestions.filter((q) => selectedIds.includes(q.id)).length)} đang ở trang/filter khác</span></div>
      {loading && <div className="inline-loading"><span className="spinner" />Đang tải danh sách câu hỏi...</div>}
      <QuestionTable
        questions={pendingQuestions}
        withCheckbox
        selectedIds={selectedIds}
        onToggleSelect={(id) => setSelectedIds((previous) => previous.includes(id) ? previous.filter((item) => item !== id) : [...previous, id])}
        canEdit={can('edit_questions')}
        canReview={can('review_questions')}
        canPublish={can('publish_to_openedx')} canDelete={can('delete_questions')}
        onEdit={startEdit}
        onApprove={(id) => transition(id, 'approve')}
        onReject={(id) => transition(id, 'reject')}
        onPublish={(id) => transition(id, 'publish')}
        onChangeStatus={handleChangeStatus}
        onPreviewOlx={previewOlx}
        onSourceTrace={showSourceTrace}
        onDelete={handleDelete}
        onRepair={handleRepair}
        onKeepAnyway={handleKeepAnyway}
        actionLoading={actionLoading}
        startIndex={(page - 1) * pageSize}
      />
      <PaginationControls page={page} pageSize={pageSize} total={total} totalPages={totalPages} onPageChange={setPage} onPageSizeChange={changePageSize} loading={loading} label="câu pending" />
    </section>
    {sourceTrace && <div className="modal-backdrop"><section className="card modal-card source-trace-modal">
      <div className="section-head"><div><h2>Source trace</h2><p className="helper">Nguồn học liệu mà AI dùng để sinh câu hỏi.</p></div><button className="btn secondary" onClick={() => setSourceTrace(null)}>Đóng</button></div>
      <div className="grid grid-3">
        <div><span className="box-label">Node gốc</span><b>{sourceTrace.source_node?.title || sourceTrace.source_node?.id || '—'}</b><small>{sourceTrace.source_node?.block_type || ''}</small></div>
        <div><span className="box-label">Chapter</span><b>{sourceTrace.chapter_node?.title || sourceTrace.chapter_node?.id || '—'}</b><small>{sourceTrace.chapter_node?.block_type || ''}</small></div>
        <div><span className="box-label">Chunk</span><b>{sourceTrace.chunk?.source_type || '—'}</b><small>{sourceTrace.chunk?.id || ''}</small></div>
      </div>
      <label>Nguồn tham chiếu</label><input className="input" readOnly value={sourceTrace.chunk?.source_ref || ''} />
      <label>Nội dung chunk/source excerpt</label><pre className="xml-preview source-preview">{sourceTrace.chunk?.content || sourceTrace.question_source_excerpt || 'Không có source excerpt.'}</pre>
      <label>Publish trace</label><pre className="xml-preview source-preview small-preview">{JSON.stringify(sourceTrace.publish_trace || {}, null, 2)}</pre>
    </section></div>}
    {editingQuestion && editForm && <QuestionEditPanel question={editingQuestion} form={editForm} canEdit={can('edit_questions')} onChange={updateEdit} onSave={saveEdit} onCancel={() => { setEditingQuestion(null); setEditForm(null) }} />}
  </div>
}
