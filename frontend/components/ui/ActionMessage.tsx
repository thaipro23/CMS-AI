"use client";

import { VisualIcon } from "./VisualIcon";

export type ActionMessageType = "success" | "error" | "info" | "warning";

export type ActionMessageData = {
  type: ActionMessageType;
  title?: string;
  body: string;
  detail?: string;
};

function compactError(raw: string, fallback: string) {
  const text = String(raw || "").trim();
  if (!text) return fallback;
  if (/401|unauthori[sz]ed|missing bearer/i.test(text))
    return "Phiên đăng nhập hết hạn. Đăng nhập lại.";
  if (/403|forbidden|permission|phân quyền/i.test(text))
    return "Bạn không có quyền thực hiện thao tác này.";
  if (/404|not found|không tìm thấy/i.test(text))
    return "Không tìm thấy dữ liệu cần xử lý.";
  if (/422|validation|invalid/i.test(text) && !text.includes(":") && text.length < 100)
    return "Dữ liệu chưa hợp lệ. Kiểm tra lại thông tin nhập.";
  if (/timeout|timed out/i.test(text))
    return "Hệ thống xử lý quá lâu. Thử lại sau.";
  if (/network|failed to fetch/i.test(text))
    return "Không kết nối được máy chủ.";
  const firstLine = text.split("\n").find(Boolean) || text;
  return firstLine.length > 140 ? `${firstLine.slice(0, 137)}...` : firstLine;
}

export function toUserError(
  error: unknown,
  fallback = "Thao tác thất bại. Vui lòng thử lại.",
): ActionMessageData {
  const raw = error instanceof Error ? error.message : String(error || "");
  return {
    type: "error",
    title: "Có lỗi",
    body: compactError(raw, fallback),
    detail: raw && raw.length > 160 ? raw : undefined,
  };
}

export function ActionMessage({
  message,
  onClose,
}: {
  message: ActionMessageData | null;
  onClose?: () => void;
}) {
  if (!message) return null;
  return (
    <section
      className={`notice notice-${message.type}`}
      role={message.type === "error" ? "alert" : "status"}
      aria-live="polite"
    >
      <VisualIcon label={message.title || titleFor(message.type)} icon={message.type === "success" ? "check" : message.type === "info" ? "info" : "alert"} tone={message.type === "success" ? "green" : message.type === "error" ? "red" : message.type === "warning" ? "amber" : "blue"} className="notice-visual-icon" />
      <div className="notice-copy">
        <strong>{message.title || titleFor(message.type)}</strong>
        <p>{message.body}</p>
        {message.detail && <small>{message.detail}</small>}
      </div>
      {onClose && (
        <button
          className="notice-close"
          onClick={onClose}
          aria-label="Đóng thông báo"
        >
          ×
        </button>
      )}
    </section>
  );
}

function titleFor(type: ActionMessageType) {
  if (type === "success") return "Thành công";
  if (type === "error") return "Có lỗi";
  if (type === "warning") return "Cần kiểm tra";
  return "Thông báo";
}
