'use client'

import Link from 'next/link'
import { useEffect, useMemo, useState } from 'react'
import { EnterpriseDataTable, type EnterpriseTableColumn } from '../../../../components/table/EnterpriseDataTable'
import { PageHeader, PageRoot } from '../../../../components/layout/PageHeader'
import { ContextBackLink } from '../../../../components/navigation/ContextBackLink'
import { useUrlTableState } from '../../../../hooks/useUrlTableState'
import type { Department, Subject, SubjectSummary } from '../../../../types'
import { createSubject, deleteSubject, getDepartment, getSubjectSummaries, updateSubject } from '../../../../lib/api'
import {
  BankTableStatusFilter,
  BankTableToolbar,
  Breadcrumb,
  ConfirmDialog,
  EntityActions,
  Modal,
  bankStatusMatches,
  emptyReviewStats,
  matchesSearch,
  reviewStatusText,
  useAsyncMessage,
  useBankData,
} from '../shared'

export function DepartmentSubjectsPage({ departmentId }: { departmentId: string }) {
  const { headers, canScope } = useBankData()
  const { message, busy, run } = useAsyncMessage()
  const { state: tableState, update: updateTableState } = useUrlTableState({ status: 'all', pageSize: 20, density: 'compact' })
  const [department, setDepartment] = useState<Department | null>(null)
  const [summaries, setSummaries] = useState<SubjectSummary[]>([])
  const [createOpen, setCreateOpen] = useState(false)
  const [code, setCode] = useState('')
  const [name, setName] = useState('')
  const [editing, setEditing] = useState<Subject | null>(null)
  const [editCode, setEditCode] = useState('')
  const [editName, setEditName] = useState('')
  const [deleteTarget, setDeleteTarget] = useState<Subject | null>(null)
  const departmentScope = { scopeType: 'DEPARTMENT' as const, scopeId: departmentId, departmentId }
  const canCreateSubject = canScope('subject.create', departmentScope)
  const canUpdateSubject = canScope('subject.update', departmentScope)

  const load = async () => {
    const [nextDepartment, nextSummaries] = await Promise.all([
      getDepartment(headers, departmentId),
      getSubjectSummaries(headers, departmentId),
    ])
    setDepartment(nextDepartment)
    setSummaries(nextSummaries)
  }
  useEffect(() => { load().catch(() => null) }, [departmentId]) // eslint-disable-line react-hooks/exhaustive-deps

  const statusFilter = tableState.status as BankTableStatusFilter
  const filtered = summaries.filter(({ subject, stats }) => matchesSearch(`${subject.code} ${subject.name}`, tableState.q) && bankStatusMatches(stats, statusFilter))
  const totalPages = Math.max(1, Math.ceil(filtered.length / tableState.pageSize))
  const safePage = Math.min(tableState.page, totalPages)
  const pageRows = filtered.slice((safePage - 1) * tableState.pageSize, safePage * tableState.pageSize)

  const openEdit = (subject: Subject) => {
    setEditing(subject)
    setEditCode(subject.code || '')
    setEditName(subject.name || '')
  }

  const columns = useMemo<EnterpriseTableColumn<SubjectSummary>[]>(() => [
    { key: 'stt', header: 'STT', kind: 'index', width: 52, sticky: 'left', hideable: false, render: (_row, index) => (safePage - 1) * tableState.pageSize + index + 1 },
    { key: 'subject', header: 'Môn học', kind: 'identity', minWidth: 300, sticky: 'left', hideable: false, render: ({ subject }) => <Link className="bank-table-link" href={`/bank/subjects/${subject.id}/versions`}><b>{subject.code}</b><small>{subject.name}</small></Link> },
    { key: 'status', header: 'Trạng thái', kind: 'status', width: 132, priority: 'important', hideable: true, render: ({ stats: rawStats }) => { const stats = rawStats || emptyReviewStats(); return <span className={`bank-row-status status-${stats.status || 'empty'}`}>{reviewStatusText(stats.status)}</span> } },
    { key: 'versions', header: 'Phiên bản', kind: 'number', width: 82, priority: 'important', hideable: true, render: ({ stats }) => stats?.subject_version_count || 0 },
    { key: 'approved', header: 'Đã duyệt', kind: 'number', width: 82, priority: 'important', hideable: true, render: ({ stats }) => stats?.review_done_version_count || 0 },
    { key: 'pending', header: 'Chờ duyệt', kind: 'number', width: 86, priority: 'important', hideable: true, render: ({ stats }) => stats?.review_not_done_version_count || 0 },
    { key: 'questions', header: 'Tổng câu', kind: 'number', width: 82, priority: 'optional', hideable: true, render: ({ stats }) => stats?.total_questions || 0 },
    { key: 'unresolved', header: 'Cần xử lý', kind: 'number', width: 86, priority: 'optional', hideable: true, defaultVisible: false, render: ({ stats }) => stats?.unresolved_count || 0 },
    { key: 'ready', header: 'Sẵn sàng', kind: 'number', width: 82, priority: 'optional', hideable: true, defaultVisible: false, render: ({ stats }) => stats?.ready_to_release_chapter_count || 0 },
    { key: 'actions', header: 'Thao tác', kind: 'actions', width: 118, sticky: 'right', hideable: false, render: ({ subject }) => <EntityActions canManage={canUpdateSubject} lockedLabel="Không có quyền" onEdit={() => openEdit(subject)} onDelete={() => setDeleteTarget(subject)} /> },
  ], [canUpdateSubject, safePage, tableState.pageSize])

  return <PageRoot className="page-stack bank-multipage">
    <PageHeader eyebrow="Ngân hàng đề" title="Môn học" />
    <ContextBackLink href={'/bank/departments'} label="Quay lại danh sách bộ môn" />
    {message ? <div className="alert info">{message}</div> : null}
    <section className="card">
      <BankTableToolbar search={tableState.q} setSearch={(q) => updateTableState({ q })} statusFilter={statusFilter} setStatusFilter={(status) => updateTableState({ status })} resultCount={filtered.length} totalCount={summaries.length} placeholder="Tìm mã môn hoặc tên môn" action={canCreateSubject ? <button className="btn" onClick={() => setCreateOpen(true)}>+ Thêm môn</button> : undefined} />
      <EnterpriseDataTable
        tableId={`bank-subjects-${departmentId}`}
        caption="Danh sách môn học"
        rows={pageRows}
        columns={columns}
        rowKey={({ subject }) => subject.id}
        density={tableState.density}
        onDensityChange={(density) => updateTableState({ density }, { resetPage: false })}
        page={safePage}
        pageSize={tableState.pageSize}
        total={filtered.length}
        totalPages={totalPages}
        onPageChange={(page) => updateTableState({ page }, { resetPage: false })}
        onPageSizeChange={(pageSize) => updateTableState({ pageSize, page: 1 }, { resetPage: false })}
        label="môn"
        emptyTitle={tableState.q || statusFilter !== 'all' ? 'Không có môn phù hợp' : 'Chưa có môn học'}
        emptyDescription={tableState.q || statusFilter !== 'all' ? 'Xóa bộ lọc hoặc thử từ khóa khác.' : 'Thêm môn đầu tiên cho bộ môn này.'}
      />
    </section>

    <Modal open={Boolean(editing)} title="Sửa môn" onClose={() => setEditing(null)}>
      <div className="mini-form">
        <label className="field-label">Mã môn</label><input className="input" value={editCode} onChange={(event) => setEditCode(event.target.value)} />
        <label className="field-label">Tên môn</label><input className="input" value={editName} onChange={(event) => setEditName(event.target.value)} />
        <div className="modal-actions"><button className="btn secondary" disabled={busy} onClick={() => setEditing(null)}>Hủy</button><button className="btn" disabled={busy || !editCode.trim() || !editName.trim()} onClick={() => {
          if (!editing) return
          run(async () => { await updateSubject(headers, editing.id, { code: editCode, name: editName }); setEditing(null) }, 'Đã sửa môn', load)
        }}>Lưu thay đổi</button></div>
      </div>
    </Modal>
    <ConfirmDialog open={Boolean(deleteTarget)} title={`Xóa môn ${deleteTarget?.code || ''}?`} description={<p>Chỉ xóa được khi môn chưa có phiên bản môn, bài hoặc câu hỏi bên trong.</p>} confirmLabel="Xác nhận xóa" danger busy={busy} onClose={() => setDeleteTarget(null)} onConfirm={() => {
      if (!deleteTarget) return
      run(async () => { await deleteSubject(headers, deleteTarget.id); setDeleteTarget(null) }, 'Đã xóa môn', load)
    }} />
    <Modal open={createOpen} title="Thêm môn" onClose={() => setCreateOpen(false)}>
      <div className="mini-form">
        <input className="input" value={code} onChange={(event) => setCode(event.target.value)} placeholder="Mã môn, ví dụ WEB107" />
        <input className="input" value={name} onChange={(event) => setName(event.target.value)} placeholder="Tên môn" />
        <div className="modal-actions"><button className="btn secondary" onClick={() => setCreateOpen(false)}>Hủy</button><button className="btn" disabled={busy || !code.trim() || !name.trim()} onClick={() => run(async () => {
          await createSubject(headers, { department_id: departmentId, code, name }); setCode(''); setName(''); setCreateOpen(false)
        }, 'Đã thêm môn', load)}>Lưu môn</button></div>
      </div>
    </Modal>
  </PageRoot>
}
