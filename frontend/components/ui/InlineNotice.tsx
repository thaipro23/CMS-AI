"use client";

import Link from "next/link";
import { ActionMessageType } from "./ActionMessage";
import { VisualIcon } from "./VisualIcon";
import { userFacingError } from '../../lib/userFacingError';
import styles from './FeedbackMessage.module.css';

export type InlineNoticeData = {
  type: ActionMessageType;
  title?: string;
  body: string;
  actionHref?: string;
  actionLabel?: string;
  onRetry?: () => void;
  retryLabel?: string;
};

export function InlineNotice({ notice }: { notice: InlineNoticeData | null }) {
  if (!notice) return null;
  return (
    <div
      className={`academic-inline-notice enterprise-inline-notice ${notice.type} ${styles.message} ${styles[notice.type]}`}
      role={notice.type === "error" ? "alert" : "status"}
      aria-live="polite"
    >
      <VisualIcon label={notice.title || titleFor(notice.type)} icon={noticeIcon(notice.type)} tone={noticeTone(notice.type)} className={`notice-visual-icon ${styles.icon}`} />
      <div className={`notice-copy ${styles.copy}`}><b>{notice.title || titleFor(notice.type)}</b>
      <span>{notice.type === 'error' ? userFacingError(notice.body) : notice.body}</span></div>
      {notice.actionHref && notice.actionLabel ? (
        <Link
          className={`btn secondary small notice-action-btn ${styles.action}`}
          href={notice.actionHref}
        >
          {notice.actionLabel}
        </Link>
      ) : null}
      {notice.onRetry ? (
        <button
          className={`btn secondary small notice-action-btn ${styles.action}`}
          type="button"
          onClick={notice.onRetry}
        >
          {notice.retryLabel || "Thử lại"}
        </button>
      ) : null}
    </div>
  );
}

export function noticeSuccess(
  body: string,
  title = "Thành công",
): InlineNoticeData {
  return { type: "success", title, body };
}
export function noticeInfo(
  body: string,
  title = "Thông báo",
): InlineNoticeData {
  return { type: "info", title, body };
}
export function noticeWarning(
  body: string,
  title = "Cần kiểm tra",
): InlineNoticeData {
  return { type: "warning", title, body };
}
export function noticeError(
  error: unknown,
  fallback = "Thao tác thất bại. Vui lòng thử lại.",
): InlineNoticeData {
  const raw = error instanceof Error ? error.message : String(error || "");
  const body = userFacingError(raw, fallback);
  return { type: "error", title: "Không thể hoàn tất", body };
}



function titleFor(type: ActionMessageType) {
  if (type === "success") return "Thành công";
  if (type === "error") return "Có lỗi";
  if (type === "warning") return "Cần kiểm tra";
  return "Thông báo";
}

function noticeIcon(type: ActionMessageType) {
  if (type === "success") return "check" as const;
  if (type === "error" || type === "warning") return "alert" as const;
  return "info" as const;
}
function noticeTone(type: ActionMessageType) {
  if (type === "success") return "green" as const;
  if (type === "error") return "red" as const;
  if (type === "warning") return "amber" as const;
  return "blue" as const;
}
