'use client'

import Link from 'next/link'
import { useRouter } from 'next/navigation'
import { useEffect, useMemo, useState } from 'react'
import { EnterpriseDataTable, type EnterpriseTableColumn } from '../../../../components/table/EnterpriseDataTable'
import { StatusBadge } from '../../../../components/ui/StatusBadge'
import { PageHeader, PageRoot } from '../../../../components/layout/PageHeader'
import { useUrlTableState } from '../../../../hooks/useUrlTableState'
import { BankHierarchyPageIntro } from '../BankHierarchyPageIntro'
import type { Department, Subject, SubjectOffering, SubjectVersionSummary } from '../../../../types'
import { createSubjectOffering, deleteSubjectOffering, getDepartment, getSubject, getSubjectVersionSummaries, updateSubjectOffering } from '../../../../lib/api'
import { BankTableStatusFilter, BankTableToolbar, Breadcrumb, ConfirmDialog, EntityActions, Modal, TERMS, bankStatusMatches, emptyReviewStats, matchesSearch, reviewStatusText, useAsyncMessage, useBankData } from '../shared'

export function SubjectVersionsPage({ subjectId }: { subjectId: string }) {
  const { headers, canScope } = useBankData()
  const { message, busy, run } = useAsyncMessage()
  const router = useRouter()
  const { state: tableState, update: updateTableState } = useUrlTableState({ status: 'all', pageSize: 20, density: 'compact' })
  const [department, setDepartment] = useState<Department | null>(null)
  const [subject, setSubject] = useState<Subject | null>(null)
  const [summaries, setSummaries] = useState<SubjectVersionSummary[]>([])
  const [createOpen, setCreateOpen] = useState(false)
  const [term, setTerm] = useState('SU25')
  const [mode, setMode] = useState<'blank' | 'clone'>('clone')
  const [cloneFromId, setCloneFromId] = useState('')
  const [editing, setEditing] = useState<SubjectOffering | null>(null)
  const [editCode, setEditCode] = useState('')
  const [editName, setEditName] = useState('')
  const [deleteTarget, setDeleteTarget] = useState<SubjectOffering | null>(null)
  const subjectScope = { scopeType: 'SUBJECT' as const, scopeId: subjectId, subjectId, departmentId: department?.id }
  const canUpdateSubject = canScope('subject.update', subjectScope)

  const load = async () => {
    const nextSubject = await getSubject(headers, subjectId)
    const [nextDepartment, nextSummaries] = await Promise.all([getDepartment(headers, nextSubject.department_id), getSubjectVersionSummaries(headers, subjectId)])
    setSubject(nextSubject); setDepartment(nextDepartment); setSummaries(nextSummaries)
    setCloneFromId((current) => current || nextSummaries[0]?.subject_version.id || '')
  }
  useEffect(() => { load().catch(() => null) }, [subjectId]) // eslint-disable-line react-hooks/exhaustive-deps

  const statusFilter = tableState.status as BankTableStatusFilter
  const filtered = summaries.filter(({ subject_version, stats }) => matchesSearch(`${subject_version.code} ${subject_version.name} ${subject_version.term || ''}`, tableState.q) && bankStatusMatches(stats, statusFilter))
  const totalPages = Math.max(1, Math.ceil(filtered.length / tableState.pageSize))
  const safePage = Math.min(tableState.page, totalPages)
  const pageRows = filtered.slice((safePage - 1) * tableState.pageSize, safePage * tableState.pageSize)

  const columns = useMemo<EnterpriseTableColumn<SubjectVersionSummary>[]>(() => [
    { key: 'stt', header: 'STT', kind: 'index', width: 52, sticky: 'left', hideable: false, render: (_row, index) => (safePage - 1) * tableState.pageSize + index + 1 },
    { key: 'version', header: 'Phiên bản môn', kind: 'identity', minWidth: 300, sticky: 'left', hideable: false, render: ({ subject_version }) => <Link className="bank-table-link" href={`/bank/subject-versions/${subject_version.id}/chapters`}><b>{subject_version.code}</b><small>{subject_version.name || subject_version.term || 'Phiên bản môn'}</small></Link> },
    { key: 'term', header: 'Học kỳ', kind: 'status', width: 96, priority: 'important', hideable: true, render: ({ subject_version }) => subject_version.term || '—' },
    { key: 'status', header: 'Trạng thái', kind: 'status', width: 136, priority: 'important', hideable: true, render: ({ stats: rawStats }) => { const stats = rawStats || emptyReviewStats(); const published = Boolean(stats.is_published || (stats.published_release_count || 0) > 0 || stats.status === 'published'); return <StatusBadge status={published ? 'published' : (stats.status || 'empty')} label={published ? 'Đã đưa lên CMS' : reviewStatusText(stats.status)} /> } },
    { key: 'chapters', header: 'Bài', kind: 'number', width: 68, priority: 'important', hideable: true, render: ({ stats }) => stats?.chapter_count || 0 },
    { key: 'questions', header: 'Tổng câu', kind: 'number', width: 92, priority: 'important', hideable: true, render: ({ stats }) => { const capacity = stats?.question_capacity || ((stats?.chapter_count || 0) * (stats?.chapter_question_limit || 100)); return `${stats?.total_questions || 0}/${capacity}` } },
    { key: 'approved', header: 'Đã duyệt', kind: 'number', width: 82, priority: 'important', hideable: true, render: ({ stats }) => stats?.approved_count || 0 },
    { key: 'unresolved', header: 'Chờ/lỗi', kind: 'number', width: 78, priority: 'optional', hideable: true, defaultVisible: false, render: ({ stats }) => stats?.unresolved_count || 0 },
    { key: 'published', header: 'Đã đưa CMS', kind: 'number', width: 92, priority: 'optional', hideable: true, defaultVisible: false, render: ({ stats }) => `${stats?.published_release_count || 0}/${stats?.chapter_count || 0}` },
    { key: 'actions', header: 'Thao tác', kind: 'actions', width: 118, sticky: 'right', hideable: false, render: ({ subject_version, stats }) => { const published = Boolean(stats?.is_published || (stats?.published_release_count || 0) > 0 || stats?.status === 'published'); return <EntityActions canManage={canUpdateSubject && !published} lockedLabel={published ? 'Đã khóa' : 'Không có quyền'} onEdit={() => { setEditing(subject_version); setEditCode(subject_version.code || ''); setEditName(subject_version.name || '') }} onDelete={() => setDeleteTarget(subject_version)} /> } },
  ], [canUpdateSubject, safePage, tableState.pageSize])

  return <PageRoot className="page-stack bank-multipage bank-hierarchy-list-page bank-subject-versions-page">
    <PageHeader
      eyebrow="Ngân hàng đề"
      title="Phiên bản môn"
      icon="bank"
      tone="blue"
      breadcrumbs={[{ label: 'Ngân hàng đề', href: '/bank/departments' }, { label: 'Phiên bản môn' }]}
    />
    <BankHierarchyPageIntro
      title="Phiên bản môn"
      description={subject
        ? `Quản lý phiên bản theo học kỳ, bài học và tiến độ duyệt của môn ${subject.code} — ${subject.name}.`
        : 'Quản lý phiên bản môn theo học kỳ, bài học và tiến độ duyệt trong phạm vi được phân quyền.'}
      icon="layers"
    />
    {message ? <div className="alert info">{message}</div> : null}
    <section className="bank-hierarchy-panel">
      <BankTableToolbar
        search={tableState.q}
        setSearch={(q) => updateTableState({ q })}
        statusFilter={statusFilter}
        setStatusFilter={(status) => updateTableState({ status })}
        resultCount={filtered.length}
        totalCount={summaries.length}
        placeholder="Tìm phiên bản, mã môn hoặc học kỳ"
        action={canUpdateSubject ? <button className="btn bank-hierarchy-create-button" type="button" onClick={() => setCreateOpen(true)}>+ Tạo phiên bản môn</button> : undefined}
      />
      <EnterpriseDataTable tableId={`bank-versions-${subjectId}`} caption="Danh sách phiên bản môn" rows={pageRows} columns={columns} rowKey={({ subject_version }) => subject_version.id} density={tableState.density} onDensityChange={(density) => updateTableState({ density }, { resetPage: false })} page={safePage} pageSize={tableState.pageSize} total={filtered.length} totalPages={totalPages} onPageChange={(page) => updateTableState({ page }, { resetPage: false })} onPageSizeChange={(pageSize) => updateTableState({ pageSize, page: 1 }, { resetPage: false })} label="phiên bản môn" emptyTitle={tableState.q || statusFilter !== 'all' ? 'Không có phiên bản phù hợp' : 'Chưa có phiên bản môn'} emptyDescription="Tạo phiên bản môn cuối cho học kỳ cần biên soạn." />
    </section>

    <Modal open={Boolean(editing)} title="Sửa phiên bản môn" onClose={() => setEditing(null)}><div className="mini-form"><label>Mã phiên bản<input className="input" value={editCode} onChange={(e) => setEditCode(e.target.value)} /></label><label>Tên phiên bản<input className="input" value={editName} onChange={(e) => setEditName(e.target.value)} /></label><div className="modal-actions"><button className="btn secondary" onClick={() => setEditing(null)}>Hủy</button><button className="btn" disabled={busy || !editCode.trim()} onClick={() => { if (!editing) return; run(async () => { await updateSubjectOffering(headers, editing.id, { code: editCode, name: editName }); setEditing(null) }, 'Đã sửa phiên bản môn', load) }}>Lưu thay đổi</button></div></div></Modal>
    <ConfirmDialog open={Boolean(deleteTarget)} title={`Xóa phiên bản môn ${deleteTarget?.code || ''}?`} description={<p>Chỉ xóa được khi phiên bản chưa có bài, tài liệu, câu hỏi hoặc Release.</p>} confirmLabel="Xác nhận xóa" danger busy={busy} onClose={() => setDeleteTarget(null)} onConfirm={() => { if (!deleteTarget) return; run(async () => { await deleteSubjectOffering(headers, deleteTarget.id); setDeleteTarget(null) }, 'Đã xóa phiên bản môn', load) }} />
    <Modal open={createOpen} title="Tạo phiên bản môn" onClose={() => setCreateOpen(false)}><div className="mini-form">
      <div className="button-row"><button className={mode === 'clone' ? 'btn' : 'btn secondary'} onClick={() => setMode('clone')}>Tạo từ phiên bản cũ</button><button className={mode === 'blank' ? 'btn' : 'btn secondary'} onClick={() => setMode('blank')}>Tạo mới hoàn toàn</button></div>
      <select className="input" value={term} onChange={(e) => setTerm(e.target.value)}>{TERMS.map(([value, label]) => <option value={value} key={value}>{value} - {label}</option>)}</select>
      {mode === 'clone' && <select className="input" value={cloneFromId} onChange={(e) => setCloneFromId(e.target.value)}>{summaries.map(({ subject_version }) => <option value={subject_version.id} key={subject_version.id}>Tạo từ {subject_version.code}</option>)}</select>}
      <p className="helper">Mỗi học kỳ chỉ được tạo một phiên bản môn cuối. Clone không tự sao chép Release hoặc Quiz.</p>
      <div className="modal-actions"><button className="btn secondary" onClick={() => setCreateOpen(false)}>Hủy</button><button className="btn" disabled={busy || !term || (mode === 'clone' && !cloneFromId)} onClick={() => run(async () => {
        const created = await createSubjectOffering(headers, { subject_id: subjectId, term, clone_from_offering_id: mode === 'clone' ? cloneFromId : null, version_code: term, clone_chapters: true, clone_materials: true, clone_questions: true }); setCreateOpen(false); router.push(`/bank/subject-versions/${created.id}/chapters`)
      }, 'Đã tạo phiên bản môn')}>Tạo phiên bản</button></div>
    </div></Modal>
  </PageRoot>
}
