'use client'

import { useEffect, useMemo, useState } from 'react'
import { useAppContext } from '../../context/AppContext'
import { estimateCost, generateQuestions, getChunksPage, getCourseNodes, getCoursePolicy } from '../../lib/api'
import { CourseChunk, CourseNodeOption, CoursePolicy } from '../../types'
import { ActionMessage, ActionMessageData, toUserError } from '../../components/ui/ActionMessage'
import { LoadingButton } from '../../components/ui/LoadingButton'
import { CostEstimateSummary } from '../../components/ui/CostEstimateSummary'
import { PaginationControls } from '../../components/ui/PaginationControls'

function sourceLabel(source: 'manual' | 'chunks') {
  return source === 'manual' ? 'Nhập nội dung thủ công' : 'Dùng node/chunk đã sync'
}

export default function GeneratePage() {
  const { courseId, authHeaders, can } = useAppContext()
  const [questionCount, setQuestionCount] = useState(20)
  const [coursePolicy, setCoursePolicy] = useState<CoursePolicy | null>(null)
  const [easyPercent, setEasyPercent] = useState(50)
  const [mediumPercent, setMediumPercent] = useState(30)
  const [hardPercent, setHardPercent] = useState(20)
  const [generationSource, setGenerationSource] = useState<'manual' | 'chunks'>('chunks')
  const [content, setContent] = useState('REST API sử dụng HTTP methods như GET, POST, PUT, DELETE. GET dùng để lấy dữ liệu. POST dùng để tạo mới tài nguyên.')
  const [chunks, setChunks] = useState<CourseChunk[]>([])
  const [nodes, setNodes] = useState<CourseNodeOption[]>([])
  const [nodeId, setNodeId] = useState('all')
  const [chunkSearch, setChunkSearch] = useState('')
  const [chunkSourceType, setChunkSourceType] = useState('all')
  const [selectedChunkIds, setSelectedChunkIds] = useState<string[]>([])
  const [selectedChunkMap, setSelectedChunkMap] = useState<Record<string, CourseChunk>>({})
  const [chunkPage, setChunkPage] = useState(1)
  const [chunkPageSize, setChunkPageSize] = useState(20)
  const [chunkTotal, setChunkTotal] = useState(0)
  const [chunkTotalPages, setChunkTotalPages] = useState(1)
  const [useNodeCoverage, setUseNodeCoverage] = useState(true)
  const [estimate, setEstimate] = useState<Record<string, any> | null>(null)
  const [message, setMessage] = useState<ActionMessageData | null>(null)
  const [loadingAction, setLoadingAction] = useState<string | null>(null)

  const selectedChunks = useMemo(() => selectedChunkIds.map((id) => selectedChunkMap[id]).filter(Boolean), [selectedChunkIds, selectedChunkMap])
  const selectedNodes = useMemo(() => nodeId === 'all' ? [] : [nodeId], [nodeId])
  const generationContent = useMemo(() => {
    if (generationSource === 'manual') return content
    return selectedChunks.map((chunk, index) => `[#${index + 1}] Source: ${chunk.source_ref || chunk.block_id}\nType: ${chunk.source_type}\nChunkId: ${chunk.id}\nBlockId: ${chunk.block_id}\n${chunk.content}`).join('\n\n---\n\n')
  }, [generationSource, content, selectedChunks])
  const estimatedContentTokens = useMemo(() => Math.max(1000, Math.ceil(generationContent.length / 3)), [generationContent])
  const selectedTokenTotal = useMemo(() => selectedChunks.reduce((sum, chunk) => sum + chunk.token_count, 0), [selectedChunks])
  const visibleSelectedCount = useMemo(() => chunks.filter((chunk) => selectedChunkIds.includes(chunk.id)).length, [chunks, selectedChunkIds])
  const hiddenSelectedCount = Math.max(0, selectedChunkIds.length - visibleSelectedCount)
  const contentNodes = useMemo(() => nodes.filter((node) => node.chunk_count > 0), [nodes])

  async function loadChunks(showMessage = false, nextPage = chunkPage, nextPageSize = chunkPageSize) {
    setLoadingAction('chunks')
    try {
      const [chunkPageData, nextNodes] = await Promise.all([
        getChunksPage(courseId, chunkSourceType, chunkSearch, authHeaders(), nodeId, nextPage, nextPageSize),
        getCourseNodes(courseId, authHeaders()),
      ])
      setChunks(chunkPageData.items)
      setChunkTotal(chunkPageData.total)
      setChunkPage(chunkPageData.page)
      setChunkPageSize(chunkPageData.page_size)
      setChunkTotalPages(chunkPageData.total_pages)
      setNodes(nextNodes)
      if (showMessage) setMessage({ type: 'success', body: `Đã tải trang ${chunkPageData.page}/${chunkPageData.total_pages}. Các chunk đã tick vẫn được giữ theo ID.` })
    } catch (error) {
      setMessage(toUserError(error))
    } finally {
      setLoadingAction(null)
    }
  }

  useEffect(() => {
    setChunkPage(1)
  }, [courseId, nodeId, chunkSourceType])

  useEffect(() => {
    const timer = window.setTimeout(() => loadChunks(false, chunkPage, chunkPageSize), chunkSearch ? 350 : 0)
    return () => window.clearTimeout(timer)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [courseId, nodeId, chunkSourceType, chunkSearch, chunkPage, chunkPageSize])


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
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [courseId])

  function changeChunkPageSize(nextPageSize: number) {
    setChunkPageSize(nextPageSize)
    setChunkPage(1)
  }

  async function handleEstimate() {
    if (generationSource === 'chunks' && !selectedChunkIds.length) {
      setMessage({ type: 'warning', body: 'Bạn đang chọn Chế độ chunk học liệu nhưng chưa chọn chunk nào.' })
      return
    }
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
        content: generationSource === 'manual' ? generationContent : undefined,
        chunk_ids: generationSource === 'chunks' ? selectedChunkIds : undefined,
        node_ids: generationSource === 'chunks' ? selectedNodes : undefined,
        use_node_coverage: useNodeCoverage,
        difficulty_percentages: { easy: easyPercent, medium: mediumPercent, hard: hardPercent },
        content_tokens: estimatedContentTokens,
      }, authHeaders(true))
      setEstimate(data as Record<string, any>)
      setMessage({ type: 'success', body: 'Estimate complete. Hãy kiểm tra quota/cost trước khi Generate.' })
    } catch (error) {
      setMessage(toUserError(error))
    } finally {
      setLoadingAction(null)
    }
  }

  async function handleGenerate() {
    if (generationSource === 'manual' && !content.trim()) {
      setMessage({ type: 'warning', body: 'Vui lòng nhập nội dung bài học hoặc chuyển sang Chế độ chunk học liệu.' })
      return
    }
    if (generationSource === 'chunks' && !selectedChunkIds.length) {
      setMessage({ type: 'warning', body: 'Vui lòng chọn ít nhất một course chunk đã sync.' })
      return
    }
    if (coursePolicy && questionCount > coursePolicy.max_questions_per_job) {
      setMessage({ type: 'warning', body: `Khóa học này chỉ cho tạo tối đa ${coursePolicy.max_questions_per_job} câu mỗi lượt.` })
      return
    }
    setLoadingAction('generate')
    try {
      setMessage({ type: 'info', body: 'Đang tạo generation job theo node Open edX...' })
      const data: any = await generateQuestions({
        course_id: courseId,
        question_count: questionCount,
        batch_size: Math.min(12, questionCount),
        content: generationSource === 'manual' ? generationContent : undefined,
        chunk_ids: generationSource === 'chunks' ? selectedChunkIds : undefined,
        node_ids: generationSource === 'chunks' ? selectedNodes : undefined,
        use_node_coverage: useNodeCoverage,
        difficulty_percentages: { easy: easyPercent, medium: mediumPercent, hard: hardPercent },
      }, authHeaders(true))
      setMessage({ type: 'success', title: 'Đã tạo job generate', body: `Job ${data?.job_id || data?.id || ''} đã được đưa vào hàng đợi. Mở Job Monitor để theo dõi trạng thái.` })
    } catch (error) {
      setMessage(toUserError(error))
    } finally {
      setLoadingAction(null)
    }
  }

  function toggleChunk(chunk: CourseChunk) {
    setSelectedChunkIds((previous) => {
      if (previous.includes(chunk.id)) {
        setSelectedChunkMap((map) => {
          const next = { ...map }
          delete next[chunk.id]
          return next
        })
        return previous.filter((item) => item !== chunk.id)
      }
      setSelectedChunkMap((map) => ({ ...map, [chunk.id]: chunk }))
      return [...previous, chunk.id]
    })
  }

  function selectVisibleChunks() {
    setSelectedChunkMap((map) => ({ ...map, ...Object.fromEntries(chunks.map((chunk) => [chunk.id, chunk])) }))
    setSelectedChunkIds((previous) => Array.from(new Set([...previous, ...chunks.map((chunk) => chunk.id)])))
  }

  function clearSelectedChunks() {
    setSelectedChunkIds([])
    setSelectedChunkMap({})
  }

  return <div className="page-stack">
    <section className="hero-card">
      <div><div className="eyebrow">Tạo câu hỏi v25.9</div><h2>Tạo Learning Check theo node Open edX</h2><p>Không dùng topic tự đoán nữa. Bạn chọn chapter/unit/component/chunks thật dưới course rồi generate câu hỏi bám đúng phần đó.</p></div>
      <div className="hero-steps"><span>1 Node</span><span>2 Chunks</span><span>3 Estimate</span><span>4 Generate</span><span>5 Review</span></div>
    </section>

    <section className="grid grid-3">
      <div className="card step-card">
        <div className="step-title"><span className="step-number">1</span><h2>Chọn nguồn dữ liệu</h2></div>
        <p className="helper">Production dùng node/chunk đã đồng bộ từ Open edX. Thủ công chỉ dành cho demo/kiểm thử nhanh.</p>
        <div className="mode-selector">
          <label className={generationSource === 'chunks' ? 'mode-card selected' : 'mode-card'}><input type="radio" checked={generationSource === 'chunks'} onChange={() => setGenerationSource('chunks')} /><span>Dùng node/chunk đã sync</span><small>Lấy nội dung học thật theo cây khóa học.</small></label>
          <label className={generationSource === 'manual' ? 'mode-card selected' : 'mode-card'}><input type="radio" checked={generationSource === 'manual'} onChange={() => setGenerationSource('manual')} /><span>Nhập nội dung thủ công</span><small>Chỉ phù hợp demo hoặc kiểm thử prompt.</small></label>
        </div>
      </div>
      <div className="card step-card">
        <div className="step-title"><span className="step-number">2</span><h2>Ước tính chi phí</h2></div>
        <label>Số câu cần tạo</label><input className="input" type="number" min={1} max={coursePolicy?.max_questions_per_job || 200} value={questionCount} onChange={(event) => setQuestionCount(Number(event.target.value))} />{coursePolicy && <small className="helper">Tối đa {coursePolicy.max_questions_per_job} câu/lượt · còn {coursePolicy.remaining_questions} câu trong khóa học</small>}
        <div className="difficulty-grid compact"><div><label>Dễ %</label><input className="input" type="number" min={0} max={100} value={easyPercent} onChange={(event) => setEasyPercent(Number(event.target.value))} /></div><div><label>Trung bình %</label><input className="input" type="number" min={0} max={100} value={mediumPercent} onChange={(event) => setMediumPercent(Number(event.target.value))} /></div><div><label>Khó %</label><input className="input" type="number" min={0} max={100} value={hardPercent} onChange={(event) => setHardPercent(Number(event.target.value))} /></div></div>
        <p className="helper">Phương pháp phần dư lớn nhất làm tròn số câu. Ví dụ 20 câu mặc định = 10 dễ, 6 trung bình, 4 khó.</p>
        <label className="inline-check"><input type="checkbox" checked={useNodeCoverage} onChange={(event) => setUseNodeCoverage(event.target.checked)} /> Bật Node Coverage Algorithm</label>
        <div className="mini-metrics"><div><span>Nguồn</span><b>{sourceLabel(generationSource)}</b></div><div><span>Token đã chọn</span><b>{(generationSource === 'chunks' ? selectedTokenTotal : estimatedContentTokens).toLocaleString('vi-VN')}</b></div></div>
        <LoadingButton className="btn secondary" loading={loadingAction === 'estimate'} disabled={!can('estimate_cost')} onClick={handleEstimate}>Ước tính chi phí</LoadingButton>
      </div>
      <div className="card step-card accent-card">
        <div className="step-title"><span className="step-number">3</span><h2>Tạo câu hỏi</h2></div>
        <p className="helper">Job chạy qua Kiểm soát chi phí, Cổng gọi model, Kiểm tra chất lượng, Ràng buộc nguồn học liệu và Chống trùng câu hỏi.</p>
        <LoadingButton className="btn" loading={loadingAction === 'generate'} disabled={!can('generate_questions')} onClick={handleGenerate}>Tạo câu hỏi</LoadingButton>
        <CostEstimateSummary estimate={estimate} />
      </div>
    </section>

    <section className="card">
      <div className="section-head"><div><h2>Nguồn dữ liệu tạo quiz</h2><p className="helper">Chế độ chunk học liệu lọc theo node dưới course, không còn lọc theo topic. Chọn filter là tự load; các chunk đã tick vẫn được giữ.</p></div><span className="badge">{sourceLabel(generationSource)}</span></div>
      {generationSource === 'manual' ? <div><label>Nội dung bài học nhập thủ công</label><textarea className="input large-textarea" rows={8} value={content} onChange={(event) => setContent(event.target.value)} /><p className="helper">Dùng cho demo. Production nên chuyển sang chế độ node/chunk.</p></div> : <div>
        <div className="grid grid-3">
          <div><label>Tìm chunk</label><input className="input" value={chunkSearch} onChange={(event) => { setChunkSearch(event.target.value); setChunkPage(1) }} /></div>
          <div><label>Loại nguồn</label><select className="input" value={chunkSourceType} onChange={(event) => { setChunkSourceType(event.target.value); setChunkPage(1) }}><option value="all">Tất cả</option><option value="html">html</option><option value="transcript">Phụ đề video</option><option value="problem">Bài quiz/problem</option><option value="file">File</option><option value="pdf">PDF</option><option value="pptx">PPTX</option></select></div>
          <div><label>Open edX node</label><select className="input" value={nodeId} onChange={(event) => { setNodeId(event.target.value); setChunkPage(1) }}><option value="all">Tất cả node</option>{contentNodes.map((node) => <option key={node.node_id} value={node.node_id}>{'—'.repeat(Math.min(node.depth, 5))} {node.title} ({node.chunk_count})</option>)}</select></div>
        </div>
        <div className="button-row"><button className="btn secondary" onClick={() => { setChunkSearch(''); setChunkSourceType('all'); setNodeId('all'); setChunkPage(1) }} disabled={loadingAction === 'chunks'}>Đặt lại bộ lọc</button>{loadingAction === 'chunks' && <span className="soft-tag"><span className="spinner tiny" /> Đang lọc...</span>}<button className="btn small secondary" onClick={selectVisibleChunks}>Chọn trang hiện tại</button><button className="btn small secondary" onClick={clearSelectedChunks}>Bỏ chọn</button></div>
        <PaginationControls page={chunkPage} pageSize={chunkPageSize} total={chunkTotal} totalPages={chunkTotalPages} onPageChange={setChunkPage} onPageSizeChange={changeChunkPageSize} loading={loadingAction === 'chunks'} label="chunks" /><div className="chunk-toolbar"><div><b>{chunks.length}</b> chunks visible / <b>{chunkTotal}</b> total · <b>{selectedChunkIds.length}</b> selected <span className="muted">({visibleSelectedCount} visible{hiddenSelectedCount ? `, ${hiddenSelectedCount} hidden by filter` : ''})</span> · <b>{selectedTokenTotal.toLocaleString('vi-VN')}</b> selected tokens</div></div>
        <div className="chunk-list">{chunks.length ? chunks.map((chunk) => <label key={chunk.id} className={selectedChunkIds.includes(chunk.id) ? 'chunk-card selected' : 'chunk-card'}><input type="checkbox" checked={selectedChunkIds.includes(chunk.id)} onChange={() => toggleChunk(chunk)} /><div><div className="chunk-title">{chunk.source_type} · {chunk.block_id}</div><div className="muted">{chunk.token_count} tokens · {chunk.source_ref || 'no source ref'}</div><p>{chunk.content.slice(0, 260)}{chunk.content.length > 260 ? '...' : ''}</p></div></label>) : <div className="empty-state">Chưa có chunk. Hãy sang trang Course Sync trước.</div>}</div><PaginationControls page={chunkPage} pageSize={chunkPageSize} total={chunkTotal} totalPages={chunkTotalPages} onPageChange={setChunkPage} onPageSizeChange={changeChunkPageSize} loading={loadingAction === 'chunks'} label="chunks" />
      </div>}
    </section>
    <ActionMessage message={message} onClose={() => setMessage(null)} />
  </div>
}
