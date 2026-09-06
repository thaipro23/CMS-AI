"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { getUdemyProgressStudents } from "../../lib/api";
import type { UdemyProgressStudent, UdemyProgressStudentList } from "../../types";
import { CompactFilterBar, WorkspaceSection } from "../operations/OperationsWorkspace";
import { EnterpriseDataTable, type EnterpriseTableColumn } from "../table/EnterpriseDataTable";
import { InlineNotice } from "../ui/InlineNotice";
import { StatusBadge } from "../ui/StatusBadge";

const EMPTY_ROWS: UdemyProgressStudentList = {
  items: [],
  total: 0,
  page: 1,
  page_size: 50,
  total_pages: 0,
  has_next: false,
};

type UdemyClassStatusFilter =
  | "all"
  | "on_track"
  | "late"
  | "no_plan"
  | "unmatched"
  | "ambiguous"
  | "outside_roster";

function percent(value?: number | null) {
  if (value == null || Number.isNaN(Number(value))) return "—";
  return `${Number(value).toLocaleString("vi-VN", { maximumFractionDigits: 2 })}%`;
}

function formatDate(value?: string | null) {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat("vi-VN", { dateStyle: "short" }).format(date);
}

function formatDateTime(value?: string | null) {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat("vi-VN", { dateStyle: "short", timeStyle: "short" }).format(date);
}

function progressStatus(row: UdemyProgressStudent) {
  if (row.status === "on_track") return <StatusBadge status="success" label="Đạt tiến độ" />;
  if (row.status === "late") return <StatusBadge status="failed" label="Chậm tiến độ" />;
  if (row.status === "no_plan") return <StatusBadge status="warning" label="Chưa có mốc" />;
  if (row.status === "outside_roster") return <StatusBadge status="warning" label="Ngoài danh sách lớp AP" />;
  if (row.status === "ambiguous") return <StatusBadge status="warning" label="Cần đối chiếu" />;
  return <StatusBadge status="failed" label="Chưa khớp AP" />;
}

export function UdemyClassProgressPanel({
  headers,
  deliveryId,
  classId,
  classCode,
}: {
  headers: HeadersInit;
  deliveryId: string;
  classId: string;
  classCode: string;
}) {
  const [rows, setRows] = useState<UdemyProgressStudentList>(EMPTY_ROWS);
  const [q, setQ] = useState("");
  const [appliedQ, setAppliedQ] = useState("");
  const [status, setStatus] = useState<UdemyClassStatusFilter>("all");
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(50);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const loadRows = useCallback(async () => {
    if (!deliveryId || !classId) return;
    setLoading(true);
    setError("");
    try {
      setRows(await getUdemyProgressStudents(headers, deliveryId, {
        q: appliedQ,
        classId,
        status,
        page,
        pageSize,
        sortBy: "student",
        sortDir: "asc",
      }));
    } catch (caught) {
      setRows(EMPTY_ROWS);
      setError(caught instanceof Error ? caught.message : "Không tải được tiến độ Udemy của lớp.");
    } finally {
      setLoading(false);
    }
  }, [appliedQ, classId, deliveryId, headers, page, pageSize, status]);

  useEffect(() => {
    void loadRows();
  }, [loadRows]);

  const columns = useMemo<EnterpriseTableColumn<UdemyProgressStudent>[]>(() => [
    {
      key: "stt",
      header: "STT",
      kind: "index",
      width: 54,
      hideable: false,
      render: (_row, index) => (page - 1) * pageSize + index + 1,
    },
    {
      key: "student",
      header: "Sinh viên",
      kind: "identity",
      minWidth: 240,
      sticky: "left",
      hideable: false,
      render: (row) => <>
        <b>{row.student_code || row.student_username || "Chưa khớp AP"}</b>
        <small>{row.display_name || row.email}</small>
        {row.email ? <small>{row.email}</small> : null}
      </>,
    },
    {
      key: "progress",
      header: "Tiến độ",
      kind: "progress",
      minWidth: 150,
      priority: "important",
      render: (row) => <><b>{percent(row.progress_percent)}</b><small>Yêu cầu {percent(row.required_progress_percent)}</small></>,
    },
    {
      key: "variance",
      header: "Chênh lệch",
      kind: "number",
      width: 112,
      priority: "important",
      render: (row) => row.variance_percent == null ? "—" : `${row.variance_percent > 0 ? "+" : ""}${percent(row.variance_percent)}`,
    },
    {
      key: "deadline",
      header: "Mốc hiện tại",
      kind: "date",
      minWidth: 135,
      priority: "optional",
      render: (row) => <><b>{formatDate(row.current_deadline_date)}</b>{row.current_plan_week ? <small>Tuần {row.current_plan_week}</small> : null}</>,
    },
    {
      key: "status",
      header: "Trạng thái",
      kind: "status",
      minWidth: 150,
      priority: "important",
      render: progressStatus,
    },
    {
      key: "match",
      header: "Đối chiếu AP",
      kind: "status",
      minWidth: 145,
      priority: "optional",
      render: (row) => row.match_status === "matched_roster"
        ? <StatusBadge status="success" label="Khớp danh sách AP" />
        : <StatusBadge status="warning" label={row.status_label || "Cần đối chiếu"} />,
    },
    {
      key: "updated",
      header: "Cập nhật",
      kind: "date",
      minWidth: 145,
      priority: "optional",
      render: (row) => formatDateTime(row.last_imported_at),
    },
  ], [page, pageSize]);

  return <WorkspaceSection
    title={`Tiến độ sinh viên Udemy · ${classCode || "Lớp"}`}
    icon="analytics"
    tone="green"
  >
    <InlineNotice notice={error ? { type: "error", title: "Không tải được tiến độ Udemy", body: error, onRetry: () => void loadRows(), retryLabel: "Thử lại" } : null} />
    <CompactFilterBar
      ariaLabel="Lọc tiến độ sinh viên Udemy của lớp"
      actions={<div className="button-row compact">
        <button className="btn secondary small" type="button" onClick={() => { setAppliedQ(q.trim()); setPage(1); }}>Áp dụng</button>
        <button className="btn secondary small" type="button" onClick={() => { setQ(""); setAppliedQ(""); setStatus("all"); setPage(1); }}>Xóa lọc</button>
      </div>}
    >
      <label>
        Tìm sinh viên
        <input
          className="input"
          value={q}
          onChange={(event) => setQ(event.target.value)}
          onKeyDown={(event) => { if (event.key === "Enter") { setAppliedQ(q.trim()); setPage(1); } }}
          placeholder="Mã SV, họ tên hoặc email..."
        />
      </label>
      <label>
        Trạng thái
        <select className="input" value={status} onChange={(event) => { setStatus(event.target.value as UdemyClassStatusFilter); setPage(1); }}>
          <option value="all">Tất cả</option>
          <option value="on_track">Đạt tiến độ</option>
          <option value="late">Chậm tiến độ</option>
          <option value="no_plan">Chưa có mốc đến hạn</option>
          <option value="unmatched">Chưa khớp AP</option>
          <option value="ambiguous">Cần đối chiếu</option>
          <option value="outside_roster">Ngoài danh sách lớp AP</option>
        </select>
      </label>
    </CompactFilterBar>

    <EnterpriseDataTable
      tableId="student-management-udemy-class-progress"
      caption={`Tiến độ Udemy lớp ${classCode || classId}`}
      rows={rows.items}
      columns={columns}
      rowKey={(row) => row.id}
      density="compact"
      loading={loading}
      error={error}
      onRetry={() => void loadRows()}
      page={rows.page || page}
      pageSize={rows.page_size || pageSize}
      total={rows.total}
      totalPages={Math.max(1, rows.total_pages || 1)}
      onPageChange={setPage}
      onPageSizeChange={(nextPageSize) => { setPageSize(nextPageSize); setPage(1); }}
      label="sinh viên"
      emptyTitle="Chưa có dữ liệu tiến độ Udemy của lớp"
      emptyDescription="Nếu lớp đã có dữ liệu AP nhưng chưa có tiến độ, hãy import báo cáo Udemy ở màn quản lý môn."
    />
  </WorkspaceSection>;
}
