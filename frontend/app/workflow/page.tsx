'use client'

import { useEffect, useMemo, useState } from 'react'
import Link from 'next/link'
import { useAppContext } from '../../context/AppContext'
import { estimateCost, generateQuestions, getChunksPage, getCourseNodes, getQuestionsPage, syncCourse, getCoursePolicy } from '../../lib/api'
import { CourseChunk, CourseNodeOption, Question, QuestionFilters, CoursePolicy } from '../../types'
import { QuestionTable } from '../../components/questions/QuestionTable'
import { ActionMessage, ActionMessageData, toUserError } from '../../components/ui/ActionMessage'
import { LoadingButton } from '../../components/ui/LoadingButton'
import { CostEstimateSummary } from '../../components/ui/CostEstimateSummary'
import { PaginationControls } from '../../components/ui/PaginationControls'

const reviewFilters: QuestionFilters = { status: 'pending_review', difficulty: 'all', nodeId: 'all', sourceType: 'all', search: '', sortBy: 'created_at', sortDir: 'desc' }
const steps = ['Đồng bộ', 'Chọn học liệu', 'Ước tính', 'Tạo câu hỏi', 'Duyệt', 'Xuất']

export default function WorkflowPage() {
  const { courseId, authHeaders, can } = useAppContext()
  const [active, setActive] = useState(0)
  const [nodes, setNodes] = useState<CourseNodeOption[]>([])
  const [chunks, setChunks] = useState<CourseChunk[]>([])
  const [questions, setQuestions] = useState<Question[]>([])
  const [nodeId, setNodeId] = useState('all')
  const [sourceType, setSourceType] = useState('all')
  const [search, setSearch] = useState('')
  const [selectedChunkIds, setSelectedChunkIds] = useState<string[]>([])
  const [selectedChunkMap, setSelectedChunkMap] = useState<Record<string, CourseChunk>>({})
  const [chunkPage, setChunkPage] = useState(1)
  const [chunkPageSize, setChunkPageSize] = useState(20)
  const [chunkTotal, setChunkTotal] = useState(0)
  const [chunkTotalPages, setChunkTotalPages] = useState(1)
  const [questionCount, setQuestionCount] = useState(20)
  const [coursePolicy, setCoursePolicy] = useState<CoursePolicy | null>(null)
  const [easyPercent, setEasyPercent] = useState(50)
  const [mediumPercent, setMediumPercent] = useState(30)
  const [hardPercent, setHardPercent] = useState(20)
  const [estimate, setEstimate] = useState<Record<string, any> | null>(null)
  const [message, setMessage] = useState<ActionMessageData | null>(null)
  const [loadingAction, setLoadingAction] = useState<string | null>(null)
  const selectedChunks = useMemo(() => selectedChunkIds.map((id) => selectedChunkMap[id]).filter(Boolean), [selectedChunkIds, selectedChunkMap])
  const tokenTotal = useMemo(() => selectedChunks.reduce((s, c) => s + c.token_count, 0), [selectedChunks])
  const visibleSelectedCount = useMemo(() => chunks.filter((chunk) => selectedChunkIds.includes(chunk.id)).length, [chunks, selectedChunkIds])
  const hiddenSelectedCount = Math.max(0, selectedChunkIds.length - visibleSelectedCount)
  const contentNodes = useMemo(() => nodes.filter((node) => node.chunk_count > 0), [nodes])

  async function loadNodesAndChunks(showMessage = false, nextPage = chunkPage, nextPageSize = chunkPageSize) {
    setLoadingAction('chunks')
    try {
      const [nextNodes, chunkPageData] = await Promise.all([
        getCourseNodes(courseId, authHeaders()),
        getChunksPage(courseId, sourceType, search, authHeaders(), nodeId, nextPage, nextPageSize),
      ])
      setNodes(nextNodes)
      setChunks(chunkPageData.items)
      setChunkTotal(chunkPageData.total)
      setChunkPage(chunkPageData.page)
      setChunkPageSize(chunkPageData.page_size)
      setChunkTotalPages(chunkPageData.total_pages)
      if (showMessage) setMessage({ type: 'success', body: `Đã tải trang ${chunkPageData.page}/${chunkPageData.total_pages}. Các chunk đã chọn vẫn được giữ theo ID.` })
    } catch (error) {
      setMessage(toUserError(error))
    } finally {
      setLoadingAction(null)
    }
  }
  async function loadReview() {
    const data = await getQuestionsPage(courseId, reviewFilters, authHeaders(), 1, 10)
    setQuestions(data.items)
  }
  useEffect(() => {
    setChunkPage(1)
  }, [courseId, nodeId, sourceType])

  useEffect(() => {
    const timer = window.setTimeout(() => loadNodesAndChunks(false, chunkPage, chunkPageSize), search ? 350 : 0)
    return () => window.clearTimeout(timer)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [courseId, nodeId, sourceType, search, chunkPage, chunkPageSize])


  useEffect(() => {
    getCoursePolicy(courseId, authHeaders()).then((policy) => {
      setCoursePolicy(policy)
      if (questionCount > policy.max_questions_per_job) setQuestionCount(policy.max_questions_per_job)
    }).catch(() => setCoursePolicy(null))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [courseId])

  useEffect(() => {
    setSelectedChunkIds([])
    setSelectedChunkMap({})
    loadReview().catch(() => undefined)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [courseId])
  function toggleChunk(chunk: CourseChunk) {
    setSelectedChunkIds((prev) => {
      if (prev.includes(chunk.id)) {
        setSelectedChunkMap((map) => {
          const next = { ...map }
          delete next[chunk.id]
          return next
        })
        return prev.filter((x) => x !== chunk.id)
      }
      setSelectedChunkMap((map) => ({ ...map, [chunk.id]: chunk }))
      return [...prev, chunk.id]
    })
  }
  function selectVisibleChunks() {
    setSelectedChunkMap((map) => ({ ...map, ...Object.fromEntries(chunks.map((chunk) => [chunk.id, chunk])) }))
    setSelectedChunkIds((prev) => Array.from(new Set([...prev, ...chunks.map((chunk) => chunk.id)])))
  }
  function clearSelectedChunks() { setSelectedChunkIds([]); setSelectedChunkMap({}) }
  function changeChunkPageSize(nextPageSize: number) { setChunkPageSize(nextPageSize); setChunkPage(1) }

  async function doSync() {
    setLoadingAction('sync')
    try {
      setMessage(null)
      await syncCourse(courseId, authHeaders(true))
      await loadNodesAndChunks(true, 1, chunkPageSize)
      setActive(1)
      setMessage({ type: 'success', body: 'Đã sync course và load node/chunk.' })
    } catch (e) { setMessage(toUserError(e)) } finally { setLoadingAction(null) }
  }
  async function doEstimate() {
    if (!selectedChunkIds.length) { setMessage({ type: 'warning', body: 'Cần chọn ít nhất một chunk trước khi estimate.' }); return }
    if (coursePolicy && questionCount > coursePolicy.max_questions_per_job) {
      setMessage({ type: 'warning', body: `Khóa học này chỉ cho tạo tối đa ${coursePolicy.max_questions_per_job} câu mỗi lượt.` })
      return
    }
    setLoadingAction('estimate')
    try {
      const data = await estimateCost({
        course_id: courseId,
        question_count: questionCount,
        batch_size: Math.min(12, questionCount),
        chunk_ids: selectedChunkIds,
        node_ids: nodeId === 'all' ? [] : [nodeId],
        use_node_coverage: true,
        difficulty_percentages: { easy: easyPercent, medium: mediumPercent, hard: hardPercent },
        content_tokens: Math.max(1000, tokenTotal),
      }, authHeaders(true))
      setEstimate(data as Record<string, any>)
      setActive(3)
      setMessage({ type: 'success', body: 'Estimate xong. Có thể Generate.' })
    } catch (e) { setMessage(toUserError(e)) } finally { setLoadingAction(null) }
  }
  async function doGenerate() {
    if (!selectedChunkIds.length) { setMessage({ type: 'warning', body: 'Cần chọn chunk trước khi generate.' }); return }
    if (coursePolicy && questionCount > coursePolicy.max_questions_per_job) {
      setMessage({ type: 'warning', body: `Khóa học này chỉ cho tạo tối đa ${coursePolicy.max_questions_per_job} câu mỗi lượt.` })
      return
    }
    setLoadingAction('generate')
    try {
      const data: any = await generateQuestions({ course_id: courseId, question_count: questionCount, batch_size: Math.min(12, questionCount), chunk_ids: selectedChunkIds, node_ids: nodeId === 'all' ? [] : [nodeId], use_node_coverage: true, difficulty_percentages: { easy: easyPercent, medium: mediumPercent, hard: hardPercent } }, authHeaders(true))
      setMessage({ type: 'success', title: 'Đã tạo job generate', body: `Job ${data?.job_id || data?.id || ''} đã được đưa vào hàng đợi. Mở Job Monitor để theo dõi chi phí thật và trạng thái.` })
      await loadReview(); setActive(4)
    } catch (e) { setMessage(toUserError(e)) } finally { setLoadingAction(null) }
  }

  return <div className="page-stack">
    <section className="hero-card"><div><div className="eyebrow">Quy trình tạo câu hỏi</div><h2>Sync → chọn node/chunks → Estimate → Generate → Review → Export</h2><p>Luồng chính cho giáo viên. Không dùng Topic tự đoán; toàn bộ scope bám theo node/chunk Open edX đã sync.</p></div></section>
    <section className="workflow-steps">{steps.map((step, i) => <button key={step} className={i === active ? 'workflow-step active' : i < active ? 'workflow-step done' : 'workflow-step'} onClick={() => setActive(i)}>{i + 1}. {step}</button>)}</section>
    <ActionMessage message={message} onClose={() => setMessage(null)} />

    {active === 0 && <section className="card"><h2>1. Đồng bộ khóa học</h2><p className="helper">Lấy course tree, block/node và chunks từ Open edX connector. Demo đang dùng mock node-based.</p><LoadingButton className="btn" loading={loadingAction === 'sync'} disabled={!can('sync_course')} onClick={doSync}>Đồng bộ khóa học hiện tại</LoadingButton></section>}

    {active === 1 && <section className="card"><div className="section-head"><div><h2>2. Chọn node và đoạn nội dung</h2><p className="helper">Chọn filter là hệ thống tự load. Các đoạn nội dung đã tick vẫn được giữ theo ID, kể cả khi bị ẩn bởi filter.</p></div><div className="button-row compact"><button className="btn secondary" onClick={() => { setNodeId('all'); setSourceType('all'); setSearch(''); setChunkPage(1) }} disabled={loadingAction === 'chunks'}>Đặt lại bộ lọc</button>{loadingAction === 'chunks' && <span className="soft-tag"><span className="spinner tiny" /> Đang lọc...</span>}</div></div><div className="grid grid-3"><div><label>Node học liệu</label><select className="input" value={nodeId} onChange={(e) => { setNodeId(e.target.value); setChunkPage(1) }}><option value="all">Tất cả node</option>{contentNodes.map((n) => <option key={n.node_id} value={n.node_id}>{'—'.repeat(Math.min(n.depth,5))} {n.title} ({n.chunk_count})</option>)}</select></div><div><label>Loại nguồn</label><select className="input" value={sourceType} onChange={(e) => { setSourceType(e.target.value); setChunkPage(1) }}><option value="all">Tất cả</option><option value="html">html</option><option value="transcript">Phụ đề video</option><option value="problem">Bài quiz/problem</option><option value="file">File</option></select></div><div><label>Tìm kiếm</label><input className="input" value={search} onChange={(e) => { setSearch(e.target.value); setChunkPage(1) }} /></div></div><div className="button-row"><button className="btn small secondary" onClick={selectVisibleChunks}>Chọn trang hiện tại</button><button className="btn small secondary" onClick={clearSelectedChunks}>Bỏ chọn</button><button className="btn" onClick={() => setActive(2)}>Đi tiếp ước tính</button></div><PaginationControls page={chunkPage} pageSize={chunkPageSize} total={chunkTotal} totalPages={chunkTotalPages} onPageChange={setChunkPage} onPageSizeChange={changeChunkPageSize} loading={loadingAction === 'chunks'} label="đoạn nội dung" /><div className="chunk-toolbar"><b>{chunks.length}</b> đoạn đang hiển thị / <b>{chunkTotal}</b> total · <b>{selectedChunkIds.length}</b> đã chọn <span className="muted">({visibleSelectedCount} đang hiển thị{hiddenSelectedCount ? `, ${hiddenSelectedCount} bị ẩn bởi bộ lọc` : ''})</span> · <b>{tokenTotal.toLocaleString('vi-VN')}</b> token đã chọn</div><div className="chunk-list">{chunks.map((chunk) => <label key={chunk.id} className={selectedChunkIds.includes(chunk.id) ? 'chunk-card selected' : 'chunk-card'}><input type="checkbox" checked={selectedChunkIds.includes(chunk.id)} onChange={() => toggleChunk(chunk)} /><div><div className="chunk-title">{chunk.source_type} · {chunk.block_id}</div><small>{chunk.token_count} tokens · {chunk.source_ref}</small><p>{chunk.content.slice(0,240)}...</p></div></label>)}</div><PaginationControls page={chunkPage} pageSize={chunkPageSize} total={chunkTotal} totalPages={chunkTotalPages} onPageChange={setChunkPage} onPageSizeChange={changeChunkPageSize} loading={loadingAction === 'chunks'} label="đoạn nội dung" /></section>}

    {active === 2 && <section className="card"><h2>3. Ước tính chi phí</h2><div className="grid grid-3"><div><label>Số câu</label><input className="input" type="number" min={1} max={200} value={questionCount} onChange={(e) => setQuestionCount(Number(e.target.value))} /></div><div className="metric-card"><span>Đoạn nội dung đã chọn</span><b>{selectedChunkIds.length}</b><small>{visibleSelectedCount} đang hiển thị, {hiddenSelectedCount} bị ẩn · {tokenTotal.toLocaleString('vi-VN')} token đã chọn</small></div><div className="button-column"><LoadingButton className="btn" loading={loadingAction === 'estimate'} disabled={!can('estimate_cost')} onClick={doEstimate}>Ước tính</LoadingButton></div></div><div className="difficulty-grid"><div><label>Dễ %</label><input className="input" type="number" min={0} max={100} value={easyPercent} onChange={(e) => setEasyPercent(Number(e.target.value))} /></div><div><label>Trung bình %</label><input className="input" type="number" min={0} max={100} value={mediumPercent} onChange={(e) => setMediumPercent(Number(e.target.value))} /></div><div><label>Khó %</label><input className="input" type="number" min={0} max={100} value={hardPercent} onChange={(e) => setHardPercent(Number(e.target.value))} /></div></div><p className="helper">Backend sẽ normalize % và dùng Phương pháp phần dư lớn nhất để làm tròn không lệch tổng câu. Mặc định 50/30/20.</p><CostEstimateSummary estimate={estimate} /></section>}

    {active === 3 && <section className="card"><h2>4. Tạo Learning Check</h2><p className="helper">Quá trình tạo sẽ đi qua Kiểm soát chi phí, Cổng gọi model, Kiểm tra chất lượng, Ràng buộc nguồn học liệu và Chống trùng câu hỏi.</p><LoadingButton className="btn" loading={loadingAction === 'generate'} disabled={!can('generate_questions')} onClick={doGenerate}>Tạo {questionCount} câu</LoadingButton></section>}

    {active === 4 && <section className="card"><div className="section-head"><div><h2>5. Review nhanh</h2><p className="helper">Duyệt chi tiết và popup chỉnh sửa nằm ở trang Duyệt câu hỏi.</p></div><Link className="btn" href="/review">Mở trang duyệt câu hỏi</Link></div><QuestionTable questions={questions.slice(0, 10)} canEdit={false} canReview={false} canPublish={false} onEdit={() => undefined} onApprove={() => undefined} onReject={() => undefined} onPublish={() => undefined} onChangeStatus={() => undefined} onPreviewOlx={() => undefined} /></section>}

    {active === 5 && <section className="card"><h2>6. Xuất / Publish</h2><p className="helper">Export OLX/XML cho câu approved. Publish thật sang Open edX vẫn tách rõ với export demo.</p><Link className="btn" href="/export">Sang trang xuất OLX</Link></section>}
  </div>
}
