export function MetricCard({ title, value, hint }: { title: string; value: string | number; hint?: string }) {
  return <div className="metric-card"><span>{title}</span><b>{value}</b>{hint && <small>{hint}</small>}</div>
}
