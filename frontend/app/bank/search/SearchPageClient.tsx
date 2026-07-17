'use client'

import { formatVNDateTime } from '../../../lib/time'
import Link from 'next/link'
import { useSearchParams } from 'next/navigation'
import { useEffect, useMemo, useState } from 'react'
import { useAppContext } from '../../../context/AppContext'
import { getBankDashboardDrilldown, searchBankDashboard } from '../../../lib/api'
import type { BankSearchResult } from '../../../types'
import { PageHeader, PageRoot } from '../../../components/layout/PageHeader'
import { VisualIcon } from '../../../components/ui/VisualIcon'
import { EnterpriseDataTable, type EnterpriseTableColumn } from '../../../components/table/EnterpriseDataTable'
import { BankPageIdentity } from '../_components/BankDesignContract'

function labelStatus(value?: string | null) {
  const labels: Record<string, string> = {
    draft: 'Bản nháp',
    pending_review: 'Chờ duyệt',
    needs_review: 'Chờ duyệt',
    approved: 'Đã duyệt',
    rejected: 'Bị từ chối',
    draft_error: 'Câu lỗi',
    published: 'Đã đưa lên CMS',
  }
  return labels[String(value || '')] || value || 'Tất cả'
}

function statusClass(value?: string | null) {
  const normalized = String(value || '').toLowerCase()
  if (normalized === 'approved') return 'success'
  if (normalized === 'rejected' || normalized === 'draft_error') return 'danger'
  if (normalized === 'pending_review' || normalized === 'needs_review') return 'warning'
  if (normalized === 'published') return 'published'
  return 'neutral'
}

function labelDifficulty(value?: string | null) {
  const labels: Record<string, string> = { easy: 'Dễ', medium: 'Trung bình', hard: 'Khó' }
  return labels[String(value || '').toLowerCase()] || value || 'Tất cả'
}

function resultTypeLabel(type?: string | null) {
  const labels: Record<string, string> = {
    department: 'Bộ môn',
    subject: 'Môn',
    subject_version: 'Phiên bản môn',
    chapter: 'Bài',
    question: 'Câu hỏi',
  }
  return labels[String(type || '')] || type || 'Kết quả'
}

function formatDate(value?: string | null) {
  if (!value) return '—'
  try { return formatVNDateTime(value) } catch { return value }
}

function truncate(value?: string | null, max = 180) {
  const text = String(value || '').replace(/\s+/g, ' ').trim()
  if (!text) return '—'
  return text.length > max ? `${text.slice(0, max - 1).trim()}…` : text
}

function Chip({ children }: { children: React.ReactNode }) {
  return <span className="dashboard-filter-chip">{children}</span>
}

function SearchResultTable({ items }: { items: BankSearchResult[] }) {
  const columns: EnterpriseTableColumn<BankSearchResult>[] = [
    { key: 'stt', header: 'STT', kind: 'index', width: 52, hideable: false, render: (_item, index) => index + 1 },
    { key: 'question', header: 'Câu hỏi', kind: 'identity', minWidth: 300, hideable: false, render: (item) => <div className="question-cell"><b>{truncate(item.title, 220)}</b><small>ID: {item.question_id || item.id || '—'}</small></div> },
    { key: 'status', header: 'Trạng thái', kind: 'status', width: 126, hideable: true, render: (item) => <span className={`status ${statusClass(item.status)}`}>{labelStatus(item.status)}</span> },
    { key: 'difficulty', header: 'Độ khó', kind: 'status', width: 112, hideable: true, render: (item) => <span className="pill-soft">{labelDifficulty(item.difficulty)}</span> },
    { key: 'actor', header: 'Người xử lý', kind: 'identity', minWidth: 180, hideable: true, render: (item) => { const actionName = item.action_by_name || item.reviewer_name || item.reviewed_by || item.action_by || '—'; return <div><b>{actionName}</b><small>{item.status === 'rejected' ? 'Người từ chối' : item.status === 'approved' ? 'Người duyệt' : 'Người xử lý gần nhất'}</small></div> } },
    { key: 'note', header: 'Lý do / ghi chú', kind: 'text', minWidth: 220, hideable: true, defaultVisible: false, render: (item) => { const note = item.status === 'rejected' ? (item.reject_reason || item.review_note) : item.review_note; return note ? truncate(note, 180) : <span className="muted-text">Không có ghi chú</span> } },
    { key: 'scope', header: 'Phạm vi', kind: 'text', minWidth: 180, hideable: true, render: (item) => <div><b>{item.subject_label || item.subtitle?.split(' · ')[2] || '—'}</b><small>{item.chapter_title || (item.chapter_id ? `Chapter: ${item.chapter_id}` : '—')}</small></div> },
    { key: 'date', header: 'Thời điểm', kind: 'date', minWidth: 160, hideable: true, defaultVisible: false, render: (item) => <div><b>{formatDate(item.reviewed_at)}</b><small>Tạo: {formatDate(item.created_at)}</small></div> },
    { key: 'actions', header: 'Thao tác', kind: 'actions', width: 84, hideable: false, render: (item) => <Link className="btn secondary small" href={item.href || '/bank'}>Mở</Link> },
  ]
  return <EnterpriseDataTable tableId="bank-search-results" caption="Kết quả tìm kiếm câu hỏi" rows={items} columns={columns} rowKey={(item) => `${item.type}-${item.id || item.question_id || item.href}`} density="compact" label="kết quả" showSummary={false} />
}


function SearchResultCards({ items }: { items: BankSearchResult[] }) {
  return <div className="dashboard-search-list">
    {items.map((item, index) => <Link key={`${item.type}-${item.id || index}`} href={item.href || '/bank'} className="dashboard-search-result-card">
      <div className="result-icon">{resultTypeLabel(item.type).slice(0, 1)}</div>
      <div className="result-body">
        <div className="result-head"><b>{item.title}</b><span>{resultTypeLabel(item.type)}</span></div>
        <p>{item.subtitle}</p>
      </div>
    </Link>)}
  </div>
}

export default function SearchPageClient() {
  const params = useSearchParams()
  const { authReady, authHeaders } = useAppContext()
  const headers = useMemo(() => authHeaders(), [authHeaders])
  const q = params.get('q') || ''
  const entity = params.get('entity') || 'questions'
  const status = params.get('status') || ''
  const difficulty = params.get('difficulty') || ''
  const questionType = params.get('question_type') || ''
  const createdFrom = params.get('created_from') || ''
  const createdTo = params.get('created_to') || ''
  const questionId = params.get('question_id') || ''
  const chapterId = params.get('chapter_id') || ''
  const subjectId = params.get('subject_id') || ''
  const [items, setItems] = useState<BankSearchResult[]>([])
  const [total, setTotal] = useState(0)
  const [returned, setReturned] = useState(0)
  const [source, setSource] = useState('')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  const hasQuestionFilters = Boolean(status || difficulty || questionType || createdFrom || createdTo || questionId || chapterId || subjectId || entity === 'questions')

  const load = async () => {
    if (!authReady) return
    setLoading(true)
    setError('')
    try {
      if (hasQuestionFilters) {
        const payload = await getBankDashboardDrilldown(headers, {
          entity,
          q,
          status,
          difficulty,
          questionType,
          createdFrom,
          createdTo,
          questionId,
          chapterId,
          subjectId,
          limit: 500,
        })
        setItems(payload.items || [])
        setTotal(Number(payload.total || 0))
        setReturned(Number(payload.returned || payload.items?.length || 0))
        setSource(String(payload.source || ''))
      } else {
        const results = await searchBankDashboard(headers, q, 50)
        setItems(results)
        setTotal(results.length)
        setReturned(results.length)
        setSource('search')
      }
    } catch (err: any) {
      setError(err?.message || 'Không tải được danh sách')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [authReady, q, entity, status, difficulty, questionType, createdFrom, createdTo, questionId, chapterId, subjectId]) // eslint-disable-line react-hooks/exhaustive-deps

  const isQuestionTable = hasQuestionFilters && items.every((item) => item.type === 'question')

  return <PageRoot className="page-stack bank-multipage bank-contract-page dashboard-search-page">
    <PageHeader eyebrow="Ngân hàng đề" title="Tìm kiếm ngân hàng đề" icon="search" breadcrumbs={[{ label: 'Ngân hàng đề', href: '/bank/departments' }, { label: 'Tìm kiếm' }]} />
    <BankPageIdentity title="Tìm kiếm ngân hàng đề" description="Tra cứu nhanh bộ môn, môn học, phiên bản, bài và câu hỏi trong đúng phạm vi được phân quyền." icon="search" tone="blue" actions={<Link className="btn secondary" href="/bank">Về Chi phí & Token</Link>} />
    <section className="card visual-section-card dashboard-search-filter-card">
      <div className="visual-section-heading"><VisualIcon label="Bộ lọc đang áp dụng" icon="filter" tone="blue" /><div><h2>Bộ lọc đang áp dụng</h2><p className="helper">Các điều kiện được lấy trực tiếp từ URL hiện tại.</p></div></div>
        <div className="dashboard-filter-row">
          {q ? <Chip>Từ khóa: {q}</Chip> : null}
          {status ? <Chip>Trạng thái: {labelStatus(status)}</Chip> : null}
          {difficulty ? <Chip>Độ khó: {labelDifficulty(difficulty)}</Chip> : null}
          {questionType ? <Chip>Loại: {questionType}</Chip> : null}
          {createdFrom || createdTo ? <Chip>Thời gian: {createdFrom || '...'} → {createdTo || '...'}</Chip> : null}
          {questionId ? <Chip>Câu hỏi: {questionId}</Chip> : null}
          {chapterId ? <Chip>Chapter: {chapterId}</Chip> : null}
          {subjectId ? <Chip>Môn: {subjectId}</Chip> : null}
        </div>
    </section>

    {loading ? <div className="dashboard-search-list">
      <div className="dashboard-skeleton" style={{ minHeight: 96 }} />
      <div className="dashboard-skeleton" style={{ minHeight: 96 }} />
      <div className="dashboard-skeleton" style={{ minHeight: 96 }} />
    </div> : error ? <div className="dashboard-error-state visual-state"><VisualIcon label="Không tải được dữ liệu" icon="alert" tone="red" /><div>
      <b>Không tải được dữ liệu.</b>
      <p>{error}</p>
      <button className="btn small" onClick={load} type="button">Thử lại</button></div>
    </div> : items.length ? <>
      <div className="dashboard-search-count">
        Đang hiển thị <b>{returned || items.length}</b>{total ? <> / <b>{total}</b></> : null} kết quả phù hợp
        {source === 'search_index' ? <small> · Dữ liệu lấy từ chỉ mục tìm kiếm</small> : null}
      </div>
      {isQuestionTable ? <SearchResultTable items={items} /> : <SearchResultCards items={items} />}
    </> : <div className="dashboard-empty-state visual-state"><VisualIcon label="Không có kết quả" icon="database" tone="slate" /><div>
      <b>Không có kết quả trong phạm vi của bạn.</b>
      <p>Dữ liệu có thể chưa được tạo hoặc bạn không có quyền trong phạm vi đó.</p>
      <Link className="btn secondary small" href="/bank">Quay lại Chi phí & Token</Link></div>
    </div>}
  </PageRoot>
}
