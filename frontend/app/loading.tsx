export default function Loading() {
  return <div className="route-state-page" aria-label="Đang tải nội dung" aria-busy="true">
    <div className="route-loading-grid">
      <div className="route-loading-line" />
      <div className="route-loading-card" />
      <div className="route-loading-card" />
    </div>
  </div>
}
