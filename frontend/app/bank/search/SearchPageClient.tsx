'use client'

import Link from 'next/link'
import { useSearchParams } from 'next/navigation'
import { useEffect, useMemo, useState } from 'react'
import { useAppContext } from '../../../context/AppContext'
import { getBankDashboardDrilldown, searchBankDashboard } from '../../../lib/api'
import type { BankSearchResult } from '../../../types'

function labelStatus(value?: string | null) {
  const labels: Record<string, string> = {
    draft: 'Bản nháp',
    pending_review: 'Chờ duyệt',
    needs_review: 'Chờ duyệt',
    approved: 'Đã duyệt',
    rejected: 'Bị từ chối',
    draft_error: 'Câu lỗi',
    published: 'Đã publish',
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
  try { return new Date(value).toLocaleString('vi-VN') } catch { return value }
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
  return <div className="responsive-table-wrap drilldown-table-wrap">
    <table className="ops-data-table drilldown-question-table">
      <thead>
        <tr>
          <th>Câu hỏi</th>
          <th>Trạng thái</th>
          <th>Độ khó</th>
          <th>Người xử lý</th>
          <th>Lý do / ghi chú</th>
          <th>Phạm vi</th>
          <th>Thời điểm</th>
          <th>Thao tác</th>
        </tr>
      </thead>
      <tbody>
        {items.map((item, index) => {
          const actionName = item.action_by_name || item.reviewer_name || item.reviewed_by || item.action_by || '—'
          const isRejected = item.status === 'rejected'
          const note = isRejected ? (item.reject_reason || item.review_note) : item.review_note
          return <tr key={`${item.type}-${item.id || item.question_id || index}`} className={`row-${item.status || 'draft'}`}>
            <td className="question-cell">
              <b>{truncate(item.title, 220)}</b>
              <small>ID: {item.question_id || item.id || '—'}</small>
            </td>
            <td><span className={`status ${statusClass(item.status)}`}>{labelStatus(item.status)}</span></td>
            <td><span className="pill-soft">{labelDifficulty(item.difficulty)}</span></td>
            <td>
              <b>{actionName}</b>
              <small>{isRejected ? 'Người từ chối' : item.status === 'approved' ? 'Người duyệt' : 'Người xử lý gần nhất'}</small>
            </td>
            <td className="note-cell">
              {note ? <span>{truncate(note, 180)}</span> : <span className="muted-text">Không có ghi chú</span>}
            </td>
            <td>
              <b>{item.subject_label || item.subtitle?.split(' · ')[2] || '—'}</b>
              <small>{item.chapter_title || (item.chapter_id ? `Chapter: ${item.chapter_id}` : '—')}</small>
            </td>
            <td>
              <b>{formatDate(item.reviewed_at)}</b>
              <small>Tạo: {formatDate(item.created_at)}</small>
            </td>
            <td><Link className="btn secondary small" href={item.href || '/bank'}>Mở</Link></td>
          </tr>
        })}
      </tbody>
    </table>
  </div>
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

  return <div className="page-stack bank-multipage dashboard-search-page">
    <div className="dashboard-search-hero card">
      <div>
        <span className="eyebrow">Danh sách</span>
        <h1>Câu hỏi trong phạm vi được giao</h1>
        <p>Kết quả lấy theo quyền hiện tại của tài khoản, dùng để kiểm tra nhanh các chỉ số trên Dashboard.</p>
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
      </div>
      <Link className="btn secondary" href="/bank">Về Dashboard</Link>
    </div>

    {loading ? <div className="dashboard-search-list">
      <div className="dashboard-skeleton" style={{ minHeight: 96 }} />
      <div className="dashboard-skeleton" style={{ minHeight: 96 }} />
      <div className="dashboard-skeleton" style={{ minHeight: 96 }} />
    </div> : error ? <div className="dashboard-error-state">
      <b>Không tải được dữ liệu.</b>
      <p>{error}</p>
      <button className="btn small" onClick={load} type="button">Thử lại</button>
    </div> : items.length ? <>
      <div className="dashboard-search-count">
        Đang hiển thị <b>{returned || items.length}</b>{total ? <> / <b>{total}</b></> : null} kết quả phù hợp
        {source === 'search_index' ? <small> · Dữ liệu lấy từ chỉ mục tìm kiếm</small> : null}
      </div>
      {isQuestionTable ? <SearchResultTable items={items} /> : <SearchResultCards items={items} />}
    </> : <div className="dashboard-empty-state">
      <b>Không có kết quả trong phạm vi của bạn.</b>
      <p>Dữ liệu có thể chưa được tạo hoặc bạn không có quyền trong phạm vi đó.</p>
      <Link className="btn secondary small" href="/bank">Quay lại Dashboard</Link>
    </div>}
  </div>
}
