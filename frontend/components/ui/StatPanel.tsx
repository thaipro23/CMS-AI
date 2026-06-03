export function StatPanel({ title, rows, empty = 'Chưa có dữ liệu.' }: { title: string; rows: Record<string, number> | { label: string; value: number | string }[]; empty?: string }) {
  const entries = Array.isArray(rows) ? rows : Object.entries(rows || {}).map(([label, value]) => ({ label, value }))
  return <div className="stat-panel">
    <h3>{title}</h3>
    {entries.length ? entries.map((row) => <div className="stat-row" key={row.label}><span>{row.label}</span><b>{row.value}</b></div>) : <p className="helper">{empty}</p>}
  </div>
}
