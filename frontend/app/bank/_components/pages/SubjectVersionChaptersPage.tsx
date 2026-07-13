'use client'

import Link from 'next/link'
import { useEffect, useMemo, useState } from 'react'
import { EnterpriseDataTable, type EnterpriseTableColumn } from '../../../../components/table/EnterpriseDataTable'
import { useUrlTableState } from '../../../../hooks/useUrlTableState'
import type { ChapterSummary, Department, Subject, SubjectChapter, SubjectOffering } from '../../../../types'
import { createSubjectChapter, deleteSubjectChapter, getChapterSummaries, getDepartment, getSubject, getSubjectOffering, updateSubjectChapter } from '../../../../lib/api'
import { BankTableStatusFilter, BankTableToolbar, Breadcrumb, ConfirmDialog, EntityActions, Modal, QuickSearchBox, bankStatusMatches, buildChapterTitle, chapterDisplayName, emptyReviewStats, matchesSearch, normalizeLessonInput, reviewStatusText, useAsyncMessage, useBankData } from '../shared'

export function SubjectVersionChaptersPage({ versionId }: { versionId: string }) {
  const { headers, canScope } = useBankData()
  const { message, busy, run } = useAsyncMessage()
  const { state: tableState, update: updateTableState } = useUrlTableState({ status: 'all', pageSize: 20, density: 'compact' })
  const [department, setDepartment] = useState<Department | null>(null)
  const [subject, setSubject] = useState<Subject | null>(null)
  const [offering, setOffering] = useState<SubjectOffering | null>(null)
  const offeringScope = { scopeType: 'SUBJECT_VERSION' as const, scopeId: versionId, subjectOfferingId: versionId, subjectId: offering?.subject_id, departmentId: department?.id }
  const canUpdateOffering = canScope('subject.update', offeringScope)
  const [summaries, setSummaries] = useState<ChapterSummary[]>([])
  const [createOpen, setCreateOpen] = useState(false)
  const [chapterInput, setChapterInput] = useState('')
  const [editing, setEditing] = useState<SubjectChapter | null>(null)
  const [editLesson, setEditLesson] = useState('')
  const [deleteTarget, setDeleteTarget] = useState<SubjectChapter | null>(null)
  const [deleteError, setDeleteError] = useState('')

  const load = async () => {
    const nextOffering = await getSubjectOffering(headers, versionId)
    const [nextSubject, nextSummaries] = await Promise.all([getSubject(headers, nextOffering.subject_id), getChapterSummaries(headers, versionId)])
    const nextDepartment = await getDepartment(headers, nextSubject.department_id)
    setOffering(nextOffering); setSubject(nextSubject); setDepartment(nextDepartment); setSummaries(nextSummaries)
  }
  useEffect(() => { load().catch(() => null) }, [versionId]) // eslint-disable-line react-hooks/exhaustive-deps

  const statusFilter = tableState.status as BankTableStatusFilter
  const filtered = summaries.filter(({ chapter, stats }) => matchesSearch(chapterDisplayName(chapter), tableState.q) && bankStatusMatches(stats, statusFilter))
  const totalPages = Math.max(1, Math.ceil(filtered.length / tableState.pageSize))
  const safePage = Math.min(tableState.page, totalPages)
  const pageRows = filtered.slice((safePage - 1) * tableState.pageSize, safePage * tableState.pageSize)

  const columns = useMemo<EnterpriseTableColumn<ChapterSummary>[]>(() => [
    { key: 'stt', header: 'STT', width: 64, minWidth: 64, sticky: 'left', stickyOffset: 0, hideable: false, className: 'stt-cell', render: (_row, index) => (safePage - 1) * tableState.pageSize + index + 1 },
    { key: 'chapter', header: 'Bài/Chapter', minWidth: 280, sticky: 'left', stickyOffset: 64, hideable: false, render: ({ chapter }) => <Link className="bank-table-link" href={`/bank/chapters/${chapter.id}`}><b>{chapterDisplayName(chapter)}</b><small>{chapter.title || chapterDisplayName(chapter)}</small></Link> },
    { key: 'status', header: 'Trạng thái', minWidth: 165, hideable: true, render: ({ stats: rawStats }) => { const stats = rawStats || emptyReviewStats(); const published = Boolean(stats.is_published || stats.release_status === 'published' || (stats.published_release_count || 0) > 0); return <span className={`bank-row-status status-${published ? 'published' : (stats.status || 'empty')}`}>{published ? 'Đã đưa lên CMS' : reviewStatusText(stats.status)}</span> } },
    { key: 'materials', header: 'Tài liệu', align: 'right', hideable: true, render: ({ stats }) => stats?.material_count || 0 },
    { key: 'questions', header: 'Tổng câu', align: 'right', hideable: true, render: ({ stats }) => `${stats?.total_questions || 0}/${stats?.question_limit || 100}` },
    { key: 'approved', header: 'Đã duyệt', align: 'right', hideable: true, render: ({ stats }) => stats?.approved_count || 0 },
    { key: 'unresolved', header: 'Chưa duyệt/lỗi', align: 'right', hideable: true, render: ({ stats }) => stats?.unresolved_count || 0 },
    { key: 'release', header: 'Bộ đề', minWidth: 150, hideable: true, render: ({ stats }) => { const published = Boolean(stats?.is_published || stats?.release_status === 'published' || (stats?.published_release_count || 0) > 0); return published ? 'Đã đưa lên CMS' : stats?.ready_to_release ? 'Sẵn sàng chốt' : stats?.release_count ? 'Đã chốt' : 'Chưa chốt' } },
    { key: 'actions', header: 'Thao tác', minWidth: 150, sticky: 'right', stickyOffset: 0, hideable: false, render: ({ chapter, stats }) => { const published = Boolean(stats?.is_published || stats?.release_status === 'published' || (stats?.published_release_count || 0) > 0); return <EntityActions variant="inline" canManage={canUpdateOffering && !published} lockedLabel={published ? 'Đã khóa' : 'Không có quyền'} onEdit={() => { setEditing(chapter); setEditLesson(normalizeLessonInput(chapterDisplayName(chapter))) }} onDelete={() => setDeleteTarget(chapter)} /> } },
  ], [canUpdateOffering, safePage, tableState.pageSize])

  return <div className="page-stack bank-multipage">
    <Breadcrumb items={[{ label: 'Ngân hàng câu hỏi', href: '/bank' }, { label: 'Bộ môn', href: '/bank/departments' }, { label: department?.name || 'Bộ môn', href: department ? `/bank/departments/${department.id}/subjects` : undefined }, { label: subject?.code || 'Môn', href: subject ? `/bank/subjects/${subject.id}/versions` : undefined }, { label: offering?.code || 'Phiên bản môn' }, { label: 'Bài/Chapter' }]} />
    <QuickSearchBox compact />
    {message ? <div className="alert info">{message}</div> : null}
    <section className="card">
      <div className="section-head"><div><h2>{offering ? `Danh sách bài trong ${offering.code}` : 'Danh sách bài trong phiên bản môn'}</h2><p className="helper">Bài/Chapter là cấp cuối trước danh sách câu hỏi. Release và Quiz được thao tác từ workspace của từng bài.</p></div></div>
      <BankTableToolbar search={tableState.q} setSearch={(q) => updateTableState({ q })} statusFilter={statusFilter} setStatusFilter={(status) => updateTableState({ status })} resultCount={filtered.length} totalCount={summaries.length} placeholder="Tìm bài, Final test hoặc Assignment" action={canUpdateOffering ? <button className="btn" onClick={() => setCreateOpen(true)}>+ Thêm bài</button> : undefined} />
      <EnterpriseDataTable tableId={`bank-chapters-${versionId}`} caption="Danh sách bài/Chapter" rows={pageRows} columns={columns} rowKey={({ chapter }) => chapter.id} density={tableState.density} onDensityChange={(density) => updateTableState({ density }, { resetPage: false })} page={safePage} pageSize={tableState.pageSize} total={filtered.length} totalPages={totalPages} onPageChange={(page) => updateTableState({ page }, { resetPage: false })} onPageSizeChange={(pageSize) => updateTableState({ pageSize, page: 1 }, { resetPage: false })} label="bài" emptyTitle={tableState.q || statusFilter !== 'all' ? 'Không có bài phù hợp' : 'Chưa có bài/Chapter'} emptyDescription="Thêm bài đầu tiên cho phiên bản môn này." />
    </section>

    <Modal open={Boolean(editing)} title="Sửa bài" onClose={() => setEditing(null)}><div className="mini-form"><label>Tên bài / Final test / Assignment<input className="input" value={editLesson} onChange={(e) => setEditLesson(e.target.value)} /></label><p className="helper">Nhập số sẽ tự lưu thành “Bài 1.2”. Tên đặc biệt được giữ nguyên.</p><div className="modal-actions"><button className="btn secondary" onClick={() => setEditing(null)}>Hủy</button><button className="btn" disabled={busy || !normalizeLessonInput(editLesson)} onClick={() => { if (!editing) return; const title = buildChapterTitle(editLesson) || editLesson.trim(); run(async () => { await updateSubjectChapter(headers, editing.id, { title }); setEditing(null) }, 'Đã sửa bài', load) }}>Lưu thay đổi</button></div></div></Modal>
    <ConfirmDialog open={Boolean(deleteTarget)} title={`Xóa ${deleteTarget ? chapterDisplayName(deleteTarget) : 'bài'}?`} description={<p>Chỉ xóa được khi bài chưa có tài liệu thật, câu hỏi, Release, mapping hoặc Quiz.</p>} confirmLabel="Xác nhận xóa" danger busy={busy} onClose={() => setDeleteTarget(null)} onConfirm={async () => {
      if (!deleteTarget) return
      try { await deleteSubjectChapter(headers, deleteTarget.id); setDeleteTarget(null); await load() } catch (error) { setDeleteTarget(null); setDeleteError(error instanceof Error ? error.message : 'Không thể xóa bài/chapter') }
    }} />
    <Modal open={Boolean(deleteError)} title="Không thể xóa bài/chapter" onClose={() => setDeleteError('')}><div className="mini-form"><div className="alert danger">{deleteError}</div><p className="helper">Kiểm tra tài liệu, câu hỏi, Release, mapping hoặc Quiz đang liên kết.</p><button className="btn" onClick={() => setDeleteError('')}>Đã hiểu</button></div></Modal>
    <Modal open={createOpen} title="Thêm bài" onClose={() => setCreateOpen(false)}><div className="mini-form"><label>Tên bài / Final test / Assignment<input className="input" value={chapterInput} onChange={(e) => setChapterInput(e.target.value)} /></label><p className="helper">Nhập số để tạo “Bài 1.2”; tên đặc biệt được giữ nguyên.</p><div className="modal-actions"><button className="btn secondary" onClick={() => setCreateOpen(false)}>Hủy</button><button className="btn" disabled={busy || !offering || !normalizeLessonInput(chapterInput)} onClick={() => run(async () => {
      if (!offering) return
      const nextNo = (summaries.reduce((max, item) => Math.max(max, Number(item.chapter.sort_order || item.chapter.chapter_no || 0)), 0) || 0) + 1
      await createSubjectChapter(headers, { subject_id: offering.subject_id, subject_offering_id: offering.id, title: buildChapterTitle(chapterInput), sort_order: nextNo }); setChapterInput(''); setCreateOpen(false)
    }, 'Đã thêm bài', load)}>Tạo bài</button></div></div></Modal>
  </div>
}
