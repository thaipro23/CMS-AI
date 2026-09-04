"use client";

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
