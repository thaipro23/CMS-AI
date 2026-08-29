"use client";

import Link from "next/link";
import { Suspense, useEffect, useMemo, useState } from "react";
import { useAppContext } from "../../context/AppContext";
import {
  createAcademicTrainingTeacherCacheJob,
  createAcademicTrainingTeacherExportJob,
  downloadAcademicTrainingTeacherReportJob,
  getAcademicCampuses,
  getAcademicTerms,
  getAcademicTrainingTeacherReport,
  getAcademicTrainingTeacherReportJobs,
  waitForAcademicTrainingTeacherReportJob,
} from "../../lib/api";
import {
  AcademicCampus,
  AcademicLearningComponentScore,
  AcademicTeacherReportJob,
  AcademicTerm,
  AcademicTrainingTeacherReport,
} from "../../types";
import { useDebouncedValue } from "../../lib/useDebouncedValue";
import { PageRoot } from '../../components/layout/PageHeader'
import { EnterpriseScreenHeader } from '../../components/layout/EnterpriseDesignContract'
import { TrainingKpiStrip } from '../../components/training/TrainingWorkspace'
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

type TrainingPlatform = "cms" | "udemy";

type TrainingSummary = {
  teacher_count: number;
  class_count: number;
  subject_count: number;
  student_count: number;
  unique_student_count: number;
  relearn_student_count: number;
  total_relearn_count: number;
  cms_class_count: number;
  udemy_class_count: number;
  cms_student_count: number;
  udemy_student_count: number;
  cms_synced_count: number;
  udemy_progress_student_count: number;
  udemy_progress_late_count: number;
  udemy_progress_average_percent: number | null;
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
  cms_class_count: 0,
  udemy_class_count: 0,
  cms_student_count: 0,
  udemy_student_count: 0,
  cms_synced_count: 0,
  udemy_progress_student_count: 0,
  udemy_progress_late_count: 0,
  udemy_progress_average_percent: null,
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
    cms_class_count: Number(value?.cms_class_count || 0),
    udemy_class_count: Number(value?.udemy_class_count || 0),
    cms_student_count: Number(value?.cms_student_count || 0),
    udemy_student_count: Number(value?.udemy_student_count || 0),
    udemy_progress_student_count: Number(value?.udemy_progress_student_count || 0),
    udemy_progress_late_count: Number(value?.udemy_progress_late_count || 0),
    udemy_progress_average_percent:
      typeof value?.udemy_progress_average_percent === "number"
        ? value.udemy_progress_average_percent
        : null,
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
  if (item.risk_student_count || Number(item.udemy_progress_late_count || 0) > 0)
    return "status-pill warning";
  return "status-pill success";
}

function platformStudentTotal(item: AcademicTrainingTeacherReport, platform: "cms" | "udemy") {
  if (platform === "cms") return Number(item.cms_student_count ?? item.student_count ?? 0);
  return Number(item.udemy_student_count || 0);
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

export function TeacherManagementPlatformPage({ platform }: { platform: TrainingPlatform }) {
  const { authHeaders } = useAppContext();
  const isCms = platform === "cms";
  const platformLabel = isCms ? "CMS" : "Udemy";
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
  const [cacheJob, setCacheJob] = useState<AcademicTeacherReportJob | null>(
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

  const loadReport = async (cancelledRef?: { cancelled: boolean }, fresh = false) => {
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
        learningPlatform: platform,
        page,
        pageSize,
        includeClasses: false,
        fresh,
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
  }, [headers, termId, branch, campus, debouncedSearch, learningStatus, page, pageSize, platform]);

  useEffect(() => {
    if (!termId || exportJob) return
    const controller = new AbortController()
    getAcademicTrainingTeacherReportJobs(headers, { status: "active", limit: 20 })
      .then((jobs) => {
        if (controller.signal.aborted) return
        const match = jobs.find((job) => {
          const request = (job.request_json || {}) as Record<string, unknown>
          return job.job_type === "export_excel"
            && job.term_id === termId
            && String(job.branch || "") === String(branch || "")
            && String(job.campus || "") === String(campus || "")
            && String(request.search || "") === String(debouncedSearch || "")
            && String(request.learning_status || "") === String(learningStatus === "all" ? "" : learningStatus || "")
            && String(request.learning_platform || "cms") === platform
        })
        if (match) setExportJob(match)
      })
      .catch(() => undefined)
    return () => controller.abort()
  }, [branch, campus, debouncedSearch, exportJob, headers, learningStatus, termId, platform])

  useEffect(() => {
    if (!termId || cacheJob) return;
    const controller = new AbortController();
    getAcademicTrainingTeacherReportJobs(headers, { status: "active", limit: 20 })
      .then((jobs) => {
        if (controller.signal.aborted) return;
        const match = jobs.find((job) => {
          const request = (job.request_json || {}) as Record<string, unknown>;
          return job.job_type === "rebuild_cache"
            && job.term_id === termId
            && String(job.branch || "") === String(branch || "")
            && String(job.campus || "") === String(campus || "")
            && String(request.learning_platform || "cms") === platform;
        });
        if (match) setCacheJob(match);
      })
      .catch(() => undefined);
    return () => controller.abort();
  }, [branch, cacheJob, campus, headers, platform, termId]);

  useEffect(() => {
    if (!exportJob || !["queued", "running"].includes(exportJob.status)) return;
    const controller = new AbortController();
    waitForAcademicTrainingTeacherReportJob(headers, exportJob.id, { signal: controller.signal })
      .then((latest) => {
        setExportJob(latest);
        setMessage(noticeSuccess(platform === "cms" ? "File Excel đã sẵn sàng từ điểm CMS mới nhất." : "File Excel đã sẵn sàng."));
      })
      .catch((error) => {
        if (controller.signal.aborted) return;
        setMessage(noticeError(error, "Không kiểm tra được trạng thái xuất Excel."));
      });
    return () => controller.abort();
  }, [headers, exportJob?.id, exportJob?.status, platform]);


  useEffect(() => {
    if (!cacheJob || !["queued", "running"].includes(cacheJob.status)) return;
    const controller = new AbortController();
    waitForAcademicTrainingTeacherReportJob(headers, cacheJob.id, { signal: controller.signal })
      .then(async (latest) => {
        setCacheJob(latest);
        setMessage(noticeSuccess(platform === "cms" ? "Đã lấy điểm CMS mới nhất và tính lại báo cáo giảng viên." : "Đã tính lại báo cáo giảng viên từ dữ liệu Udemy mới nhất đã import."));
        await loadReport(undefined, true);
      })
      .catch((error) => {
        if (controller.signal.aborted) return;
        setMessage(noticeError(error, "Không tính lại được báo cáo giảng viên."));
      });
    return () => controller.abort();
  }, [headers, cacheJob?.id, cacheJob?.status, platform]);

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

  const rebuildTeacherCache = async () => {
    if (!termId) {
      setMessage(noticeWarning("Chọn học kỳ trước khi làm mới số liệu."));
      return;
    }
    setMessage(null);
    try {
      const job = await createAcademicTrainingTeacherCacheJob(headers, {
        termId,
        branch,
        campus,
        learningPlatform: platform,
      });
      setCacheJob(job);
      setMessage(noticeInfo(platform === "cms" ? "Đã đưa yêu cầu lấy điểm CMS mới nhất và tính lại báo cáo vào hàng đợi." : "Đã đưa yêu cầu tính lại báo cáo Udemy vào hàng đợi."));
    } catch (error) {
      setMessage(noticeError(error, "Không tạo được tác vụ làm mới số liệu."));
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
        learningPlatform: platform,
      });
      setExportJob(job);
      setMessage(noticeInfo(platform === "cms" ? "Đã đưa yêu cầu lấy điểm CMS mới nhất rồi xuất Excel vào hàng đợi." : `Đã đưa yêu cầu xuất Excel giảng viên ${platformLabel} vào hàng đợi.`));
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
        exportJob.file_name || `teacher-management-${platform}-${exportJob.id}.xlsx`,
      );
    } catch (error) {
      setMessage(noticeError(error, "Không tải được file Excel."));
    }
  };

  const columns = useMemo<EnterpriseTableColumn<AcademicTrainingTeacherReport>[]>(() => {
    const shared: EnterpriseTableColumn<AcademicTrainingTeacherReport>[] = [
      { key: "stt", header: "STT", kind: "index", width: 52, sticky: "left", hideable: false, render: (_item, index) => (page - 1) * pageSize + index + 1 },
      { key: "teacher", header: "Giảng viên", kind: "identity", minWidth: 225, sticky: "left", priority: "required", hideable: false, render: (item) => <div className="teacher-identity teacher-identity-text-only"><b>{item.teacher_name || item.teacher_username}</b><small>{item.teacher_username}{item.teacher_email ? ` · ${item.teacher_email}` : ""}</small><small>{item.branch?.toUpperCase() || "N/A"}{item.campus ? ` · ${item.campus.toUpperCase()}` : ""}</small></div> },
      { key: "scale", header: "Quy mô", kind: "number", minWidth: 175, priority: "important", hideable: true, render: (item) => <><b>{item.class_count} lớp · {item.subject_count} môn</b><small>{platformLabel} · {platformStudentTotal(item, platform)} lượt sinh viên</small><small>{item.unique_student_count} sinh viên duy nhất</small></> },
    ];

    const platformColumns: EnterpriseTableColumn<AcademicTrainingTeacherReport>[] = isCms
      ? [
          { key: "cms", header: "CMS / Open edX", kind: "status", minWidth: 190, priority: "important", hideable: true, render: (item) => { const cmsTotal = platformStudentTotal(item, "cms"); return <><span className={syncTone(item.cms_synced_count, cmsTotal)}>CMS {ratioLabel(item.cms_synced_count, cmsTotal)}</span><small>Đã ghi danh {ratioLabel(item.learning_enrolled_count, cmsTotal)}</small><small>Tiến độ trung bình {percentLabel(item.learning_avg_progress_percent)}</small>{item.classes_without_course_count ? <small className="danger-text">{item.classes_without_course_count} lớp chưa ghép Course</small> : null}</> } },
          { key: "risk", header: "Cảnh báo CMS", kind: "status", minWidth: 195, priority: "important", hideable: true, render: (item) => { const statuses = item.status_counts || {}; const riskTotal = Number(item.risk_student_count || 0); return <><span className={riskTone(item)}>{riskTotal ? `${riskTotal} SV cần xem` : "Ổn"}</span><small>Chậm mốc tiến độ {countLabel(statuses.deadline_late)} · Tiến độ thấp {countLabel(statuses.low_progress)}</small><small>Không đủ thi {countLabel(statuses.exam_not_eligible)}</small></> } },
        ]
      : [
          { key: "udemy", header: "Tiến độ Udemy", kind: "progress", minWidth: 195, priority: "important", hideable: true, render: (item) => { const udemyTotal = platformStudentTotal(item, "udemy"); const imported = Number(item.udemy_progress_student_count || 0); const late = Number(item.udemy_progress_late_count || 0); return <><span className={syncTone(imported, udemyTotal)}>Đã import {ratioLabel(imported, udemyTotal)}</span><small>Tiến độ trung bình {percentLabel(item.udemy_progress_average_percent)}</small><small className={late > 0 ? "danger-text" : undefined}>{late > 0 ? `${late} SV chậm tiến độ` : "Không có SV chậm"}</small></> } },
          { key: "risk", header: "Cảnh báo Udemy", kind: "status", minWidth: 185, priority: "important", hideable: true, render: (item) => { const late = Number(item.udemy_progress_late_count || 0); const unmatched = Number((item as any).udemy_progress_unmatched_count || 0); return <><span className={late || unmatched ? "status-pill warning" : "status-pill success"}>{late || unmatched ? `${late + unmatched} trường hợp` : "Ổn"}</span><small>Chậm tiến độ {late}</small><small>Chưa khớp roster {unmatched}</small></> } },
        ];

    return [
      ...shared,
      ...platformColumns,
      { key: "actions", header: "Thao tác", kind: "actions", width: 106, sticky: "right", hideable: false, render: (item) => { const params = new URLSearchParams(); if (termId) params.set("term_id", termId); if (branch) params.set("branch", branch); if (campus) params.set("campus", campus); params.set("list_campus", campus || "all"); params.set("platform", platform); if (selectedTerm?.term_name) params.set("term_name", selectedTerm.term_name); params.set("teacher_name", item.teacher_name || item.teacher_username); return <Link className="btn secondary small teacher-row-action" href={`/teacher-management/teachers/${encodeURIComponent(item.teacher_id)}/classes?${params.toString()}`}>Xem lớp</Link> } },
    ];
  }, [branch, campus, isCms, page, pageSize, platform, platformLabel, selectedTerm?.term_name, termId]);

  return (
    <PageRoot className="page-stack enterprise-standard-page student-management-page academic-flow-page training-management-page teacher-management-page ux-enterprise-page">
      <EnterpriseScreenHeader
        eyebrow="Vận hành đào tạo"
        title={`Quản lý giảng viên ${platformLabel}`}
        description={isCms ? "Theo dõi giảng viên, lớp CMS/Open edX, đồng bộ, ghi danh, tiến độ và các trường hợp cần hỗ trợ." : "Theo dõi giảng viên phụ trách lớp Udemy, tỷ lệ sinh viên đã import, tiến độ và cảnh báo theo kế hoạch."}
        icon="teachers"
        tone="blue"
        breadcrumbs={[{ label: 'Vận hành đào tạo' }, { label: `Quản lý giảng viên ${platformLabel}` }]}
        primaryAction={<button className="btn" type="button" onClick={exportExcelBackground} disabled={!termId || exportJob?.status === "queued" || exportJob?.status === "running"}>{exportJob && ["queued", "running"].includes(exportJob.status) ? `Đang xuất ${jobPercent(exportJob)}%` : "Xuất Excel"}</button>}
        secondaryActions={<>
          <button className="btn secondary" type="button" onClick={rebuildTeacherCache} disabled={!termId || cacheJob?.status === "queued" || cacheJob?.status === "running"}>
            {cacheJob && ["queued", "running"].includes(cacheJob.status) ? `Đang làm mới ${jobPercent(cacheJob)}%` : "Làm mới số liệu"}
          </button>
          {exportJob?.status === "completed" ? <button className="btn secondary" type="button" onClick={downloadBackgroundExcel}>Tải Excel</button> : null}
        </>}
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
              {isCms ? <>
                <option value="no_course_map">Có lớp chưa ghép Course CMS</option>
                <option value="cms_not_synced">Có SV chưa đồng bộ CMS</option>
                <option value="not_fully_enrolled">Có SV chưa ghi danh</option>
                <option value="no_activity">Có SV chưa học</option>
                <option value="low_progress">Có SV tiến độ thấp</option>
                <option value="low_grade">Có SV điểm thấp</option>
                <option value="deadline_late">Có SV chậm mốc tiến độ Quiz</option>
                <option value="exam_not_eligible">Có SV không được thi</option>
                <option value="exam_insufficient_data">Có SV thiếu dữ liệu xét thi</option>
                <option value="has_alert">Có cảnh báo CMS</option>
              </> : <>
                <option value="udemy_late">Có SV Udemy chậm tiến độ</option>
                <option value="has_alert">Có cảnh báo Udemy</option>
              </>}
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

        <TrainingKpiStrip compact items={isCms ? [
          { key: 'teachers', label: 'Giảng viên CMS', value: countLabel(summary.teacher_count), hint: 'Theo bộ lọc hiện tại' },
          { key: 'classes', label: 'Lớp CMS', value: countLabel(summary.class_count), hint: `${countLabel(summary.subject_count)} môn` },
          { key: 'cms', label: 'Đồng bộ CMS', value: ratioLabel(summary.cms_synced_count, summary.cms_student_count), hint: `${countLabel(summary.learning_enrolled_count)} đã ghi danh` },
          { key: 'active', label: 'Đang học', value: countLabel(summary.learning_active_count), hint: `${countLabel(summary.student_count)} lượt sinh viên` },
          { key: 'risk', label: 'Cần theo dõi', value: countLabel(summary.risk_student_count), hint: `${countLabel(summary.deadline_late_student_count)} trễ deadline`, tone: summary.risk_student_count > 0 ? 'warning' : 'success' },
          { key: 'course', label: 'Chưa ghép Course', value: countLabel(summary.classes_without_course_count), hint: 'Chỉ lớp CMS', tone: summary.classes_without_course_count > 0 ? 'warning' : 'success' },
        ] : [
          { key: 'teachers', label: 'Giảng viên Udemy', value: countLabel(summary.teacher_count), hint: 'Theo bộ lọc hiện tại' },
          { key: 'classes', label: 'Lớp Udemy', value: countLabel(summary.class_count), hint: `${countLabel(summary.subject_count)} môn` },
          { key: 'students', label: 'Sinh viên Udemy', value: countLabel(summary.udemy_student_count || summary.student_count), hint: 'Theo roster AP' },
          { key: 'imported', label: 'Đã có tiến độ', value: ratioLabel(summary.udemy_progress_student_count, summary.udemy_student_count || summary.student_count), hint: 'Snapshot gần nhất' },
          { key: 'progress', label: 'Tiến độ trung bình', value: percentLabel(summary.udemy_progress_average_percent), hint: 'Theo file import mới nhất' },
          { key: 'late', label: 'Chậm tiến độ', value: countLabel(summary.udemy_progress_late_count), hint: 'Theo mốc kế hoạch đến hạn', tone: summary.udemy_progress_late_count > 0 ? 'warning' : 'success' },
        ]} />

        {cacheJob &&
          ["queued", "running", "failed"].includes(cacheJob.status) && (
            <InlineNotice
              notice={{
                type: cacheJob.status === "failed" ? "error" : "info",
                title: `Làm mới báo cáo giảng viên ${platformLabel}`,
                body: `${cacheJob.progress_label} · ${jobPercent(cacheJob)}%${cacheJob.status === "failed" ? ` · ${cacheJob.error_message || "Thất bại"}` : ""}`,
              }}
            />
          )}

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
          tableId={`teacher-management-${platform}`}
          caption={`Danh sách giảng viên ${platformLabel}`}
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
    </PageRoot>
  );
}
