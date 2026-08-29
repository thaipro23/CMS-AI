import type { AppIconName } from '../icons/AppIcon'
import type { VisualTone } from './VisualIcon'
import { VisualIcon } from './VisualIcon'

export function MetricCard({ title, value, hint, icon, tone }: { title: string; value: string | number; hint?: string; icon?: AppIconName; tone?: VisualTone }) {
  return <div className={`metric-card visual-card tone-${tone || 'auto'}`}>
    <VisualIcon label={title} icon={icon} tone={tone} />
    <div className="metric-card-copy"><span>{title}</span><b>{value}</b>{hint && <small>{hint}</small>}</div>
  </div>
}
