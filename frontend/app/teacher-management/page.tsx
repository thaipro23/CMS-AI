"use client";

import Link from "next/link";
import { Suspense, useEffect, useMemo, useState } from "react";
import { useAppContext } from "../../context/AppContext";
import {
  createAcademicTrainingTeacherExportJob,
  downloadAcademicTrainingTeacherReport,
  downloadAcademicTrainingTeacherReportJob,
  getAcademicCampuses,
  getAcademicTerms,
  getAcademicTrainingTeacherReport,
  getAcademicTrainingTeacherReportJob,
} from "../../lib/api";
import {
  AcademicCampus,
  AcademicLearningComponentScore,
  AcademicTeacherReportJob,
  AcademicTerm,
  AcademicTrainingTeacherReport,
} from "../../types";
import { useDebouncedValue } from "../../lib/useDebouncedValue";
import { PageHeader } from '../../components/layout/PageHeader'
import { EnterpriseDataTable, EnterpriseTableColumn } from "../../components/table/EnterpriseDataTable";
import { useAcademicTableState } from "../../hooks/useAcademicTableState";
import {
  InlineNotice,
  InlineNoticeData,
  noticeError,
  noticeInfo,
  noticeSuccess,
  noticeWarning,
} from "../../components/ui/InlineNotice";

type TrainingSummary = {
  teacher_count: number;
  class_count: number;
  subject_count: number;
  student_count: number;
  unique_student_count: number;
  relearn_student_count: number;
  total_relearn_count: number;
  cms_synced_count: number;
  learning_enrolled_count: number;
  learning_active_count: number;
  risk_student_count: number;
  classes_without_course_count: number;
  deadline_late_student_count: number;
  deadline_late_quiz_count: number;
  exam_eligible_student_count: number;
  exam_not_eligible_student_count: number;
  exam_insufficient_data_student_count: number;
  quiz_failed_count: number;
  assignment_not_graded_count: number;
};

const EMPTY_SUMMARY: TrainingSummary = {
  teacher_count: 0,
  class_count: 0,
  subject_count: 0,
  student_count: 0,
  unique_student_count: 0,
  relearn_student_count: 0,
  total_relearn_count: 0,
  cms_synced_count: 0,
  learning_enrolled_count: 0,
  learning_active_count: 0,
  risk_student_count: 0,
  classes_without_course_count: 0,
  deadline_late_student_count: 0,
  deadline_late_quiz_count: 0,
  exam_eligible_student_count: 0,
  exam_not_eligible_student_count: 0,
  exam_insufficient_data_student_count: 0,
  quiz_failed_count: 0,
  assignment_not_graded_count: 0,
};

function normalizeSummary(
  value?: Partial<TrainingSummary> | null,
): TrainingSummary {
  return {
    ...EMPTY_SUMMARY,
    ...(value || {}),
    relearn_student_count: Number(value?.relearn_student_count || 0),
    total_relearn_count: Number(value?.total_relearn_count || 0),
    deadline_late_student_count: Number(
      value?.deadline_late_student_count || 0,
    ),
    deadline_late_quiz_count: Number(value?.deadline_late_quiz_count || 0),
    exam_eligible_student_count: Number(
      (value as any)?.exam_eligible_student_count || 0,
    ),
    exam_not_eligible_student_count: Number(
      (value as any)?.exam_not_eligible_student_count || 0,
    ),
    exam_insufficient_data_student_count: Number(
      (value as any)?.exam_insufficient_data_student_count || 0,
    ),
    quiz_failed_count: Number((value as any)?.quiz_failed_count || 0),
    assignment_not_graded_count: Number(
      (value as any)?.assignment_not_graded_count || 0,
    ),
  };
}

function normalizePercentValue(value?: number | null) {
  if (typeof value !== "number" || Number.isNaN(value)) return null;
  if (value >= 0 && value <= 1) return value * 100;
  return value;
}

function percentLabel(value?: number | null) {
  const percent = normalizePercentValue(value);
  if (percent === null) return "N/A";
  return `${Math.round(percent * 10) / 10}%`;
}

function grade10Label(value?: number | null) {
  const percent = normalizePercentValue(value);
  if (percent === null) return "N/A";
  const score = Math.max(0, Math.min(10, percent / 10));
  return `${Math.round(score * 10) / 10}/10`;
}

function score10Label(value?: number | null) {
  if (typeof value !== "number" || Number.isNaN(value)) return "N/A";
  let score = value;
  if (score >= 0 && score <= 1) score *= 10;
  if (score > 10) score /= 10;
  score = Math.max(0, Math.min(10, score));
  return `${Math.round(score * 10) / 10}/10`;
}

function componentKey(score: AcademicLearningComponentScore) {
  return String(score.key || score.name || "").trim();
}

function componentDisplayName(score: AcademicLearningComponentScore) {
  return String(score.name || score.key || "Đầu điểm").trim();
}

function gradeColumnCompare(
  left: { key: string; name: string },
  right: { key: string; name: string },
) {
  return left.name.localeCompare(right.name, "vi", {
    numeric: true,
    sensitivity: "base",
  });
}

function componentScoreText(score?: AcademicLearningComponentScore | null) {
  if (!score) return "N/A";
  const percent = normalizePercentValue(score.percent);
  if (percent !== null) return grade10Label(percent);
  if (
    typeof score.earned === "number" &&
    typeof score.possible === "number" &&
    score.possible > 0
  ) {
    const value = Math.max(
      0,
      Math.min(10, (score.earned / score.possible) * 10),
    );
    return `${Math.round(value * 10) / 10}/10`;
  }
  return "N/A";
}

function countLabel(value?: number | null) {
  return String(value || 0);
}

function ratioLabel(done?: number | null, total?: number | null) {
  const cleanDone = done || 0;
  const cleanTotal = total || 0;
  return `${cleanDone}/${cleanTotal}`;
}

function syncTone(done?: number | null, total?: number | null) {
  const cleanDone = Number(done || 0);
  const cleanTotal = Number(total || 0);
  if (cleanTotal <= 0) return "status-pill neutral";
  if (cleanDone >= cleanTotal) return "status-pill success";
  if (cleanDone > 0) return "status-pill warning";
  return "status-pill danger";
}

function alertText(alerts?: string[]) {
  return alerts?.length
    ? alerts.slice(0, 3).join(", ")
    : "Không có cảnh báo lớn";
}

function counterText(total: number, page: number, pageSize: number) {
  if (!total) return "0 giáo viên";
  const start = (page - 1) * pageSize + 1;
  const end = Math.min(total, page * pageSize);
  return `${start}-${end} / ${total}`;
}

function riskTone(item: AcademicTrainingTeacherReport) {
  if (item.classes_without_course_count || item.status_counts?.sync_error)
    return "status-pill danger";
  if (item.risk_student_count) return "status-pill warning";
  return "status-pill success";
}

function jobPercent(job?: AcademicTeacherReportJob | null) {
  if (!job) return 0;
  const total = Math.max(1, Number(job.progress_total || 100));
  return Math.max(
    0,
    Math.min(
      100,
      Math.round((Number(job.progress_current || 0) / total) * 100),
    ),
  );
}

function downloadBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 1000);
}

function TeacherManagementContent() {
  const { authHeaders } = useAppContext();
  const headers = useMemo(() => authHeaders(), [authHeaders]);
  const [terms, setTerms] = useState<AcademicTerm[]>([]);
  const [campuses, setCampuses] = useState<AcademicCampus[]>([]);
  const [items, setItems] = useState<AcademicTrainingTeacherReport[]>([]);
  const [summary, setSummary] = useState<TrainingSummary>(EMPTY_SUMMARY);
  const { state, update } = useAcademicTableState({ branch: "poly", status: "all", pageSize: 50 });
  const { termId, branch, campus, q: search, status: learningStatus, page, pageSize, density } = state;
  const debouncedSearch = useDebouncedValue(search, 350);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [exportJob, setExportJob] = useState<AcademicTeacherReportJob | null>(
    null,
  );
  const [message, setMessage] = useState<InlineNoticeData | null>(null);

  useEffect(() => {
    let cancelled = false;
    getAcademicTerms(headers, { branch, active: true })
      .then((data) => {
        if (cancelled) return;
        setTerms(data);
        if (!termId || !data.some((item) => item.id === termId)) {
          const preferred = data.find((item) => item.term_name === "Summer 2026") || data[0];
          update({ termId: preferred?.id || "" });
        }
      })
      .catch((error) =>
        setMessage(noticeError(error, "Không tải được học kỳ.")),
      );
    return () => {
      cancelled = true;
    };
  }, [headers, branch, termId]);

  useEffect(() => {
    let cancelled = false;
    getAcademicCampuses(headers, { branch, active: true })
      .then((data) => {
        if (cancelled) return;
        setCampuses(data);
        if (campus && !data.some((item) => item.campus_code === campus)) update({ campus: "" });
      })
      .catch(() => setCampuses([]));
    return () => {
      cancelled = true;
    };
  }, [headers, branch, campus]);

  const resetReportState = () => {
    setItems([]);
    setSummary(EMPTY_SUMMARY);
    setTotal(0);
  };

  const loadReport = async (cancelledRef?: { cancelled: boolean }) => {
    if (!termId) {
      resetReportState();
      setLoading(false);
      return;
    }
    setLoading(true);
    setMessage(null);
    try {
      const result = await getAcademicTrainingTeacherReport(headers, {
        termId,
        branch,
        campus,
        search: debouncedSearch,
        learningStatus,
        page,
        pageSize,
        includeClasses: false,
      });
      if (cancelledRef?.cancelled) return;
      setItems(result.items || []);
      setSummary(normalizeSummary(result.summary));
      setTotal(result.total || 0);
    } catch (error) {
      if (!cancelledRef?.cancelled)
        setMessage({
          ...noticeError(error, "Không tải được danh sách giảng viên."),
          onRetry: () => loadReport(),
        });
    } finally {
      if (!cancelledRef?.cancelled) setLoading(false);
    }
  };

  useEffect(() => {
    const cancelledRef = { cancelled: false };
    loadReport(cancelledRef);
    return () => {
      cancelledRef.cancelled = true;
    };
  }, [headers, termId, branch, campus, debouncedSearch, learningStatus, page, pageSize]);

  useEffect(() => {
    if (!exportJob || !["queued", "running"].includes(exportJob.status)) return;
    const timer = window.setInterval(async () => {
      try {
        const latest = await getAcademicTrainingTeacherReportJob(
          headers,
          exportJob.id,
        );
        setExportJob(latest);
        if (latest.status === "completed") {
          setMessage(noticeSuccess("File Excel đã sẵn sàng."));
        }
      } catch (error) {
        setMessage(
          noticeError(error, "Không kiểm tra được trạng thái xuất Excel."),
        );
      }
    }, 2500);
    return () => window.clearInterval(timer);
  }, [headers, exportJob?.id, exportJob?.status]);

  const selectedTerm = terms.find((item) => item.id === termId);
  const totalPages = Math.max(1, Math.ceil(total / pageSize));

  useEffect(() => {
    if (page > totalPages) update({ page: totalPages }, { resetPage: false });
  }, [page, totalPages, update]);

  const classComponentColumns = (item: AcademicTrainingTeacherReport) => {
    const columns: Array<{ key: string; name: string }> = [];
    const seen = new Set<string>();
    (item.classes || []).forEach((cls) => {
      (cls.learning_component_summaries || []).forEach((score) => {
        const key = componentKey(score);
        const name = componentDisplayName(score);
        const dedupeKey = (key || name).toLowerCase();
        if (!dedupeKey || seen.has(dedupeKey)) return;
        seen.add(dedupeKey);
        columns.push({ key: key || name, name });
      });
    });
    return columns.sort(gradeColumnCompare);
  };

  const classComponentScore = (
    cls: any,
    column: { key: string; name: string },
  ) => {
    return (
      cls.learning_component_summaries?.find(
        (score: AcademicLearningComponentScore) =>
          componentKey(score) === column.key || score.name === column.name,
      ) || null
    );
  };

  const exportExcel = async () => {
    setExporting(true);
    setMessage(null);
    try {
      const blob = await downloadAcademicTrainingTeacherReport(headers, {
        termId,
        branch,
        campus,
        search: debouncedSearch,
        learningStatus,
      });
      const termPart = (selectedTerm?.term_name || "term").replace(
        /[^a-zA-Z0-9]+/g,
        "-",
      );
      downloadBlob(
        blob,
        `bao-cao-quan-ly-giang-vien-${branch}-${termPart}.xlsx`,
      );
      setMessage(noticeSuccess("Đã xuất Excel."));
    } catch (error) {
      setMessage(noticeError(error, "Không xuất được file Excel."));
    } finally {
      setExporting(false);
    }
  };

  const exportExcelBackground = async () => {
    if (!termId) {
      setMessage(noticeWarning("Chọn học kỳ trước khi xuất Excel."));
      return;
    }
    setMessage(null);
    try {
      const job = await createAcademicTrainingTeacherExportJob(headers, {
        termId,
        branch,
        campus,
        search: debouncedSearch,
        learningStatus,
      });
      setExportJob(job);
      setMessage(noticeInfo("Đã đưa yêu cầu xuất Excel vào hàng đợi."));
    } catch (error) {
      setMessage(noticeError(error, "Không tạo được tác vụ xuất Excel."));
    }
  };

  const downloadBackgroundExcel = async () => {
    if (!exportJob?.id) return;
    try {
      const blob = await downloadAcademicTrainingTeacherReportJob(
        headers,
        exportJob.id,
      );
      downloadBlob(
        blob,
        exportJob.file_name || `teacher-management-report-${exportJob.id}.xlsx`,
      );
    } catch (error) {
      setMessage(noticeError(error, "Không tải được file Excel."));
    }
  };

  const columns = useMemo<EnterpriseTableColumn<AcademicTrainingTeacherReport>[]>(() => [
    { key: "stt", header: "STT", width: 72, sticky: "left", stickyOffset: 0, hideable: false, render: (_item, index) => (page - 1) * pageSize + index + 1 },
    { key: "teacher", header: "Giảng viên", minWidth: 250, sticky: "left", stickyOffset: 72, render: (item) => <div className="teacher-identity"><span className="teacher-avatar">{(item.teacher_name || item.teacher_username || "GV").slice(0, 2).toUpperCase()}</span><div><b>{item.teacher_name || item.teacher_username}</b><small>{item.teacher_username}{item.teacher_email ? ` · ${item.teacher_email}` : ""}</small><small>{item.branch?.toUpperCase() || "N/A"}{item.campus ? ` · ${item.campus.toUpperCase()}` : ""}</small></div></div> },
    { key: "scale", header: "Quy mô đào tạo", minWidth: 220, render: (item) => <><b>{item.class_count} lớp · {item.subject_count} môn</b><small>{item.subject_codes?.slice(0, 6).join(", ") || "N/A"}</small><small>{item.student_count} lượt SV · {item.unique_student_count} SV riêng biệt</small><small>Học lại: {countLabel(item.relearn_student_count)} SV · {countLabel(item.total_relearn_count)} lượt</small></> },
    { key: "cms", header: "Đồng bộ CMS", minWidth: 220, render: (item) => <><span className={syncTone(item.cms_synced_count, item.student_count)}>User CMS match {ratioLabel(item.cms_synced_count, item.student_count)}</span><small>Ghi danh CMS {ratioLabel(item.learning_enrolled_count, item.student_count)}</small>{item.classes_without_course_count ? <small className="danger-text">{item.classes_without_course_count} lớp chưa ghép Course CMS</small> : <small>Course CMS đã map cho các lớp có dữ liệu</small>}</> },
    { key: "progress", header: "Tiến độ học", minWidth: 210, render: (item) => <><b>Completion {percentLabel(item.learning_avg_progress_percent)}</b><small>Điểm tổng {score10Label(item.learning_avg_grade_10)}</small><small>Có hoạt động {ratioLabel(item.learning_active_count, item.student_count)}</small><small>Trễ deadline {countLabel(item.deadline_late_student_count)} SV · {countLabel(item.deadline_late_quiz_count)} lượt quiz</small></> },
    { key: "risk", header: "Tình hình sinh viên", minWidth: 260, render: (item) => { const statuses = item.status_counts || {}; return <><span className={riskTone(item)}>{item.risk_student_count ? `${item.risk_student_count} SV cần theo dõi` : "Ổn"}</span><small>Chưa học {countLabel(statuses.no_activity)} · Tiến độ thấp {countLabel(statuses.low_progress)} · Điểm thấp {countLabel(statuses.low_grade)}</small><small>Trễ deadline {countLabel(statuses.deadline_late)} SV · Không được thi {countLabel(statuses.exam_not_eligible)} SV</small><small>{alertText(item.learning_alerts)}</small></> } },
    { key: "actions", header: "Thao tác", minWidth: 110, sticky: "right", hideable: false, render: (item) => { const params = new URLSearchParams(); if (termId) params.set("term_id", termId); if (branch) params.set("branch", branch); if (campus) params.set("campus", campus); params.set("list_campus", campus || "all"); if (selectedTerm?.term_name) params.set("term_name", selectedTerm.term_name); params.set("teacher_name", item.teacher_name || item.teacher_username); return <Link className="btn secondary small teacher-row-action" href={`/teacher-management/teachers/${encodeURIComponent(item.teacher_id)}/classes?${params.toString()}`}>Xem lớp</Link> } },
  ], [branch, campus, page, pageSize, selectedTerm?.term_name, termId]);

  return (
    <div className="page-stack student-management-page academic-flow-page training-management-page teacher-management-page ux-enterprise-page">
      <PageHeader
        eyebrow="Vận hành đào tạo"
        title="Quản lý giảng viên"
        description={`${selectedTerm?.term_name || "Chưa chọn kỳ"} · ${branch.toUpperCase()} · ${campus ? campus.toUpperCase() : "Tất cả cơ sở"} · ${counterText(total, page, pageSize)} giảng viên`}
        secondaryActions={<><button className="btn secondary" type="button" onClick={exportExcelBackground} disabled={!termId || exportJob?.status === "queued" || exportJob?.status === "running"}>{exportJob && ["queued", "running"].includes(exportJob.status) ? `Đang xuất ${jobPercent(exportJob)}%` : "Xuất Excel nền"}</button>{exportJob?.status === "completed" && <button className="btn secondary" type="button" onClick={downloadBackgroundExcel}>Tải Excel</button>}</>}
        primaryAction={<button className="btn" type="button" onClick={exportExcel} disabled={exporting || loading}>{exporting ? "Đang xuất..." : "Xuất trực tiếp"}</button>}
      />
      <section className="card academic-unified-card ux-surface-card teacher-workspace-card">
        <div className="academic-filter-bar ux-filter-grid teacher-filter-bar">
          <label>
            Hệ
            <select
              className="input"
              value={branch}
              onChange={(event) => {
                update({ branch: event.target.value, campus: "" });
              }}
            >
              <option value="poly">Poly</option>
              <option value="ptcd">PTCĐ</option>
            </select>
          </label>
          <label>
            Học kỳ
            <select
              className="input"
              value={termId}
              onChange={(event) => {
                update({ termId: event.target.value });
              }}
            >
              {!terms.length && (
                <option value="">Chưa có kỳ, tạo tại /semesters</option>
              )}
              {terms.map((item) => (
                <option key={item.id} value={item.id}>
                  {item.term_name}
                </option>
              ))}
            </select>
          </label>
          <label>
            Cơ sở
            <select
              className="input"
              value={campus}
              onChange={(event) => {
                update({ campus: event.target.value });
              }}
            >
              <option value="">Tất cả cơ sở</option>
              {campuses.map((item) => (
                <option key={item.id} value={item.campus_code}>
                  {item.campus_code.toUpperCase()} · {item.campus_name}
                </option>
              ))}
            </select>
          </label>
          <label>
            Trạng thái
            <select
              className="input"
              value={learningStatus}
              onChange={(event) => {
                update({ status: event.target.value });
              }}
            >
              <option value="all">Tất cả giáo viên</option>
              <option value="no_course_map">Có lớp chưa ghép Course CMS</option>
              <option value="cms_not_synced">Có SV chưa đồng bộ CMS</option>
              <option value="not_fully_enrolled">Có SV chưa ghi danh</option>
              <option value="no_activity">Có SV chưa học</option>
              <option value="low_progress">Có SV tiến độ thấp</option>
              <option value="low_grade">Có SV điểm thấp</option>
              <option value="deadline_late">Có SV trễ deadline quiz</option>
              <option value="exam_not_eligible">Có SV không được thi</option>
              <option value="exam_insufficient_data">
                Có SV thiếu dữ liệu xét thi
              </option>
              <option value="has_alert">Có cảnh báo</option>
            </select>
          </label>
          <label className="academic-filter-search">
            Tìm giảng viên/lớp/môn
            <input
              className="input"
              value={search}
              onChange={(event) => {
                update({ q: event.target.value });
              }}
              placeholder="Tên GV, username, COM1071, lớp..."
            />
          </label>
        </div>

        <div className="academic-summary-strip training-summary-strip ux-kpi-grid">
          <div>
            <span>Tổng giảng viên</span>
            <b>{countLabel(summary.teacher_count)}</b>
            <small>Theo bộ lọc hiện tại</small>
          </div>
          <div>
            <span>Tổng số lớp</span>
            <b>{countLabel(summary.class_count)}</b>
            <small>Theo hệ · học kỳ · cơ sở đang chọn</small>
          </div>
          <div>
            <span>Tổng số sinh viên</span>
            <b>{countLabel(summary.student_count)}</b>
            <small>Theo bộ lọc hiện tại</small>
          </div>
          <div>
            <span>User CMS match</span>
            <b>{countLabel(summary.cms_synced_count)}</b>
            <small>Theo bộ lọc hiện tại</small>
          </div>
          <div>
            <span>Ghi danh CMS</span>
            <b>{countLabel(summary.learning_enrolled_count)}</b>
            <small>Theo bộ lọc hiện tại</small>
          </div>
          <div>
            <span>Cần theo dõi</span>
            <b>{countLabel(summary.risk_student_count)}</b>
            <small>Nhãn mềm, cần GV xác minh</small>
          </div>
          <div>
            <span>Trễ deadline</span>
            <b>{countLabel(summary.deadline_late_student_count)}</b>
            <small>
              {countLabel(summary.deadline_late_quiz_count)} lượt quiz trễ
            </small>
          </div>
          <div>
            <span>Không được thi</span>
            <b>{countLabel(summary.exam_not_eligible_student_count)}</b>
            <small>
              {countLabel(summary.exam_insufficient_data_student_count)} SV chưa
              đủ dữ liệu xét thi
            </small>
          </div>
        </div>

        {exportJob &&
          ["queued", "running", "failed"].includes(exportJob.status) && (
            <InlineNotice
              notice={{
                type: exportJob.status === "failed" ? "error" : "info",
                title: "Tác vụ Excel",
                body: `${exportJob.progress_label} · ${jobPercent(exportJob)}%${exportJob.status === "failed" ? ` · ${exportJob.error_message || "Thất bại"}` : ""}`,
              }}
            />
          )}

        {!campus && (
          <InlineNotice
            notice={{
              type: "warning",
              title: "Dữ liệu lớn",
              body: "Đang xem tất cả cơ sở. Nên lọc cơ sở để tải nhanh hơn.",
            }}
          />
        )}

        <InlineNotice notice={message} />

        <EnterpriseDataTable
          tableId="teacher-management"
          caption="Danh sách giảng viên"
          rows={items}
          columns={columns}
          rowKey={(item) => item.teacher_id}
          density={density}
          onDensityChange={(value) => update({ density: value }, { resetPage: false })}
          loading={loading}
          error={message?.type === "error" ? message.body : undefined}
          onRetry={() => loadReport()}
          emptyTitle="Chưa có dữ liệu theo bộ lọc hiện tại"
          emptyDescription="Đổi cơ sở, học kỳ, trạng thái hoặc xóa từ khóa tìm kiếm."
          emptyAction={<button className="btn secondary small" type="button" onClick={() => update({ q: "", status: "all", page: 1 }, { resetPage: false })}>Xóa bộ lọc nhanh</button>}
          page={page}
          pageSize={pageSize}
          total={total}
          totalPages={totalPages}
          onPageChange={(value) => update({ page: value }, { resetPage: false })}
          onPageSizeChange={(value) => update({ pageSize: value, page: 1 }, { resetPage: false })}
          label="giảng viên"
          getRowClassName={() => "teacher-row-compact"}
        />

      </section>
    </div>
  );
}

export default function TeacherManagementPage() {
  return (
    <Suspense
      fallback={<div className="card">Đang tải quản lý giảng viên...</div>}
    >
      <TeacherManagementContent />
    </Suspense>
  );
}
