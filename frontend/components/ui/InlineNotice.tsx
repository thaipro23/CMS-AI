"use client";

import Link from "next/link";
import { ActionMessageType } from "./ActionMessage";

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
      className={`academic-inline-notice ${notice.type}`}
      role={notice.type === "error" ? "alert" : "status"}
      aria-live="polite"
    >
      <b>{notice.title || titleFor(notice.type)}</b>
      <span>{notice.body}</span>
      {notice.actionHref && notice.actionLabel ? (
        <Link
          className="btn secondary small notice-action-btn"
          href={notice.actionHref}
        >
          {notice.actionLabel}
        </Link>
      ) : null}
      {notice.onRetry ? (
        <button
          className="btn secondary small notice-action-btn"
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
  const body = compactError(raw, fallback);
  return { type: "error", title: "Có lỗi", body };
}

function compactError(raw: string, fallback: string) {
  const text = String(raw || "").trim();
  if (!text) return fallback;
  if (/401|unauthori[sz]ed|missing bearer/i.test(text))
    return "Phiên đăng nhập hết hạn. Đăng nhập lại.";
  if (/403|forbidden|permission|phân quyền/i.test(text))
    return "Bạn không có quyền thực hiện thao tác này.";
  if (/404|not found|không tìm thấy/i.test(text))
    return "Không tìm thấy dữ liệu cần xử lý.";
  if (/422|validation|invalid/i.test(text))
    return "Dữ liệu chưa hợp lệ. Kiểm tra lại thông tin nhập.";
  if (/timeout|timed out/i.test(text))
    return "Hệ thống xử lý quá lâu. Thử lại sau.";
  if (/network|failed to fetch/i.test(text))
    return "Không kết nối được máy chủ.";
  const firstLine = text.split("\n").find(Boolean) || text;
  return firstLine.length > 140 ? `${firstLine.slice(0, 137)}...` : firstLine;
}

function titleFor(type: ActionMessageType) {
  if (type === "success") return "Thành công";
  if (type === "error") return "Có lỗi";
  if (type === "warning") return "Cần kiểm tra";
  return "Thông báo";
}
