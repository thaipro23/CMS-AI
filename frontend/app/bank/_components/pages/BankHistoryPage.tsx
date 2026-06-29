'use client'

import { formatVNDateTime } from '../../../../lib/time'
import Link from 'next/link'
import { useEffect, useMemo, useState } from 'react'
import { getBankReleases, getCourseQuizInstances, rollbackCourseQuizInstance } from '../../../../lib/api'
import type { BankRelease, CourseQuizInstance } from '../../../../types'
import { useBankData, useAsyncMessage, Breadcrumb, statusClass, statusLabel, Modal } from '../shared'

function dateText(value?: string | null) { try { return value ? formatVNDateTime(value) : '—' } catch { return value || '—' } }
function releaseTitle(item: BankRelease) { return item.release_code || item.title || item.id }

export function BankHistoryPage() {
  const { headers, can } = useBankData()
  const { message, busy, run } = useAsyncMessage()
  const [quizHistory, setQuizHistory] = useState<CourseQuizInstance[]>([])
  const [releases, setReleases] = useState<BankRelease[]>([])
  const [q, setQ] = useState('')
  const [status, setStatus] = useState('all')
  const [quizOpen, setQuizOpen] = useState(false)
  const [releaseOpen, setReleaseOpen] = useState(false)

  const load = async () => {
    const [quizRows, releaseRows] = await Promise.all([
      getCourseQuizInstances(headers, { limit: 100 }),
      getBankReleases(headers),
    ])
    setQuizHistory(quizRows)
    setReleases(releaseRows)
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
  const filteredReleases = useMemo(() => {
    const needle = q.trim().toLowerCase()
    return releases.filter((item) => {
      const passStatus = status === 'all' || item.status === status
      const passText = !needle || [item.id, item.release_code, item.title, item.bank_version_id, item.openedx_library_key].filter(Boolean).some((v) => String(v).toLowerCase().includes(needle))
      return passStatus && passText
    })
  }, [q, releases, status])
  const created = quizHistory.filter((i) => i.status !== 'rolled_back' && i.status !== 'failed').length
  const rolledBack = quizHistory.filter((i) => i.status === 'rolled_back').length
  const failed = quizHistory.filter((i) => i.status === 'failed').length

  return <div className="page-stack bank-multipage ops-console history-console">
    <Breadcrumb items={[{ label: 'Bộ môn', href: '/bank/departments' }, { label: 'Lịch sử bộ đề và Quiz' }]} />
    {message ? <div className="alert info">{message}</div> : null}
    <section className="ops-hero card">
      <div><span className="eyebrow">Lịch sử</span><h1>Lịch sử ngân hàng đề</h1><p>Theo dõi bộ đề đã chốt, Quiz đã tạo, thao tác khôi phục và lỗi cần xử lý.</p></div>
    </section>
    <section className="ops-kpi-grid"><div><span>Bộ đề</span><b>{releases.length}</b></div><div><span>Quiz đang hiệu lực</span><b>{created}</b></div><div><span>Đã khôi phục</span><b>{rolledBack}</b></div><div><span>Lỗi</span><b>{failed}</b></div></section>
    <section className="card history-action-panel"><div className="button-row no-margin history-action-buttons"><button className="btn secondary" type="button" onClick={() => setQuizOpen(true)}>Quiz trên CMS ({quizHistory.length})</button><button className="btn secondary" type="button" onClick={() => setReleaseOpen(true)}>Bộ đề gần đây ({releases.length})</button><Link className="btn" href="/bank/quiz">Tạo Quiz trên CMS</Link></div></section>

    <Modal open={quizOpen} title="Quiz trên CMS" wide onClose={() => setQuizOpen(false)}>
      <div className="modal-filter-bar"><label>Tìm kiếm<input className="input" value={q} onChange={(e) => setQ(e.target.value)} placeholder="khóa học, bộ đề, bài kiểm tra..." /></label><label>Trạng thái<select className="input" value={status} onChange={(e) => setStatus(e.target.value)}><option value="all">Tất cả</option><option value="created">Đã tạo</option><option value="published">Đã đưa lên CMS</option><option value="rolled_back">Đã khôi phục</option><option value="failed">Thất bại</option></select></label><button className="btn secondary" onClick={() => load()} type="button">Làm mới</button></div>
      <div className="responsive-table-wrap"><table className="ops-data-table"><thead><tr><th>Quiz</th><th>Khóa học</th><th>Trạng thái</th><th>Bộ đề</th><th>Bài kiểm tra</th><th>Ngày tạo</th><th>Thao tác</th></tr></thead><tbody>{filteredQuiz.map((item) => <tr key={item.id}><td><b>{item.metadata_json?.quiz_title || 'Quiz trên CMS'}</b></td><td>{item.openedx_course_id}</td><td><span className={statusClass(item.status)}>{statusLabel(item.status)}</span></td><td><small>{item.bank_release_id}</small></td><td><code>{item.openedx_unit_node_id || '—'}</code></td><td><small>{dateText(item.created_at)}</small></td><td><button className="btn small secondary" disabled={busy || !can('publish_questions') || item.status === 'rolled_back'} onClick={() => run(async () => { await rollbackCourseQuizInstance(headers, item.id, { mode: 'safe', note: 'Khôi phục từ trang lịch sử Quiz' }) }, 'Đã gửi yêu cầu khôi phục Quiz', load)}>Khôi phục</button></td></tr>)}{!filteredQuiz.length ? <tr><td colSpan={7}><div className="empty-state">Chưa có Quiz phù hợp.</div></td></tr> : null}</tbody></table></div>
    </Modal>
    <Modal open={releaseOpen} title="Bộ đề gần đây" wide onClose={() => setReleaseOpen(false)}>
      <div className="modal-filter-bar"><label>Tìm kiếm<input className="input" value={q} onChange={(e) => setQ(e.target.value)} placeholder="khóa học, bộ đề, bài kiểm tra..." /></label><label>Trạng thái<select className="input" value={status} onChange={(e) => setStatus(e.target.value)}><option value="all">Tất cả</option><option value="created">Đã tạo</option><option value="published">Đã đưa lên CMS</option><option value="rolled_back">Đã khôi phục</option><option value="failed">Thất bại</option></select></label><button className="btn secondary" onClick={() => load()} type="button">Làm mới</button></div>
      <div className="responsive-table-wrap"><table className="ops-data-table"><thead><tr><th>Bộ đề</th><th>Trạng thái</th><th>Phiên bản câu hỏi</th><th>Thư viện CMS</th><th>Số câu</th><th>Ngày tạo</th></tr></thead><tbody>{filteredReleases.map((item) => <tr key={item.id}><td><b>{releaseTitle(item)}</b><small>{item.id}</small></td><td><span className={statusClass(item.status)}>{statusLabel(item.status)}</span></td><td><small>{item.bank_version_id}</small></td><td>{item.openedx_library_key || 'Chưa có thư viện'}</td><td>{item.approved_question_count || 0}</td><td><small>{dateText(item.created_at)}</small></td></tr>)}{!filteredReleases.length ? <tr><td colSpan={6}><div className="empty-state">Chưa có release trong phạm vi này.</div></td></tr> : null}</tbody></table></div>
    </Modal>
  </div>
}
