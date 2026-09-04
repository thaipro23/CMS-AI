from pathlib import Path
import re


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if old not in text:
        raise SystemExit(f'{label}: marker not found')
    return text.replace(old, new, 1)


# ---------------------------------------------------------------------------
# 1) Show class-scoped Udemy progress directly on the student class page.
# ---------------------------------------------------------------------------
component_path = Path('frontend/components/student-management/UdemyClassProgressPanel.tsx')
component_path.parent.mkdir(parents=True, exist_ok=True)
component_path.write_text(r'''"use client";

import Link from "next/link";
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
  if (row.status === "outside_roster") return <StatusBadge status="warning" label="Ngoài roster AP" />;
  if (row.status === "ambiguous") return <StatusBadge status="warning" label="Cần đối chiếu" />;
  return <StatusBadge status="failed" label="Chưa khớp AP" />;
}

export function UdemyClassProgressPanel({
  headers,
  deliveryId,
  classId,
  classCode,
  managementHref,
}: {
  headers: HeadersInit;
  deliveryId: string;
  classId: string;
  classCode: string;
  managementHref: string;
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
        ? <StatusBadge status="success" label="Đúng roster" />
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
    description="Hiển thị trực tiếp dữ liệu Udemy của đúng lớp này; không cần chuyển sang màn quản lý môn chỉ để xem tiến độ."
    icon="analytics"
    tone="green"
    actions={<Link className="btn secondary small" href={managementHref}>Import / kế hoạch Udemy</Link>}
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
          <option value="outside_roster">Ngoài roster AP</option>
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
''')

class_page_path = Path('frontend/app/student-management/classes/[classId]/page.tsx')
class_page = class_page_path.read_text()
class_page = replace_once(
    class_page,
    "import { AppIcon } from '../../../../components/icons/AppIcon'\n",
    "import { AppIcon } from '../../../../components/icons/AppIcon'\nimport { UdemyClassProgressPanel } from '../../../../components/student-management/UdemyClassProgressPanel'\n",
    'class page Udemy component import',
)
class_page = replace_once(
    class_page,
    '      primaryAction={isUdemyClass ? <Link className="btn primary" href={udemyDashboardHref}>Xem tiến độ Udemy</Link> : <Link className="btn primary" href={behaviorHref}>Phân tích học tập</Link>}\n',
    '      primaryAction={isUdemyClass ? (classInfo?.subject_delivery_id ? <Link className="btn primary" href={udemyDashboardHref}>Import / kế hoạch Udemy</Link> : undefined) : <Link className="btn primary" href={behaviorHref}>Phân tích học tập</Link>}\n',
    'class page primary Udemy action',
)
class_page = replace_once(
    "      {isUdemyClass ? <InlineNotice notice={{ ...noticeInfo('Điểm và tiến độ lấy từ file Udemy. Full CMS, Enrollment và cập nhật điểm Open edX đã được ẩn để tránh chạy sai nền tảng.', 'Lớp đang vận hành trên Udemy'), actionHref: udemyDashboardHref, actionLabel: 'Mở quản lý Udemy' }} /> : null}\n",
    "      {isUdemyClass ? <InlineNotice notice={{ ...noticeInfo('Điểm và tiến độ lấy từ file Udemy. Tiến độ từng sinh viên được hiển thị ngay bên dưới; chỉ mở quản lý môn khi cần import file hoặc chỉnh kế hoạch.', 'Lớp đang vận hành trên Udemy'), actionHref: classInfo?.subject_delivery_id ? udemyDashboardHref : undefined, actionLabel: classInfo?.subject_delivery_id ? 'Import / kế hoạch Udemy' : undefined }} /> : null}\n",
    'class page Udemy notice',
)
insert_marker = "    </section>\n\n    {!isUdemyClass ? <>"
insert_value = """    </section>\n\n    {isUdemyClass && classInfo?.subject_delivery_id ? <UdemyClassProgressPanel\n      headers={headers}\n      deliveryId={classInfo.subject_delivery_id}\n      classId={classId}\n      classCode={classInfo.class_code || 'Lớp'}\n      managementHref={udemyDashboardHref}\n    /> : null}\n\n    {!isUdemyClass ? <>"""
class_page = replace_once(class_page, insert_marker, insert_value, 'class page direct Udemy progress insertion')
class_page_path.write_text(class_page)


# ---------------------------------------------------------------------------
# 2) Rebuild legacy quiz import page using the same enterprise page contract
#    as the rest of Dash-CMS. All page-specific styling lives in a CSS module.
# ---------------------------------------------------------------------------
import_page_path = Path('frontend/app/import-quiz-cms-old/page.tsx')
import_page_path.write_text(r'''"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { EnterpriseScreenHeader } from "../../components/layout/EnterpriseDesignContract";
import { PageRoot } from "../../components/layout/PageHeader";
import { OperationsKpiStrip, WorkspaceSection } from "../../components/operations/OperationsWorkspace";
import { InlineNotice } from "../../components/ui/InlineNotice";
import { StatusBadge } from "../../components/ui/StatusBadge";
import {
  enqueueLegacyQuizCmsOldImport,
  getBankOperationJob,
  previewLegacyQuizCmsOldImport,
  skipInvalidLegacyQuizCmsOldQuestions,
} from "../../lib/api";
import type { BankOperationJob, LegacyQuizCmsOldImportPreview } from "../../types";
import { useBankData } from "../bank/_components/shared";
import styles from "./page.module.css";

const TERMINAL_JOB_STATUSES = new Set(["completed", "failed", "canceled"]);
type LegacyImportError = LegacyQuizCmsOldImportPreview["errors"][number];

const ERROR_LABELS: Record<string, string> = {
  MISSING_IMAGE: "Thiếu ảnh câu hỏi",
  SUBJECT_NOT_FOUND: "Không tìm thấy môn đích",
  SUBJECT_AMBIGUOUS: "Mã môn không duy nhất",
  INVALID_QUESTION: "Câu hỏi không hợp lệ",
  BANK_PREFLIGHT_FAILED: "Câu chưa đạt kiểm tra kho đề/CMS",
  INVALID_TYPE: "TYPE không hợp lệ",
  INVALID_DIFFICULTY: "NGƯỠNG không hợp lệ",
  INVALID_WORKBOOK: "File Excel không hợp lệ",
  INVALID_SHEET: "Sheet không hợp lệ",
};

function fileSize(value: number) {
  if (value < 1024 * 1024) return `${Math.max(1, Math.round(value / 1024))} KB`;
  return `${(value / 1024 / 1024).toFixed(1)} MB`;
}

function typeLabel(value: string) {
  return ({
    single_select: "Chọn một đáp án đúng",
    multi_select: "Chọn nhiều đáp án đúng",
    dropdown_fill: "Chọn và điền vào ô trống",
  } as Record<string, string>)[value] || value;
}

function difficultyLabel(value: string) {
  return ({
    easy: "Dễ",
    medium: "Trung bình",
    hard: "Khó",
    unclassified: "Chưa phân loại",
  } as Record<string, string>)[value] || value;
}

function mergeFiles(current: File[], incoming: File[]) {
  const files = new Map(current.map((file) => [`${file.name}:${file.size}:${file.lastModified}`, file]));
  incoming.forEach((file) => files.set(`${file.name}:${file.size}:${file.lastModified}`, file));
  return Array.from(files.values());
}

function FileList({ files, onRemove }: { files: File[]; onRemove: (index: number) => void }) {
  if (!files.length) return null;
  return <div className={styles.fileList}>
    {files.map((file, index) => <div className={styles.fileRow} key={`${file.name}-${file.lastModified}-${index}`}>
      <div className={styles.fileCopy}><b>{file.name}</b><small>{fileSize(file.size)}</small></div>
      <button type="button" className="btn secondary small" aria-label={`Bỏ ${file.name}`} onClick={() => onRemove(index)}>Bỏ</button>
    </div>)}
  </div>;
}

function ImportSteps({ current }: { current: number }) {
  const steps = [
    ["1", "Chọn tệp", "Excel và ảnh đi kèm"],
    ["2", "Kiểm tra & xử lý", "Môn, sheet, đáp án, ảnh"],
    ["3", "Xác nhận import", "Tạo câu Chờ duyệt"],
  ];
  return <section className={styles.steps} aria-label="Tiến trình import">
    {steps.map(([number, title, description], index) => {
      const step = index + 1;
      const stateClass = step < current ? styles.stepDone : step === current ? styles.stepCurrent : "";
      return <div className={`${styles.step} ${stateClass}`.trim()} key={number} aria-current={step === current ? "step" : undefined}>
        <span className={styles.stepNumber}>{step < current ? "✓" : number}</span>
        <div><b>{title}</b><small>{description}</small></div>
      </div>;
    })}
  </section>;
}

export default function ImportQuizCmsOldPage() {
  const { headers } = useBankData();
  const [workbooks, setWorkbooks] = useState<File[]>([]);
  const [assets, setAssets] = useState<File[]>([]);
  const [preview, setPreview] = useState<LegacyQuizCmsOldImportPreview | null>(null);
  const [job, setJob] = useState<BankOperationJob | null>(null);
  const [busyAction, setBusyAction] = useState<"preview" | "skip" | "enqueue" | null>(null);
  const [error, setError] = useState("");
  const busy = Boolean(busyAction);

  const resetResult = () => {
    setPreview(null);
    setJob(null);
    setError("");
  };

  const workbookBytes = useMemo(() => workbooks.reduce((sum, file) => sum + file.size, 0), [workbooks]);
  const assetBytes = useMemo(() => assets.reduce((sum, file) => sum + file.size, 0), [assets]);
  const errorGroups = useMemo(() => {
    const groups = new Map<string, LegacyImportError[]>();
    for (const item of preview?.errors || []) {
      const code = item.code || "INVALID_DATA";
      groups.set(code, [...(groups.get(code) || []), item]);
    }
    return Array.from(groups, ([code, items]) => ({ code, items }))
      .sort((left, right) => right.items.length - left.items.length);
  }, [preview]);

  useEffect(() => {
    if (!job || TERMINAL_JOB_STATUSES.has(job.status)) return;
    const timer = window.setInterval(() => {
      getBankOperationJob(headers, job.id).then(setJob).catch(() => null);
    }, 2_000);
    return () => window.clearInterval(timer);
  }, [headers, job]);

  const runPreview = async (selectedAssets: File[] = assets) => {
    if (!workbooks.length) return;
    setBusyAction("preview");
    setError("");
    setPreview(null);
    setJob(null);
    try {
      setPreview(await previewLegacyQuizCmsOldImport(headers, workbooks, selectedAssets));
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Không thể kiểm tra file import.");
    } finally {
      setBusyAction(null);
    }
  };

  const startImport = async () => {
    if (!preview?.can_commit) return;
    setBusyAction("enqueue");
    setError("");
    try {
      const queued = await enqueueLegacyQuizCmsOldImport(headers, preview.preview_token);
      setJob(queued.job);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Không thể tạo tác vụ import.");
    } finally {
      setBusyAction(null);
    }
  };

  const skipInvalidQuestions = async () => {
    if (!preview?.can_skip_invalid_questions) return;
    setBusyAction("skip");
    setError("");
    try {
      setPreview(await skipInvalidLegacyQuizCmsOldQuestions(headers, preview.preview_token));
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Không thể bỏ qua các câu lỗi.");
    } finally {
      setBusyAction(null);
    }
  };

  const addAssets = (incoming: File[], recheck = false) => {
    if (!incoming.length) return;
    const nextAssets = mergeFiles(assets, incoming);
    setAssets(nextAssets);
    resetResult();
    if (recheck && workbooks.length) void runPreview(nextAssets);
  };

  const result = (job?.result || {}) as Record<string, unknown>;
  const currentStep = job || preview?.can_commit ? 3 : preview ? 2 : 1;
  const readyQuestionCount = preview ? Math.max(0, preview.question_count - preview.invalid_question_count) : 0;
  const unclassifiedDifficultyCount = Number(preview?.difficulty_counts.unclassified || 0);
  const targetSubjects = preview?.workbooks
    .filter((workbook) => workbook.subject_code)
    .map((workbook) => `${workbook.subject_code} · ${workbook.subject_name}`)
    .join(", ");

  return <PageRoot className={`page-stack enterprise-standard-page ux-enterprise-page ${styles.page}`}>
    <EnterpriseScreenHeader
      eyebrow="Ngân hàng đề"
      title="Import Quiz CMS cũ"
      description="Kiểm tra Excel, xử lý lỗi ngay từ bước import rồi đưa câu hợp lệ vào đúng môn, đúng bài của phiên bản SU26."
      icon="upload"
      tone="blue"
      breadcrumbs={[{ label: "Ngân hàng đề", href: "/bank/departments" }, { label: "Import Quiz CMS cũ" }]}
      meta={<span className="soft-tag">Đích cố định · SU26</span>}
      secondaryActions={<Link className="btn secondary" href="/bank/departments">Ngân hàng đề</Link>}
    />

    <ImportSteps current={currentStep} />

    <WorkspaceSection
      title="Quy tắc dữ liệu legacy"
      description="Kiểm tra ngay trước khi ghi vào kho đề; validation trong kho đề và khi publish vẫn được giữ làm lớp bảo vệ tiếp theo."
      icon="info"
      tone="blue"
    >
      <div className={styles.ruleGrid}>
        <div><span>TYPE</span><b>0 · Một đáp án</b><small>1 · Nhiều đáp án · 2 · Điền ô trống</small></div>
        <div><span>NGƯỠNG</span><b>1 · Dễ · 2 · Trung bình</b><small>3 · Khó; thiếu ngưỡng vẫn được nhận và xếp quota linh hoạt.</small></div>
        <div><span>ẢNH</span><b>Kiểm tra trước khi import</b><small>Thiếu ảnh có thể bổ sung và kiểm tra lại hoặc bỏ đúng câu lỗi.</small></div>
      </div>
    </WorkspaceSection>

    {!preview ? <WorkspaceSection
      title="1. Chọn nguồn import"
      description="Tên file phải bắt đầu bằng mã môn. Mỗi sheet tương ứng một Bài trong SU26. Bước này chưa ghi dữ liệu."
      icon="upload"
      tone="blue"
      actions={<button className="btn" type="button" disabled={busy || !workbooks.length} onClick={() => void runPreview()}>{busyAction === "preview" ? "Đang kiểm tra..." : "Kiểm tra file"}</button>}
    >
      <div className={styles.uploadGrid}>
        <section className={styles.uploadCard}>
          <div className={styles.uploadHeading}><span>01</span><div><h3>File Excel câu hỏi</h3><p>Tối đa 20 file <code>.xlsx</code>.</p></div></div>
          <label className={`${styles.filePicker} btn secondary`}>
            Chọn file Excel
            <input hidden type="file" accept=".xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" multiple disabled={busy} onChange={(event) => { setWorkbooks(Array.from(event.target.files || [])); resetResult(); event.currentTarget.value = ""; }} />
          </label>
          <FileList files={workbooks} onRemove={(index) => { setWorkbooks((current) => current.filter((_, itemIndex) => itemIndex !== index)); resetResult(); }} />
          <small>{workbooks.length ? `${workbooks.length} file · ${fileSize(workbookBytes)}` : "Ví dụ: MEC229 - Đồ gá.xlsx"}</small>
        </section>

        <section className={styles.uploadCard}>
          <div className={styles.uploadHeading}><span>02</span><div><h3>Ảnh đi kèm</h3><p>Không bắt buộc ở lần chọn đầu; nhận ảnh trực tiếp hoặc ZIP.</p></div></div>
          <label className={`${styles.filePicker} btn secondary`}>
            Chọn ảnh hoặc ZIP
            <input hidden type="file" accept=".png,.jpg,.jpeg,.webp,.zip,image/png,image/jpeg,image/webp,application/zip" multiple disabled={busy} onChange={(event) => { addAssets(Array.from(event.target.files || [])); event.currentTarget.value = ""; }} />
          </label>
          <FileList files={assets} onRemove={(index) => { setAssets((current) => current.filter((_, itemIndex) => itemIndex !== index)); resetResult(); }} />
          <small>{assets.length ? `${assets.length} file · ${fileSize(assetBytes)}` : "Có thể bổ sung sau khi hệ thống xác định đúng câu thiếu ảnh."}</small>
        </section>
      </div>
    </WorkspaceSection> : null}

    <InlineNotice notice={error ? { type: "error", title: "Không thể hoàn tất", body: error } : null} />

    {preview ? <>
      <WorkspaceSection
        title="2. Kết quả kiểm tra"
        description={`${targetSubjects || "Chưa xác định được môn đích"} · ${preview.workbook_count} file · ${preview.sheet_count} sheet`}
        icon="search"
        tone={preview.can_commit ? "green" : "amber"}
        actions={<div className="button-row compact"><StatusBadge status={preview.can_commit ? "ready" : "failed"} label={preview.can_commit ? "Sẵn sàng import" : "Cần xử lý"} /><button className="btn secondary small" type="button" disabled={busy} onClick={resetResult}>Đổi tệp</button></div>}
      >
        <OperationsKpiStrip ariaLabel="Tổng quan kết quả import" items={[
          { label: "Tổng câu nguồn", value: preview.original_question_count, hint: `${preview.sheet_count} sheet`, icon: "book" },
          { label: "Câu hợp lệ", value: readyQuestionCount, hint: "Sẽ đưa vào Chờ duyệt", tone: "success", icon: "check" },
          { label: "Câu cần xử lý", value: preview.invalid_question_count, hint: preview.missing_image_question_count ? `${preview.missing_image_question_count} câu thiếu ảnh` : "Không còn lỗi cấp câu", tone: preview.invalid_question_count ? "danger" : "success", icon: "alert" },
          { label: "Chưa có độ khó", value: unclassifiedDifficultyCount, hint: "Xếp quota linh hoạt", tone: unclassifiedDifficultyCount ? "warning" : "neutral", icon: "analytics" },
        ]} />
      </WorkspaceSection>

      <div className={styles.reviewGrid}>
        <WorkspaceSection
          title="Đối chiếu môn và bài"
          description="Mỗi sheet tạo hoặc dùng lại đúng Bài tương ứng trong SU26."
          icon="book"
          tone="blue"
        >
          <div className={styles.tableScroll}>
            <table className={styles.sheetTable}>
              <thead><tr><th>File</th><th>Sheet</th><th>Bài</th><th>Câu</th><th>Loại câu</th><th>Độ khó</th><th>Kiểm tra</th></tr></thead>
              <tbody>
                {preview.workbooks.flatMap((workbook) => workbook.sheets.map((sheet) => <tr key={`${workbook.filename}-${sheet.sheet_name}`}>
                  <td><b>{workbook.filename}</b><small>{workbook.subject_code ? `${workbook.subject_code} · ${workbook.subject_name}` : "Chưa khớp môn"}</small></td>
                  <td>{sheet.sheet_name}</td>
                  <td>Bài {sheet.chapter_no}</td>
                  <td>{sheet.question_count}</td>
                  <td>{Object.entries(sheet.type_counts).map(([key, count]) => `${typeLabel(key)}: ${count}`).join(" · ")}</td>
                  <td>{Object.entries(sheet.difficulty_counts).map(([key, count]) => `${difficultyLabel(key)}: ${count}`).join(" · ")}</td>
                  <td><StatusBadge status={sheet.error_count ? "failed" : sheet.warning_count ? "warning" : "success"} label={sheet.error_count ? `${sheet.error_count} lỗi` : sheet.warning_count ? `${sheet.warning_count} cảnh báo` : "Hợp lệ"} /></td>
                </tr>))}
              </tbody>
            </table>
          </div>
        </WorkspaceSection>

        <WorkspaceSection
          title="Xử lý lỗi và cảnh báo"
          description="Chỉ lỗi cấp câu mới được bỏ qua; lỗi môn, file hoặc sheet vẫn phải sửa."
          icon="alert"
          tone={preview.errors.length ? "amber" : "green"}
        >
          <div className={styles.issueStack}>
            {preview.can_skip_invalid_questions ? <>
              <InlineNotice notice={{ type: "warning", title: "Có câu cần quyết định", body: preview.missing_image_question_count ? `${preview.missing_image_question_count} câu đang thiếu ảnh. Bổ sung ảnh để kiểm tra lại hoặc bỏ đúng các câu lỗi khỏi lần import này.` : `${preview.invalid_question_count} câu đang lỗi. Có thể bỏ các câu này khỏi lần import hiện tại.` }} />
              <div className={styles.issueActions}>
                {preview.missing_image_question_count ? <label className="btn secondary">
                  Bổ sung ảnh và kiểm tra lại
                  <input hidden type="file" accept=".png,.jpg,.jpeg,.webp,.zip,image/png,image/jpeg,image/webp,application/zip" multiple disabled={busy} onChange={(event) => { addAssets(Array.from(event.target.files || []), true); event.currentTarget.value = ""; }} />
                </label> : null}
                <button className="btn danger" type="button" disabled={busy} onClick={() => void skipInvalidQuestions()}>{busyAction === "skip" ? "Đang loại câu lỗi..." : `Bỏ qua ${preview.invalid_question_count} câu lỗi`}</button>
              </div>
            </> : null}

            {errorGroups.length ? errorGroups.map(({ code, items }, groupIndex) => <details className={styles.issueGroup} key={code} open={groupIndex === 0}>
              <summary><span><b>{ERROR_LABELS[code] || code}</b><small>{code}</small></span><strong>{items.length}</strong></summary>
              <div className={styles.issueItems}>
                {items.slice(0, 12).map((item, index) => <div className={styles.issueItem} key={`${code}-${item.workbook}-${item.sheet}-${item.row}-${index}`}>
                  <small>{[item.workbook, item.sheet, item.row ? `dòng ${item.row}` : "", item.field].filter(Boolean).join(" · ")}</small>
                  <p>{item.message}</p>
                </div>)}
                {items.length > 12 ? <small>Còn {items.length - 12} lỗi cùng nhóm.</small> : null}
              </div>
            </details>) : <InlineNotice notice={{ type: "success", title: "Không còn lỗi chặn", body: "Dữ liệu đã qua preflight và có thể chuyển sang bước xác nhận import." }} />}

            {preview.skipped_invalid_questions.length ? <details className={styles.issueGroup} open>
              <summary><span><b>Câu đã bỏ qua</b><small>Không được tạo trong ngân hàng đề</small></span><strong>{preview.skipped_invalid_question_count}</strong></summary>
              <div className={styles.issueItems}>{preview.skipped_invalid_questions.slice(0, 12).map((item, index) => <div className={styles.issueItem} key={`${item.workbook}-${item.sheet}-${item.row}-${index}`}><b>{item.error_codes?.join(", ") || "INVALID_QUESTION"}</b><small>{[item.sheet, item.row ? `dòng ${item.row}` : ""].filter(Boolean).join(" · ")}</small></div>)}</div>
            </details> : null}

            {preview.warnings.length ? <details className={styles.issueGroup}>
              <summary><span><b>Cảnh báo</b><small>Không chặn import</small></span><strong>{preview.warnings.length}</strong></summary>
              <div className={styles.issueItems}>{preview.warnings.slice(0, 20).map((warning, index) => <div className={styles.issueItem} key={`${warning}-${index}`}><p>{warning}</p></div>)}</div>
            </details> : null}
          </div>
        </WorkspaceSection>
      </div>

      {!job ? <WorkspaceSection
        title="3. Xác nhận import"
        description="Mọi câu mới đều ghi nhận người import và vào trạng thái Chờ duyệt. Validation trong kho đề/publish vẫn tiếp tục chạy."
        icon="check"
        tone={preview.can_commit ? "green" : "amber"}
        actions={<button className="btn" type="button" disabled={busy || !preview.can_commit} onClick={() => void startImport()}>{busyAction === "enqueue" ? "Đang tạo tác vụ..." : "Import vào SU26"}</button>}
      >
        <InlineNotice notice={{
          type: preview.can_commit ? "success" : "warning",
          title: preview.can_commit ? `Sẵn sàng import ${preview.question_count} câu` : "Chưa thể import",
          body: `${preview.message} Câu thiếu concept/độ khó vẫn được nhận và xếp linh hoạt khi tạo Quiz.`,
        }} />
      </WorkspaceSection> : null}
    </> : null}

    {job ? <WorkspaceSection
      title="Tác vụ import"
      description={job.progress_label || "Đang xử lý dữ liệu legacy trong tác vụ nền."}
      icon="jobs"
      tone={job.status === "failed" ? "red" : job.status === "completed" ? "green" : "blue"}
      actions={<StatusBadge status={job.status} label={job.status === "completed" ? "Hoàn tất" : job.status === "failed" ? "Thất bại" : job.status === "running" ? "Đang chạy" : "Đang chờ"} />}
    >
      <progress className={styles.progress} max={100} value={Math.max(0, Math.min(100, job.progress_percent || 0))} />
      <p className={styles.progressText}>{Math.round(job.progress_percent || 0)}% · {job.progress_current}/{job.progress_total} sheet</p>
      <InlineNotice notice={job.error_message ? { type: "error", title: "Import thất bại", body: job.error_message } : null} />
      <InlineNotice notice={job.status === "completed" ? { type: "success", title: String(result.message || "Import hoàn tất."), body: `${Number(result.created_question_count || 0)} câu mới đang Chờ duyệt; đã loại ${Number(result.skipped_invalid_question_count || 0)} câu lỗi; bỏ qua ${Number(result.skipped_question_count || 0)} câu đã có do retry.` } : null} />
      <div className="button-row"><Link className="btn secondary" href="/bank/departments">Mở Ngân hàng đề</Link><Link className="btn secondary" href="/jobs">Xem tác vụ nền</Link></div>
    </WorkspaceSection> : null}
  </PageRoot>;
}
''')

css_module_path = Path('frontend/app/import-quiz-cms-old/page.module.css')
css_module_path.write_text(r'''.page {
  min-width: 0;
}

.steps {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 10px;
}

.step {
  min-width: 0;
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 12px 14px;
  border: 1px solid #dbe3ee;
  border-radius: 12px;
  background: #fff;
}

.step > div {
  min-width: 0;
  display: grid;
  gap: 2px;
}

.step b {
  color: #0f172a;
  font-size: 13px;
}

.step small {
  overflow: hidden;
  color: #64748b;
  font-size: 11px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.stepNumber {
  width: 30px;
  height: 30px;
  flex: 0 0 30px;
  display: grid;
  place-items: center;
  border-radius: 999px;
  color: #475569;
  background: #f1f5f9;
  font-size: 12px;
  font-weight: 850;
}

.stepCurrent {
  border-color: #93c5fd;
  background: #f8fbff;
}

.stepCurrent .stepNumber {
  color: #fff;
  background: #2563eb;
}

.stepDone {
  border-color: #bbf7d0;
  background: #f7fef9;
}

.stepDone .stepNumber {
  color: #fff;
  background: #16a34a;
}

.ruleGrid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 10px;
}

.ruleGrid > div {
  min-width: 0;
  display: grid;
  gap: 4px;
  padding: 12px 14px;
  border: 1px solid #e2e8f0;
  border-radius: 10px;
  background: #f8fafc;
}

.ruleGrid span {
  color: #2563eb;
  font-size: 10px;
  font-weight: 850;
  letter-spacing: .05em;
}

.ruleGrid b {
  color: #0f172a;
  font-size: 13px;
}

.ruleGrid small {
  color: #64748b;
  font-size: 11px;
  line-height: 1.45;
}

.uploadGrid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
}

.uploadCard {
  min-width: 0;
  display: grid;
  align-content: start;
  gap: 12px;
  padding: 14px;
  border: 1px solid #dbe3ee;
  border-radius: 12px;
  background: #f8fafc;
}

.uploadCard > small {
  color: #64748b;
  font-size: 11px;
}

.uploadHeading {
  display: flex;
  align-items: center;
  gap: 10px;
}

.uploadHeading > span {
  width: 32px;
  height: 32px;
  flex: 0 0 32px;
  display: grid;
  place-items: center;
  border-radius: 9px;
  color: #1d4ed8;
  background: #dbeafe;
  font-size: 11px;
  font-weight: 850;
}

.uploadHeading > div {
  min-width: 0;
}

.uploadHeading h3,
.uploadHeading p {
  margin: 0;
}

.uploadHeading h3 {
  color: #0f172a;
  font-size: 14px;
}

.uploadHeading p {
  margin-top: 2px;
  color: #64748b;
  font-size: 11px;
}

.filePicker {
  margin: 0;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-height: 42px;
  cursor: pointer;
}

.fileList {
  display: grid;
  gap: 6px;
  max-height: 180px;
  overflow: auto;
}

.fileRow {
  min-width: 0;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  padding: 8px 10px;
  border: 1px solid #e2e8f0;
  border-radius: 9px;
  background: #fff;
}

.fileCopy {
  min-width: 0;
  display: grid;
  gap: 2px;
}

.fileCopy b {
  overflow: hidden;
  color: #0f172a;
  font-size: 12px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.fileCopy small {
  color: #64748b;
  font-size: 10px;
}

.reviewGrid {
  min-width: 0;
  display: grid;
  grid-template-columns: minmax(0, 1.65fr) minmax(320px, .75fr);
  align-items: start;
  gap: 14px;
}

.reviewGrid > * {
  min-width: 0;
}

.tableScroll {
  max-width: 100%;
  overflow-x: auto;
  border: 1px solid #dbe3ee;
  border-radius: 10px;
}

.sheetTable {
  width: 100%;
  min-width: 980px;
  border-collapse: separate;
  border-spacing: 0;
  font-size: 11px;
}

.sheetTable th,
.sheetTable td {
  padding: 9px 10px;
  border-bottom: 1px solid #eef2f7;
  text-align: left;
  vertical-align: top;
}

.sheetTable th {
  color: #475569;
  background: #f8fafc;
  font-size: 10px;
  letter-spacing: .03em;
  text-transform: uppercase;
  white-space: nowrap;
}

.sheetTable tbody tr:last-child td {
  border-bottom: 0;
}

.sheetTable td:first-child {
  min-width: 190px;
}

.sheetTable td:first-child small {
  display: block;
  margin-top: 3px;
  color: #64748b;
}

.issueStack {
  display: grid;
  gap: 10px;
}

.issueActions {
  display: grid;
  gap: 8px;
}

.issueActions > * {
  width: 100%;
  margin: 0;
  justify-content: center;
  text-align: center;
}

.issueGroup {
  overflow: hidden;
  border: 1px solid #dbe3ee;
  border-radius: 10px;
  background: #fff;
}

.issueGroup summary {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  align-items: center;
  gap: 10px;
  padding: 10px 12px;
  cursor: pointer;
  list-style: none;
}

.issueGroup summary::-webkit-details-marker {
  display: none;
}

.issueGroup summary > span {
  min-width: 0;
  display: grid;
  gap: 2px;
}

.issueGroup summary small {
  color: #64748b;
  font-size: 9px;
}

.issueGroup summary strong {
  min-width: 28px;
  padding: 4px 7px;
  border-radius: 999px;
  color: #991b1b;
  background: #fee2e2;
  font-size: 11px;
  text-align: center;
}

.issueItems {
  display: grid;
  gap: 6px;
  max-height: 320px;
  overflow: auto;
  padding: 9px 10px 10px;
  border-top: 1px solid #eef2f7;
  background: #f8fafc;
}

.issueItem {
  display: grid;
  gap: 3px;
  padding: 8px;
  border-radius: 8px;
  background: #fff;
}

.issueItem p {
  margin: 0;
  color: #7f1d1d;
  font-size: 10px;
  line-height: 1.45;
}

.issueItem small {
  color: #64748b;
  font-size: 9px;
}

.progress {
  width: 100%;
  height: 12px;
}

.progressText {
  margin: 6px 0 0;
  color: #64748b;
  font-size: 12px;
}

@media (max-width: 1050px) {
  .reviewGrid {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 820px) {
  .steps,
  .ruleGrid,
  .uploadGrid {
    grid-template-columns: 1fr;
  }

  .step small {
    white-space: normal;
  }
}
''')


# ---------------------------------------------------------------------------
# 3) Remove page-specific legacy import CSS from globals.css. The new page uses
#    a CSS module, so globals remains a shared contract instead of a feature dump.
# ---------------------------------------------------------------------------
globals_path = Path('frontend/app/globals.css')
globals_css = globals_path.read_text()
legacy_start = globals_css.find('\n.legacy-quiz-import-page {')
legacy_end = globals_css.find('\n.dropdown-blank-toolbar {', legacy_start)
if legacy_start < 0 or legacy_end < 0:
    raise SystemExit('globals legacy import block markers not found')
globals_css = globals_css[:legacy_start] + '\n' + globals_css[legacy_end:]

globals_css = globals_css.replace(
    '.subject-quick-search-controls, .legacy-import-upload-grid { grid-template-columns: 1fr; }',
    '.subject-quick-search-controls { grid-template-columns: 1fr; }',
)
globals_css = globals_css.replace(
    '.subject-quick-search-heading, .legacy-import-source-heading, .legacy-import-preview-heading, .legacy-import-action-bar, .legacy-import-confirm, .dropdown-blank-toolbar { align-items: stretch; flex-direction: column; }',
    '.subject-quick-search-heading, .dropdown-blank-toolbar { align-items: stretch; flex-direction: column; }',
)
# Remaining import-only rules in the responsive blocks are single-line rules.
globals_css = re.sub(r'^\s*\.legacy-import[^\n]*\n', '', globals_css, flags=re.M)
if 'legacy-import' in globals_css or 'legacy-quiz-import' in globals_css:
    raise SystemExit('globals.css still contains legacy import page selectors')
globals_path.write_text(globals_css)


# Safety assertions: this patch must stay page/component scoped.
if 'UdemyClassProgressPanel' not in class_page_path.read_text():
    raise SystemExit('Udemy class progress panel was not wired into class page')
if 'Xem tiến độ Udemy' in class_page_path.read_text():
    raise SystemExit('old redirect-oriented Udemy CTA still present')
new_import_page = import_page_path.read_text()
for marker in ('EnterpriseScreenHeader', 'WorkspaceSection', 'OperationsKpiStrip', 'page.module.css'):
    if marker not in new_import_page:
        raise SystemExit(f'import page missing enterprise marker: {marker}')
for forbidden in ('BankWorkflowStepper', 'BankPageIdentity', 'legacy-import-', 'legacy-quiz-import-page'):
    if forbidden in new_import_page:
        raise SystemExit(f'import page still depends on old global UI contract: {forbidden}')
