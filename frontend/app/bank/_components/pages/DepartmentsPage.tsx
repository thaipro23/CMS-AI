'use client'

import Link from 'next/link'
import { useCallback, useEffect, useId, useMemo, useState } from 'react'
import { EnterpriseDataTable, type EnterpriseTableColumn } from '../../../../components/table/EnterpriseDataTable'
import { PageHeader, PageRoot } from '../../../../components/layout/PageHeader'
import { InlineNotice, type InlineNoticeData } from '../../../../components/ui/InlineNotice'
import { LoadingButton } from '../../../../components/ui/LoadingButton'
import { StatusBadge } from '../../../../components/ui/StatusBadge'
import { BankPageIdentity } from '../BankDesignContract'
import { useUrlTableState } from '../../../../hooks/useUrlTableState'
import type { Department, DepartmentSummary, Subject } from '../../../../types'
import { createDepartment, deleteDepartment, getDepartmentSummaries, searchSubjects, updateDepartment } from '../../../../lib/api'
import {
  BankTableStatusFilter,
  BankTableToolbar,
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

type DepartmentFormValue = {
  code: string
  name: string
}

function DepartmentFormDialog({
  open,
  mode,
  value,
  busy,
  onChange,
  onClose,
  onSubmit,
}: {
  open: boolean
  mode: 'create' | 'edit'
  value: DepartmentFormValue
  busy: boolean
  onChange: (value: DepartmentFormValue) => void
  onClose: () => void
  onSubmit: () => void
}) {
  const formId = useId()
  const codeId = `${formId}-code`
  const nameId = `${formId}-name`
  const valid = Boolean(value.code.trim() && value.name.trim())
  const isCreate = mode === 'create'

  return <Modal
    open={open}
    title={isCreate ? 'Thêm bộ môn' : 'Sửa bộ môn'}
    description={isCreate
      ? 'Bộ môn là cấp cao nhất của Ngân hàng đề. Mã bộ môn nên ngắn, ổn định và không trùng.'
      : 'Thay đổi tên hoặc mã hiển thị. Các môn học và dữ liệu bên trong không bị di chuyển.'}
    busy={busy}
    onClose={onClose}
    footer={<div className="modal-actions">
      <button className="btn secondary" type="button" disabled={busy} onClick={onClose}>Hủy</button>
      <LoadingButton
        className="btn"
        type="submit"
        form={formId}
        loading={busy}
        loadingLabel="Đang lưu..."
        disabled={!valid}
      >
        {isCreate ? 'Thêm bộ môn' : 'Lưu thay đổi'}
      </LoadingButton>
    </div>}
  >
    <form id={formId} className="enterprise-entity-form" onSubmit={(event) => { event.preventDefault(); if (valid && !busy) onSubmit() }}>
      <label htmlFor={codeId}>
        <span>Mã bộ môn <b aria-hidden="true">*</b></span>
        <input
          id={codeId}
          className="input"
          value={value.code}
          onChange={(event) => onChange({ ...value, code: event.target.value })}
          placeholder="Ví dụ: CNTT"
          autoComplete="off"
          required
          data-dialog-autofocus
        />
        <small>Dùng để nhận diện nhanh trong bảng và khi phân quyền phạm vi.</small>
      </label>
      <label htmlFor={nameId}>
        <span>Tên bộ môn <b aria-hidden="true">*</b></span>
        <input
          id={nameId}
          className="input"
          value={value.name}
          onChange={(event) => onChange({ ...value, name: event.target.value })}
          placeholder="Ví dụ: Công nghệ thông tin"
          autoComplete="off"
          required
        />
      </label>
    </form>
  </Modal>
}

export function DepartmentsPage() {
  const { headers, can, canScope } = useBankData()
  const { message, messageTone, busy, busyLabel, run } = useAsyncMessage()
  const { state: tableState, update: updateTableState } = useUrlTableState({ status: 'all', pageSize: 20, density: 'compact' })
  const [summaries, setSummaries] = useState<DepartmentSummary[]>([])
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState('')
  const [createOpen, setCreateOpen] = useState(false)
  const [createValue, setCreateValue] = useState<DepartmentFormValue>({ code: '', name: '' })
  const [editing, setEditing] = useState<Department | null>(null)
  const [editValue, setEditValue] = useState<DepartmentFormValue>({ code: '', name: '' })
  const [deleteTarget, setDeleteTarget] = useState<Department | null>(null)
  const [subjectResults, setSubjectResults] = useState<Subject[]>([])
  const [subjectSearching, setSubjectSearching] = useState(false)
  const [subjectSearchError, setSubjectSearchError] = useState('')
  const [subjectDepartmentFilter, setSubjectDepartmentFilter] = useState('all')

  const canCreateDepartment = can('department.manage_all')
  const search = tableState.q
  const statusFilter = tableState.status as BankTableStatusFilter

  const load = useCallback(async () => {
    setLoading(true)
    setLoadError('')
    try {
      setSummaries(await getDepartmentSummaries(headers))
    } catch (error) {
      setLoadError(error instanceof Error ? error.message : 'Không thể tải danh sách bộ môn.')
      throw error
    } finally {
      setLoading(false)
    }
  }, [headers])

  useEffect(() => {
    load().catch(() => null)
  }, [load])

  useEffect(() => {
    const query = search.trim()
    if (query.length < 2) {
      setSubjectResults([])
      setSubjectSearching(false)
      setSubjectSearchError('')
      return
    }
    const controller = new AbortController()
    const timer = window.setTimeout(() => {
      setSubjectSearching(true)
      setSubjectSearchError('')
      searchSubjects(headers, { query, signal: controller.signal })
        .then(setSubjectResults)
        .catch((error) => {
          if (controller.signal.aborted) return
          setSubjectSearchError(error instanceof Error ? error.message : 'Không thể tìm môn học.')
        })
        .finally(() => {
          if (!controller.signal.aborted) setSubjectSearching(false)
        })
    }, 250)
    return () => {
      window.clearTimeout(timer)
      controller.abort()
    }
  }, [headers, search])

  const visible = useMemo(() => summaries.filter(({ department, stats }) => (
    matchesSearch(`${department.code} ${department.name}`, search) && bankStatusMatches(stats, statusFilter)
  )), [search, statusFilter, summaries])

  const totalPages = Math.max(1, Math.ceil(visible.length / tableState.pageSize))
  const safePage = Math.min(tableState.page, totalPages)
  const pageRows = visible.slice((safePage - 1) * tableState.pageSize, safePage * tableState.pageSize)
  const departmentById = useMemo(() => new Map(
    summaries.map(({ department }) => [department.id, department]),
  ), [summaries])
  const visibleSubjectResults = useMemo(() => subjectResults.filter((subject) => (
    subjectDepartmentFilter === 'all' || subject.department_id === subjectDepartmentFilter
  )), [subjectDepartmentFilter, subjectResults])

  const openEditDepartment = (department: Department) => {
    setEditing(department)
    setEditValue({ code: department.code || '', name: department.name || '' })
  }

  const saveEditDepartment = () => {
    if (!editing) return
    const payload = { code: editValue.code.trim(), name: editValue.name.trim() }
    run(async () => {
      await updateDepartment(headers, editing.id, payload)
      setEditing(null)
    }, 'Đã cập nhật bộ môn.', load)
  }

  const createNewDepartment = () => {
    const payload = { code: createValue.code.trim(), name: createValue.name.trim() }
    run(async () => {
      await createDepartment(headers, payload)
      setCreateValue({ code: '', name: '' })
      setCreateOpen(false)
    }, 'Đã thêm bộ môn.', load)
  }

  const confirmDeleteDepartment = () => {
    if (!deleteTarget) return
    run(async () => {
      await deleteDepartment(headers, deleteTarget.id)
      setDeleteTarget(null)
    }, 'Đã xóa bộ môn.', load)
  }

  const columns = useMemo<EnterpriseTableColumn<DepartmentSummary>[]>(() => [
    {
      key: 'stt',
      header: 'STT',
      kind: 'index',
      width: 52,
      sticky: 'left',
      hideable: false,
      render: (_row, index) => (safePage - 1) * tableState.pageSize + index + 1,
    },
    {
      key: 'department',
      header: 'Bộ môn',
      kind: 'identity',
      minWidth: 320,
      sticky: 'left',
      hideable: false,
      render: ({ department }) => <Link className="bank-table-link" href={`/bank/departments/${department.id}/subjects`}>
        <b>{department.name}</b>
        <small>{department.code}</small>
      </Link>,
    },
    {
      key: 'status',
      header: 'Trạng thái',
      kind: 'status',
      width: 146,
      priority: 'important',
      hideable: true,
      render: ({ stats: rawStats }) => {
        const stats = rawStats || emptyReviewStats()
        return <StatusBadge status={stats.status || 'empty'} label={reviewStatusText(stats.status)} />
      },
    },
    {
      key: 'subjects',
      header: 'Môn',
      kind: 'number',
      width: 84,
      priority: 'important',
      hideable: true,
      render: ({ stats }) => stats?.subject_count || 0,
    },
    {
      key: 'approved',
      header: 'Đã duyệt',
      kind: 'number',
      width: 102,
      priority: 'important',
      hideable: true,
      render: ({ stats }) => stats?.review_done_subject_count || 0,
    },
    {
      key: 'pending',
      header: 'Chờ duyệt',
      kind: 'number',
      width: 92,
      priority: 'important',
      hideable: true,
      render: ({ stats }) => stats?.review_not_done_subject_count || 0,
    },
    {
      key: 'unresolved',
      header: 'Thay đổi chưa xử lý',
      kind: 'number',
      width: 138,
      priority: 'optional',
      hideable: true,
      defaultVisible: false,
      render: ({ stats }) => stats?.unresolved_count || 0,
    },
    {
      key: 'ready',
      header: 'Bài sẵn sàng chốt',
      kind: 'number',
      width: 126,
      priority: 'optional',
      hideable: true,
      defaultVisible: false,
      render: ({ stats }) => stats?.ready_to_release_chapter_count || 0,
    },
    {
      key: 'actions',
      header: 'Thao tác',
      kind: 'actions',
      width: 148,
      sticky: 'right',
      hideable: false,
      render: ({ department }) => <EntityActions
        canManage={canScope('department.update', { scopeType: 'DEPARTMENT', scopeId: department.id, departmentId: department.id })}
        lockedLabel="Chỉ xem"
        onEdit={() => openEditDepartment(department)}
        onDelete={() => setDeleteTarget(department)}
      />,
    },
  ], [canScope, safePage, tableState.pageSize])

  const operationNotice: InlineNoticeData | null = message ? {
    type: messageTone,
    title: messageTone === 'error' ? 'Không thể hoàn tất thao tác' : 'Đã cập nhật dữ liệu',
    body: message,
  } : null

  return <PageRoot className="page-stack bank-multipage bank-contract-page bank-departments-page bank-hierarchy-list-page">
    <PageHeader
      eyebrow="Ngân hàng đề"
      title="Bộ môn"
      icon="bank"
      tone="blue"
      breadcrumbs={[{ label: 'Ngân hàng đề', href: '/bank' }, { label: 'Bộ môn' }]}
    />

    <BankPageIdentity
      title="Bộ môn"
      description="Quản lý danh sách bộ môn, môn học và tiến độ duyệt trong phạm vi được phân quyền."
      icon="campus"
      actions={canCreateDepartment ? <button className="btn" type="button" onClick={() => setCreateOpen(true)}>+ Thêm bộ môn</button> : undefined}
    />

    <InlineNotice notice={operationNotice} />
    {busy ? <div className="inline-system-status" role="status" aria-live="polite"><span className="spinner tiny" aria-hidden="true" />{busyLabel}</div> : null}

    <section className="subject-quick-search" aria-label="Tìm bộ môn hoặc môn học">
      <div className="subject-quick-search-heading">
        <div><span>Tìm kiếm</span><b>Tìm bộ môn hoặc môn học</b></div>
        <small>Một ô tìm kiếm cho cả bảng bộ môn và truy cập nhanh môn học.</small>
      </div>
      <div className="subject-quick-search-controls">
        <div className="subject-quick-search-box">
          <span aria-hidden="true">⌕</span>
          <input
            className="input"
            value={search}
            onChange={(event) => updateTableState({ q: event.target.value })}
            placeholder="Tìm bộ môn hoặc môn học, ví dụ CNTT, Cơ điện, MEC229..."
            aria-label="Tìm bộ môn hoặc môn học"
            autoComplete="off"
          />
          {subjectSearching ? <span className="spinner tiny" aria-label="Đang tìm" /> : null}
          {search ? <button type="button" className="icon-button" aria-label="Xóa từ khóa" onClick={() => updateTableState({ q: '' })}>×</button> : null}
        </div>
        <label className="subject-quick-search-filter">
          <span>Bộ môn</span>
          <select className="input" aria-label="Lọc kết quả theo bộ môn" value={subjectDepartmentFilter} onChange={(event) => setSubjectDepartmentFilter(event.target.value)}>
            <option value="all">Tất cả bộ môn</option>
            {summaries.map(({ department }) => <option key={department.id} value={department.id}>{department.code} · {department.name}</option>)}
          </select>
        </label>
      </div>
      {subjectSearchError ? <div className="alert error">{subjectSearchError}</div> : null}
      {search.trim().length >= 2 && !subjectSearching && !subjectSearchError ? <div className="subject-quick-search-results">
        <div className="subject-quick-search-result-meta"><span>{visibleSubjectResults.length} môn phù hợp</span><small>Kết quả trong phạm vi được phân quyền</small></div>
        {visibleSubjectResults.length ? visibleSubjectResults.map((subject) => {
          const department = departmentById.get(subject.department_id)
          return <Link key={subject.id} href={`/bank/subjects/${subject.id}/versions`}>
            <span className="subject-quick-search-code">{subject.code}</span>
            <span><b>{subject.name}</b><small>{department ? `${department.code} · ${department.name}` : 'Bộ môn trong phạm vi được phân quyền'}</small></span>
            <StatusBadge status={subject.status} label={subject.status === 'active' ? 'Hoạt động' : 'Tạm khóa'} />
            <strong>Mở môn →</strong>
          </Link>
        }) : <p>Không tìm thấy môn phù hợp.</p>}
      </div> : null}
    </section>

    <section className="bank-hierarchy-panel" aria-label="Danh sách bộ môn">
      <BankTableToolbar
        search={search}
        setSearch={(value) => updateTableState({ q: value })}
        statusFilter={statusFilter}
        setStatusFilter={(value) => updateTableState({ status: value })}
        resultCount={visible.length}
        totalCount={summaries.length}
        placeholder="Tìm bộ môn hoặc môn học..."
        hideSearch
      />

      <EnterpriseDataTable
        tableId="bank-departments"
        caption="Danh sách bộ môn"
        rows={pageRows}
        columns={columns}
        rowKey={({ department }) => department.id}
        density={tableState.density}
        onDensityChange={(density) => updateTableState({ density }, { resetPage: false })}
        loading={loading}
        error={loadError}
        onRetry={() => load().catch(() => null)}
        page={safePage}
        pageSize={tableState.pageSize}
        total={visible.length}
        totalPages={totalPages}
        onPageChange={(page) => updateTableState({ page }, { resetPage: false })}
        onPageSizeChange={(pageSize) => updateTableState({ pageSize, page: 1 }, { resetPage: false })}
        label="bộ môn"
        emptyTitle={search || statusFilter !== 'all' ? 'Không có kết quả phù hợp' : 'Chưa có bộ môn'}
        emptyDescription={search || statusFilter !== 'all'
          ? 'Xóa bộ lọc hoặc thử từ khóa khác.'
          : 'Thêm bộ môn đầu tiên để bắt đầu cấu trúc Ngân hàng đề.'}
        emptyAction={!search && statusFilter === 'all' && canCreateDepartment
          ? <button className="btn" type="button" onClick={() => setCreateOpen(true)}>Thêm bộ môn</button>
          : undefined}
      />
    </section>

    <DepartmentFormDialog
      open={createOpen}
      mode="create"
      value={createValue}
      busy={busy}
      onChange={setCreateValue}
      onClose={() => setCreateOpen(false)}
      onSubmit={createNewDepartment}
    />

    <DepartmentFormDialog
      open={Boolean(editing)}
      mode="edit"
      value={editValue}
      busy={busy}
      onChange={setEditValue}
      onClose={() => setEditing(null)}
      onSubmit={saveEditDepartment}
    />

    <ConfirmDialog
      open={Boolean(deleteTarget)}
      title={`Xóa bộ môn ${deleteTarget?.code || ''}?`}
      description={<p>Bộ môn <b>{deleteTarget?.name || ''}</b> chỉ có thể xóa khi chưa có môn học bên trong. Thao tác xóa không thể hoàn tác.</p>}
      confirmLabel="Xóa bộ môn"
      danger
      busy={busy}
      onClose={() => setDeleteTarget(null)}
      onConfirm={confirmDeleteDepartment}
    />
  </PageRoot>
}
