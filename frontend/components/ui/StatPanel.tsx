import type { AppIconName } from '../icons/AppIcon'
import type { VisualTone } from './VisualIcon'
import { VisualIcon } from './VisualIcon'

export function StatPanel({ title, rows, empty = 'Chưa có dữ liệu.', icon, tone }: { title: string; rows: Record<string, number> | { label: string; value: number | string }[]; empty?: string; icon?: AppIconName; tone?: VisualTone }) {
  const entries = Array.isArray(rows) ? rows : Object.entries(rows || {}).map(([label, value]) => ({ label, value }))
  return <div className="stat-panel visual-section-card">
    <div className="visual-section-heading"><VisualIcon label={title} icon={icon} tone={tone} /><div><h3>{title}</h3></div></div>
    {entries.length ? entries.map((row) => <div className="stat-row" key={row.label}><span>{row.label}</span><b>{row.value}</b></div>) : <p className="helper">{empty}</p>}
  </div>
}
