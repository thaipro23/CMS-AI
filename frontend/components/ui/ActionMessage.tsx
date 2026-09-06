"use client";

import { VisualIcon } from "./VisualIcon";
import { userFacingError } from '../../lib/userFacingError';
import styles from './FeedbackMessage.module.css';

export type ActionMessageType = "success" | "error" | "info" | "warning";

export type ActionMessageData = {
  type: ActionMessageType;
  title?: string;
  body: string;
  detail?: string;
};



export function toUserError(
  error: unknown,
  fallback = "Thao tác thất bại. Vui lòng thử lại.",
): ActionMessageData {
  const raw = error instanceof Error ? error.message : String(error || "");
  return {
    type: "error",
    title: "Không thể hoàn tất",
    body: userFacingError(raw, fallback),
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
      className={`notice enterprise-action-message notice-${message.type} ${styles.message} ${styles[message.type]}`}
      role={message.type === "error" ? "alert" : "status"}
      aria-live="polite"
    >
      <VisualIcon label={message.title || titleFor(message.type)} icon={message.type === "success" ? "check" : message.type === "info" ? "info" : "alert"} tone={message.type === "success" ? "green" : message.type === "error" ? "red" : message.type === "warning" ? "amber" : "blue"} className={`notice-visual-icon ${styles.icon}`} />
      <div className={`notice-copy ${styles.copy}`}>
        <strong>{message.title || titleFor(message.type)}</strong>
        <p>{message.type === 'error' ? userFacingError(message.body) : message.body}</p>
        {message.detail && message.type !== 'error' && <small>{message.detail}</small>}
      </div>
      {onClose && (
        <button
          className={`notice-close ${styles.action}`}
          type="button"
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
