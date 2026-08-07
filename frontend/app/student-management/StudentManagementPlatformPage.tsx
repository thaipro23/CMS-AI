"use client";

import Link from "next/link";
import { Suspense, useEffect, useMemo, useState } from "react";
import { useAppContext } from "../../context/AppContext";
import { useFeedback } from "../../components/ui/FeedbackProvider";
import {
  autoMapAcademicSubjectCourse,
  autoMapAllAcademicSubjectCoursesAndSync,
  getAcademicBulkOperationJobs,
  getAcademicCampuses,
  getAcademicTeacherSubjects,
  getAcademicTerms,
} from "../../lib/api";
import {
  AcademicBulkOperationJob,
  AcademicCampus,
  AcademicLearningComponentScore,
  AcademicSubjectManagement,
  AcademicSubjectManagementSummary,
  AcademicTerm,
} from "../../types";
import { PageRoot } from '../../components/layout/PageHeader'
import { EnterpriseScreenHeader } from '../../components/layout/EnterpriseDesignContract'
import { TrainingKpiStrip } from '../../components/training/TrainingWorkspace'
import { WorkspaceSection } from '../../components/operations/OperationsWorkspace'
import { EnterpriseDataTable, EnterpriseTableColumn } from "../../components/table/EnterpriseDataTable";
import { useAcademicTableState } from "../../hooks/useAcademicTableState";
import { useDebouncedValue } from "../../lib/useDebouncedValue";
import {
  InlineNotice,
  InlineNoticeData,
  noticeError,
  noticeInfo,
  noticeSuccess,
  noticeWarning,
} from "../../components/ui/InlineNotice";

type TrainingPlatform = 'cms' | 'udemy';

const EMPTY_SUBJECT_SUMMARY: AcademicSubjectManagementSummary = {
  subject_count: 0,
  class_count: 0,
  student_count: 0,
  teacher_count: 0,
  cms_synced_count: 0,
  cms_unsynced_count: 0,
  course_mapped_count: 0,
  course_missing_count: 0,
  learning_enrolled_count: 0,
  learning_active_count: 0,
  learning_synced_count: 0,
  alert_subject_count: 0,
  scope_label: "Toàn bộ bộ lọc",
};

function normalizeSubjectSummary(
  value?: Partial<AcademicSubjectManagementSummary> | null,
): AcademicSubjectManagementSummary {
  return {
    ...EMPTY_SUBJECT_SUMMARY,
    ...(value || {}),
    subject_count: Number(value?.subject_count || 0),
    class_count: Number(value?.class_count || 0),
    student_count: Number(value?.student_count || 0),
    teacher_count: Number(value?.teacher_count || 0),
    cms_synced_count: Number(value?.cms_synced_count || 0),
    cms_unsynced_count: Number(value?.cms_unsynced_count || 0),
    course_mapped_count: Number(value?.course_mapped_count || 0),
    course_missing_count: Number(value?.course_missing_count || 0),
    learning_enrolled_count: Number(value?.learning_enrolled_count || 0),
    learning_active_count: Number(value?.learning_active_count || 0),
    learning_synced_count: Number(value?.learning_synced_count || 0),
    alert_subject_count: Number(value?.alert_subject_count || 0),
    scope_label: value?.scope_label || "Toàn bộ bộ lọc",
  };
}

function countLabel(value?: number | null) {
  return String(value || 0);
}

function statusClass(status?: string | null) {
  const value = (status || "").toLowerCase();
  if (["mapped", "already_mapped", "auto_mapped"].includes(value))
    return "status-pill success";
  if (value === "auto_candidate") return "status-pill warning";
  if (["multiple_candidates", "not_found"].includes(value))
    return "status-pill danger";
  return "status-pill neutral";
}

function percentLabel(value?: number | null) {
  if (typeof value !== "number" || Number.isNaN(value)) return "N/A";
  return `${Math.round(value * 10) / 10}%`;
}

function componentScoreText(score: AcademicLearningComponentScore) {
  if (typeof score.percent === "number" && !Number.isNaN(score.percent))
    return percentLabel(score.percent);
  if (typeof score.earned === "number" && typeof score.possible === "number")
    return `${Math.round(score.earned * 100) / 100}/${Math.round(score.possible * 100) / 100}`;
  return "N/A";
}

function componentSummaryLine(scores?: AcademicLearningComponentScore[]) {
  if (!scores?.length) return "N/A";
  return scores
    .slice(0, 3)
    .map((score) => `${score.name || "TP"}: ${componentScoreText(score)}`)
    .join(" · ");
}

function alertText(alerts?: string[]) {
  return alerts && alerts.length
    ? alerts.slice(0, 2).join(", ")
    : "Không có cảnh báo";
}

function counterText(total: number, page: number, pageSize: number) {
  if (!total) return "0 môn";
  const start = (page - 1) * pageSize + 1;
  const end = Math.min(total, page * pageSize);
  return `${start}-${end} / ${total}`;
}

function buildSubjectClassesHref(
  subject: AcademicSubjectManagement,
  context: {
    platform: TrainingPlatform;
    termId: string;
    termName?: string;
    branch: string;
    campus: string;
  },
) {
  const params = new URLSearchParams();
  params.set("platform", context.platform);
  if (context.termId) params.set("term_id", context.termId);
  if (context.branch) params.set("branch", context.branch);
  if (context.campus) params.set("campus", context.campus);
  if (context.termName) params.set("term_name", context.termName);
  params.set("subject_code", subject.subject_code || "");
  params.set("subject_name", subject.subject_name || "");
  const qs = params.toString();
  return `/student-management/subjects/${encodeURIComponent(subject.id)}/classes${qs ? `?${qs}` : ""}`;
}

function StudentManagementSubjectsContent({ platform }: { platform: TrainingPlatform }) {
  const isCms = platform === "cms";
  const platformLabel = isCms ? "CMS" : "Udemy";
  const { authHeaders } = useAppContext();
  const { confirmAction } = useFeedback();
  const headers = useMemo(() => authHeaders(), [authHeaders]);
  const jsonHeaders = useMemo(() => authHeaders(true), [authHeaders]);
  const [terms, setTerms] = useState<AcademicTerm[]>([]);
  const [campuses, setCampuses] = useState<AcademicCampus[]>([]);
  const [subjects, setSubjects] = useState<AcademicSubjectManagement[]>([]);
  const { state, update } = useAcademicTableState({ branch: "poly", status: "all", pageSize: 50 });
  const { termId, branch, campus, q: search, status: learningStatus, page, pageSize, density } = state;
  const debouncedSearch = useDebouncedValue(search, 350);
  const [total, setTotal] = useState(0);
  const [summary, setSummary] = useState<AcademicSubjectManagementSummary>(
    EMPTY_SUBJECT_SUMMARY,
  );
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState<InlineNoticeData | null>(null);
  const [mappingSubjectId, setMappingSubjectId] = useState("");
  const [bulkMapping, setBulkMapping] = useState(false);
  const [bulkJobs, setBulkJobs] = useState<AcademicBulkOperationJob[]>([]);
  const [currentBulkJobId, setCurrentBulkJobId] = useState("");

  useEffect(() => {
    let cancelled = false;
    getAcademicTerms(headers, { branch, active: true })
      .then((items) => {
        if (cancelled) return;
        setTerms(items);
        if (!items.some((item) => item.id === termId)) {
          const preferred = items.find((item) => item.term_name === "Summer 2026") || items[0];
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
      .then((items) => {
        if (cancelled) return;
        setCampuses(items);
        if (campus && !items.some((item) => item.campus_code === campus)) update({ campus: "" });
      })
      .catch(() => setCampuses([]));
    return () => {
      cancelled = true;
    };
  }, [headers, branch, campus]);

  const loadSubjects = async (cancelledRef?: { cancelled: boolean }) => {
    setLoading(true);
    setMessage(null);
    try {
      const result = await getAcademicTeacherSubjects(headers, {
        termId,
        branch,
        campus,
        search: debouncedSearch,
        learningStatus,
        learningPlatform: platform,
        page,
        pageSize,
      });
      if (cancelledRef?.cancelled) return;
      setSubjects(result.items);
      setTotal(result.total);
      setSummary(normalizeSubjectSummary(result.summary));
    } catch (error) {
      if (!cancelledRef?.cancelled)
        setMessage({
          ...noticeError(error, "Không tải được danh sách môn."),
          onRetry: () => loadSubjects(),
        });
    } finally {
      if (!cancelledRef?.cancelled) setLoading(false);
    }
  };

  useEffect(() => {
    const cancelledRef = { cancelled: false };
    loadSubjects(cancelledRef);
    return () => {
      cancelledRef.cancelled = true;
    };
  }, [headers, termId, branch, campus, debouncedSearch, learningStatus, page, pageSize, platform]);

  const loadBulkJobs = async () => {
    if (!isCms) { setBulkJobs([]); return; }
    try {
      const items = await getAcademicBulkOperationJobs(headers, {
        status: "active",
        limit: 20,
      });
      setBulkJobs(
        items.filter((job) => {
          const request = job.request_json || {};
          const sameTerm =
            !termId || job.term_id === termId || request.term_id === termId;
          const sameBranch =
            !branch || job.branch === branch || request.branch === branch;
          const sameCampus =
            !campus || job.campus === campus || request.campus === campus;
          return (
            job.job_type === "subject_auto_map_all_sync" &&
            sameTerm &&
            sameBranch &&
            sameCampus
          );
        }),
      );
    } catch {
      setBulkJobs([]);
    }
  };

  const selectedTerm = terms.find((item) => item.id === termId);
  const totalPages = Math.max(1, Math.ceil(total / pageSize));

  useEffect(() => {
    if (page > totalPages) update({ page: totalPages }, { resetPage: false });
  }, [page, totalPages, update]);

  useEffect(() => {
    loadBulkJobs();
    const timer = window.setInterval(() => loadBulkJobs(), 10000);
    return () => window.clearInterval(timer);
  }, [headers, termId, branch, campus, isCms]);

  const runAutoMapAllAndSync = async () => {
    if (!isCms) return;
    if (!termId) {
      setMessage(
        noticeWarning("Chọn học kỳ trước khi tự động ghép Course CMS."),
      );
      return;
    }
    const accepted = await confirmAction({
      title: "Tự động ghép Course CMS?",
      description: "Hệ thống sẽ ghép các môn trong bộ lọc hiện tại, sau đó đưa lớp phù hợp vào hàng đợi đồng bộ tài khoản CMS, ghi danh và dữ liệu học tập.",
      confirmLabel: "Tạo tác vụ nền",
    });
    if (!accepted) return;
    setBulkMapping(true);
    setMessage(noticeInfo("Đang tạo tác vụ nền."));
    try {
      const result = await autoMapAllAcademicSubjectCoursesAndSync(
        jsonHeaders,
        {
          termId,
          branch,
          campus,
          search: debouncedSearch,
          learningStatus,
          force: true,
          limit: 500,
          syncLearning: true,
          maxClasses: 3000,
        },
      );
      setCurrentBulkJobId(result.job_id || "");
      setMessage({
        ...noticeSuccess(result.message || "Đã tạo tác vụ nền."),
        actionHref: "/jobs",
        actionLabel: "Xem tác vụ nền",
      });
      await loadBulkJobs();
    } catch (error) {
      setMessage(
        noticeError(error, "Không tạo được tác vụ tự động ghép Course CMS."),
      );
    } finally {
      setBulkMapping(false);
    }
  };

  const runAutoMap = async (subject: AcademicSubjectManagement) => {
    if (!isCms) return;
    if (!termId) {
      setMessage(
        noticeWarning("Chọn học kỳ trước khi tự động ghép Course CMS."),
      );
      return;
    }
    setMappingSubjectId(subject.id);
    setMessage(null);
    try {
      const result = await autoMapAcademicSubjectCourse(
        jsonHeaders,
        subject.id,
        { termId, branch },
      );
      setMessage(noticeSuccess(result.message || "Đã ghép Course CMS."));
      const refreshed = await getAcademicTeacherSubjects(headers, {
        termId,
        branch,
        campus,
        search: debouncedSearch,
        learningStatus,
        learningPlatform: platform,
        page,
        pageSize,
      });
      setSubjects(refreshed.items);
      setTotal(refreshed.total);
      setSummary(normalizeSubjectSummary(refreshed.summary));
    } catch (error) {
      setMessage(noticeError(error, "Không tự động ghép được Course CMS."));
    } finally {
      setMappingSubjectId("");
    }
  };

  const columns = useMemo<EnterpriseTableColumn<AcademicSubjectManagement>[]>(() => {
    const common: EnterpriseTableColumn<AcademicSubjectManagement>[] = [
      { key: "stt", header: "STT", kind: "index", width: 52, sticky: "left", hideable: false, render: (_subject, index) => (page - 1) * pageSize + index + 1 },
      { key: "subject", header: "Môn", kind: "identity", minWidth: 230, sticky: "left", priority: "required", hideable: false, render: (subject) => <><b>{subject.subject_code}</b><small>{subject.subject_name}</small></> },
      { key: "scale", header: "Quy mô", kind: "number", width: 150, priority: "important", hideable: true, render: (subject) => <><b>{subject.class_count} lớp · {subject.student_count} SV</b><small>{subject.teacher_count} GV · {subject.campus_count} cơ sở</small></> },
    ];
    const actions: EnterpriseTableColumn<AcademicSubjectManagement> = {
      key: "actions", header: "Thao tác", kind: "actions", width: isCms ? 126 : 112, sticky: "right", hideable: false,
      render: (subject) => <div className="row-actions">
        <Link className="btn small primary" href={buildSubjectClassesHref(subject, { platform, termId, termName: selectedTerm?.term_name, branch, campus })}>Xem lớp</Link>
        {isCms && !["mapped", "already_mapped", "auto_mapped"].includes(String(subject.course_mapping_status || "").toLowerCase()) ? <button className="btn small secondary" type="button" disabled={mappingSubjectId === subject.id} onClick={() => runAutoMap(subject)}>{mappingSubjectId === subject.id ? "Đang ghép..." : "Tự động ghép"}</button> : null}
      </div>,
    };
    if (isCms) return [
      ...common,
      { key: "cms", header: "Đồng bộ CMS", kind: "status", minWidth: 155, priority: "important", hideable: true, render: (subject) => <><span className={subject.cms_unsynced_count ? "status-pill warning" : "status-pill success"}>{subject.cms_synced_count}/{subject.student_count} đã match</span><small>{subject.cms_unsynced_count} cần xử lý</small></> },
      { key: "course", header: "Course CMS", kind: "status", minWidth: 170, priority: "optional", hideable: true, render: (subject) => <><span className={statusClass(subject.course_mapping_status)}>{subject.course_mapping_label || subject.course_mapping_status}</span><small>{subject.openedx_course_id || subject.suggested_openedx_course_id || "N/A"}</small></> },
      { key: "learning", header: "Học tập CMS", kind: "progress", minWidth: 190, priority: "important", hideable: true, render: (subject) => <><b>{subject.learning_enrolled_count || 0}/{subject.student_count} ghi danh</b><small>{subject.learning_active_count || 0} đã học · TB {percentLabel(subject.learning_avg_progress_percent)}</small>{subject.learning_alerts?.length ? <small className="danger-text">{alertText(subject.learning_alerts)}</small> : null}</> },
      actions,
    ];
    return [
      ...common,
      { key: "progress", header: "Tiến độ Udemy", kind: "progress", minWidth: 190, priority: "important", hideable: true, render: (subject) => <><span className={(subject.udemy_progress_student_count || 0) < subject.student_count ? "status-pill warning" : "status-pill success"}>Đã import {subject.udemy_progress_student_count || 0}/{subject.student_count}</span><small>Tiến độ TB {percentLabel(subject.udemy_progress_average_percent)}</small></> },
      { key: "late", header: "Cảnh báo Udemy", kind: "status", minWidth: 170, priority: "important", hideable: true, render: (subject) => <><span className={(subject.udemy_progress_late_count || 0) > 0 ? "status-pill danger" : "status-pill success"}>{subject.udemy_progress_late_count || 0} SV chậm</span><small>{subject.learning_alerts?.length ? alertText(subject.learning_alerts) : "Không có cảnh báo"}</small></> },
      actions,
    ];
  }, [branch, campus, isCms, mappingSubjectId, page, pageSize, platform, selectedTerm?.term_name, termId]);

  return (
    <PageRoot className="page-stack enterprise-standard-page student-management-page academic-flow-page ux-enterprise-page">
      <EnterpriseScreenHeader
        eyebrow="Vận hành đào tạo"
        title={`Quản lý sinh viên ${platformLabel}`}
        description={isCms ? "Quản lý môn, lớp, sinh viên, tài khoản CMS/Open edX, ghi danh và tiến độ học trong phạm vi được phân quyền." : "Quản lý môn, lớp, sinh viên, dữ liệu import và tiến độ Udemy trong phạm vi được phân quyền."}
        icon="students"
        tone="blue"
        breadcrumbs={[{ label: 'Vận hành đào tạo' }, { label: `Quản lý sinh viên ${platformLabel}` }]}
      />
      <section className="card academic-filter-panel" aria-label="Bộ lọc danh sách môn">
        <div className="academic-filter-bar">
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
            Trạng thái học tập
            <select
              className="input"
              value={learningStatus}
              onChange={(event) => {
                update({ status: event.target.value });
              }}
            >
              <option value="all">Tất cả môn</option>
              {isCms ? <>
                <option value="no_course_map">Chưa ghép course</option>
                <option value="cms_not_synced">Chưa đồng bộ CMS</option>
                <option value="no_learning_data">Chưa có progress CMS</option>
              </> : <>
                <option value="udemy_not_imported">Chưa import tiến độ</option>
                <option value="udemy_late">Có SV chậm tiến độ</option>
              </>}
              <option value="has_alert">Có cảnh báo</option>
            </select>
          </label>
          <label className="academic-filter-search">
            Tìm môn
            <input
              className="input"
              value={search}
              onChange={(event) => {
                update({ q: event.target.value });
              }}
              placeholder="WEB107, BUS2015, thiết kế..."
            />
          </label>
        </div>
      </section>

      <TrainingKpiStrip compact items={isCms ? [
          { key: 'subjects', label: 'Môn CMS', value: countLabel(summary.subject_count), hint: counterText(total, page, pageSize) },
          { key: 'classes', label: 'Lớp CMS', value: countLabel(summary.class_count), hint: 'Theo bộ lọc hiện tại' },
          { key: 'students', label: 'Sinh viên', value: countLabel(summary.student_count), hint: 'Không đếm theo trang' },
          { key: 'course', label: 'Course CMS', value: `${countLabel(summary.course_mapped_count)}/${countLabel(summary.subject_count)}`, hint: `${countLabel(summary.course_missing_count)} môn chưa ghép`, tone: summary.course_missing_count > 0 ? 'warning' : 'success' },
          { key: 'alerts', label: 'Cần kiểm tra', value: countLabel(summary.alert_subject_count), hint: 'Môn có cảnh báo CMS', tone: summary.alert_subject_count > 0 ? 'warning' : 'success' },
      ] : [
          { key: 'subjects', label: 'Môn Udemy', value: countLabel(summary.subject_count), hint: counterText(total, page, pageSize) },
          { key: 'classes', label: 'Lớp Udemy', value: countLabel(summary.class_count), hint: 'Theo bộ lọc hiện tại' },
          { key: 'students', label: 'Sinh viên', value: countLabel(summary.student_count), hint: 'Không đếm theo trang' },
          { key: 'imported', label: 'Đã có tiến độ', value: countLabel(summary.udemy_progress_student_count), hint: `TB ${percentLabel(summary.udemy_progress_average_percent)}` },
          { key: 'late', label: 'Chậm tiến độ', value: countLabel(summary.udemy_progress_late_count), hint: 'Theo milestone hiện tại', tone: (summary.udemy_progress_late_count || 0) > 0 ? 'warning' : 'success' },
      ]} />

      <WorkspaceSection
        title={`Danh sách môn ${platformLabel}`}
        description={isCms ? `${countLabel(summary.course_missing_count)} môn chưa ghép Course CMS trong phạm vi hiện tại.` : `${countLabel(summary.udemy_progress_late_count)} sinh viên đang chậm tiến độ Udemy trong phạm vi hiện tại.`}
        actions={isCms ? <button className="btn" type="button" disabled={!termId || bulkMapping} onClick={runAutoMapAllAndSync}>{bulkMapping ? "Đang tạo job..." : "Tự động ghép Course CMS"}</button> : undefined}
        icon="book"
        tone={isCms ? (summary.course_missing_count > 0 ? "amber" : "green") : ((summary.udemy_progress_late_count || 0) > 0 ? "amber" : "green")}
      >
        {isCms && bulkJobs.length ? (
          <InlineNotice
            notice={{
              type: "success",
              title: "Đang chạy nền",
              body: `${bulkJobs.length} tác vụ đang xử lý. Bạn có thể F5 hoặc chuyển màn hình.`,
              actionHref: "/jobs",
              actionLabel: "Xem tác vụ nền",
            }}
          />
        ) : null}
        {isCms && currentBulkJobId ? (
          <InlineNotice
            notice={{
              type: "success",
              title: "Đã tạo tác vụ",
              body: `Mã ${currentBulkJobId.slice(0, 8)} · worker đang xử lý.`,
              actionHref: "/jobs",
              actionLabel: "Xem tác vụ nền",
            }}
          />
        ) : null}

        <InlineNotice notice={message} />

        <EnterpriseDataTable
          tableId={`student-management-${platform}-subjects`}
          caption={`Danh sách môn ${platformLabel}`}
          rows={subjects}
          columns={columns}
          rowKey={(subject) => subject.id}
          density={density}
          onDensityChange={(value) => update({ density: value }, { resetPage: false })}
          loading={loading}
          error={message?.type === "error" ? message.body : undefined}
          onRetry={() => loadSubjects()}
          emptyTitle="Chưa có môn phù hợp"
          emptyDescription={`Đổi học kỳ, cơ sở, trạng thái hoặc xóa từ khóa. Nếu vẫn trống, kiểm tra môn đã được cấu hình ${platformLabel} tại Quản lý môn học và dữ liệu AP sync.`}
          emptyAction={<button className="btn secondary small" type="button" onClick={() => update({ q: "", status: "all", page: 1 }, { resetPage: false })}>Xóa bộ lọc nhanh</button>}
          page={page}
          pageSize={pageSize}
          total={total}
          totalPages={totalPages}
          onPageChange={(value) => update({ page: value }, { resetPage: false })}
          onPageSizeChange={(value) => update({ pageSize: value, page: 1 }, { resetPage: false })}
          label="môn"
          showSummary={false}
        />
      </WorkspaceSection>
    </PageRoot>
  );
}

export function StudentManagementPlatformPage({ platform }: { platform: TrainingPlatform }) {
  return (
    <Suspense
      fallback={<div className="card">Đang tải quản lý sinh viên...</div>}
    >
      <StudentManagementSubjectsContent platform={platform} />
    </Suspense>
  );
}
