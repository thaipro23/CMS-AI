'use client'

import Link from 'next/link'
import { useEffect, useMemo, useState } from 'react'
import { getAuditLogs, getBankReleases, getCourseQuizInstances, rollbackCourseQuizInstance } from '../../../../lib/api'
import type { AuditLogRow, BankRelease, CourseQuizInstance } from '../../../../types'
import { useBankData, useAsyncMessage, Breadcrumb, statusClass, statusLabel } from '../shared'

function dateText(value?: string | null) { try { return value ? new Date(value).toLocaleString('vi-VN') : '—' } catch { return value || '—' } }
function releaseTitle(item: BankRelease) { return item.release_code || item.title || item.id }
function eventText(row: AuditLogRow) { return row.action.replace('question_bank.', 'Bank · ').replace('openedx.', 'Open edX · ') }

export function BankHistoryPage() {
  const { headers, can } = useBankData()
  const { message, busy, run } = useAsyncMessage()
  const [quizHistory, setQuizHistory] = useState<CourseQuizInstance[]>([])
  const [releases, setReleases] = useState<BankRelease[]>([])
  const [auditRows, setAuditRows] = useState<AuditLogRow[]>([])
  const [q, setQ] = useState('')
  const [status, setStatus] = useState('all')

  const load = async () => {
    const [quizRows, releaseRows, audit] = await Promise.all([
      getCourseQuizInstances(headers, { limit: 100 }),
      getBankReleases(headers),
      getAuditLogs('', { page: 1, pageSize: 100 }, headers),
    ])
    setQuizHistory(quizRows)
    setReleases(releaseRows)
    setAuditRows((audit.items || []).filter((row) => row.action.includes('release') || row.action.includes('quiz') || row.action.includes('rollback') || row.action.includes('publish')))
  }
  useEffect(() => { load().catch(() => null) }, []) // eslint-disable-line react-hooks/exhaustive-deps

  const filteredQuiz = useMemo(() => {
    const needle = q.trim().toLowerCase()
    return quizHistory.filter((item) => {
      const passStatus = status === 'all' || item.status === status
      const passText = !needle || [item.openedx_course_id, item.openedx_unit_node_id, item.bank_release_id, item.metadata_json?.quiz_title].filter(Boolean).some((v) => String(v).toLowerCase().includes(needle))
      return passStatus && passText
    })
  }, [q, quizHistory, status])
  const created = quizHistory.filter((i) => i.status !== 'rolled_back' && i.status !== 'failed').length
  const rolledBack = quizHistory.filter((i) => i.status === 'rolled_back').length
  const failed = quizHistory.filter((i) => i.status === 'failed').length

  return <div className="page-stack bank-multipage ops-console history-console">
    <Breadcrumb items={[{ label: 'Bộ môn', href: '/bank/departments' }, { label: 'Lịch sử publish / quiz' }]} />
    {message ? <div className="alert info">{message}</div> : null}
    <section className="ops-hero card"><div><span className="eyebrow">Release & Quiz history</span><h1>Lịch sử ngân hàng đề</h1><p>Theo dõi release, publish Open edX, Quiz đã tạo và rollback. Giao diện này giúp kiểm tra nhanh “đã đẩy gì lên Open edX”.</p></div><Link className="btn" href="/bank/quiz">Tạo Quiz Open edX</Link></section>
    <section className="ops-kpi-grid"><div><span>Release gần đây</span><b>{releases.length}</b></div><div><span>Quiz đang hiệu lực</span><b>{created}</b></div><div><span>Đã rollback</span><b>{rolledBack}</b></div><div><span>Lỗi</span><b>{failed}</b></div></section>
    <section className="card ops-filter-card"><div className="grid grid-3"><label>Tìm lịch sử<input className="input" value={q} onChange={(e) => setQ(e.target.value)} placeholder="course, release, unit..." /></label><label>Trạng thái<select className="input" value={status} onChange={(e) => setStatus(e.target.value)}><option value="all">Tất cả</option><option value="created">Đã tạo</option><option value="published">Đã publish</option><option value="rolled_back">Đã rollback</option><option value="failed">Thất bại</option></select></label><div className="button-column"><button className="btn secondary" onClick={() => load()}>Làm mới</button></div></div></section>
    <section className="ops-two-col"><section className="card"><div className="section-head"><div><h2>Quiz Open edX</h2><p className="helper">Click vào unit để đối chiếu cấu hình sau khi tạo Quiz.</p></div></div><div className="history-card-list">{filteredQuiz.map((item) => <article className="history-card" key={item.id}><div className="history-head"><div><b>{item.metadata_json?.quiz_title || item.openedx_course_id}</b><small>{item.openedx_course_id}</small></div><span className={statusClass(item.status)}>{statusLabel(item.status)}</span></div><div className="history-meta"><span>Release: {item.bank_release_id}</span><span>Unit: {item.openedx_unit_node_id || '—'}</span><span>{dateText(item.created_at)}</span></div><div className="button-row"><button className="btn small secondary" disabled={busy || !can('publish_questions') || item.status === 'rolled_back'} onClick={() => run(async () => { await rollbackCourseQuizInstance(headers, item.id, { mode: 'safe', note: 'Rollback từ trang lịch sử Quiz' }) }, 'Đã gửi yêu cầu rollback Quiz', load)}>Rollback</button></div></article>)}{!filteredQuiz.length ? <div className="empty-state">Chưa có Quiz phù hợp.</div> : null}</div></section><section className="card"><div className="section-head"><div><h2>Release gần đây</h2><p className="helper">Các bản chốt bộ đề/publish trong scope.</p></div></div><div className="history-card-list compact">{releases.slice(0, 18).map((item) => <article className="history-card" key={item.id}><div className="history-head"><div><b>{releaseTitle(item)}</b><small>{item.bank_version_id}</small></div><span className={statusClass(item.status)}>{statusLabel(item.status)}</span></div><div className="history-meta"><span>{dateText(item.created_at)}</span><span>{item.openedx_library_key || 'Chưa có Library'}</span></div></article>)}{!releases.length ? <div className="empty-state">Chưa có release trong phạm vi này.</div> : null}</div></section></section>
    <section className="card"><div className="section-head"><div><h2>Dòng sự kiện</h2><p className="helper">Publish, rollback và quiz events đã lọc theo quyền.</p></div></div><div className="audit-timeline mini">{auditRows.slice(0, 30).map((row) => <article className={`audit-card ${row.status === 'failed' ? 'failed' : 'success'}`} key={row.id}><div className="audit-marker" /><div className="audit-body"><div className="audit-top"><b>{eventText(row)}</b><span className={statusClass(row.status)}>{statusLabel(row.status)}</span></div><p>{row.message || '—'}</p><div className="audit-meta"><span>{dateText(row.created_at)}</span><span>{row.actor_id}</span><span>{row.target_type} {row.target_id || ''}</span></div></div></article>)}{!auditRows.length ? <div className="empty-state">Chưa có sự kiện publish/quiz.</div> : null}</div></section>
  </div>
}
