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
    rejected: 'Đã bỏ',
    draft_error: 'Câu lỗi',
    published: 'Đã publish',
  }
  return labels[String(value || '')] || value || 'Tất cả'
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

function Chip({ children }: { children: React.ReactNode }) {
  return <span className="dashboard-filter-chip">{children}</span>
}

function SearchResultCard({ item }: { item: BankSearchResult }) {
  return <Link href={item.href || '/bank'} className="dashboard-search-result-card">
    <div className="result-icon">{resultTypeLabel(item.type).slice(0, 1)}</div>
    <div className="result-body">
      <div className="result-head"><b>{item.title}</b><span>{resultTypeLabel(item.type)}</span></div>
      <p>{item.subtitle}</p>
      {item.type === 'question' ? <div className="result-tags">
        {item.status ? <small className="status warning">{labelStatus(item.status)}</small> : null}
        {item.difficulty ? <small>{labelDifficulty(item.difficulty)}</small> : null}
        {item.question_id ? <small>ID: {item.question_id}</small> : null}
      </div> : null}
    </div>
  </Link>
}

export default function BankSearchPage() {
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
          limit: 100,
        })
        setItems(payload.items || [])
      } else {
        setItems(await searchBankDashboard(headers, q, 50))
      }
    } catch (err: any) {
      setError(err?.message || 'Không tải được danh sách drill-down')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [authReady, q, entity, status, difficulty, questionType, createdFrom, createdTo, questionId, chapterId, subjectId]) // eslint-disable-line react-hooks/exhaustive-deps

  return <div className="page-stack bank-multipage dashboard-search-page">
    <div className="dashboard-search-hero card">
      <div>
        <span className="eyebrow">Drill-down</span>
        <h1>Danh sách xử lý từ Dashboard</h1>
        <p>Toàn bộ kết quả đã được backend lọc theo scope RBAC của tài khoản hiện tại.</p>
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
      <div className="dashboard-search-count">Tìm thấy <b>{items.length}</b> kết quả phù hợp</div>
      <div className="dashboard-search-list">
        {items.map((item, index) => <SearchResultCard key={`${item.type}-${item.id || item.question_id || index}`} item={item} />)}
      </div>
    </> : <div className="dashboard-empty-state">
      <b>Không có kết quả trong phạm vi của bạn.</b>
      <p>Dữ liệu có thể chưa được tạo, chưa rebuild search index, hoặc bạn không có quyền trong scope đó.</p>
      <Link className="btn secondary small" href="/bank">Quay lại Dashboard</Link>
    </div>}
  </div>
}
