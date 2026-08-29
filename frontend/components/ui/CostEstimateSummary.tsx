'use client'

import { CostEstimateLike } from '../../types'
import { VisualIcon } from './VisualIcon'

function money(value: unknown) {
  const num = Number(value || 0)
  return `$${num.toFixed(6)}`
}

function vnd(value: unknown) {
  return `${Number(value || 0).toLocaleString('vi-VN')} VND`
}

function tokens(value: unknown) {
  return Number(value || 0).toLocaleString('vi-VN')
}

export function CostEstimateSummary({ estimate }: { estimate: CostEstimateLike | null }) {
  if (!estimate) return <p className="helper">Nên estimate cost trước khi generate.</p>
  const rows = [
    { label: 'Token input', value: tokens(estimate.estimated_input_tokens), hint: `Đã cache: ${tokens(estimate.estimated_cached_input_tokens)}`, icon: 'database' as const, tone: 'blue' as const },
    { label: 'Output dự kiến', value: tokens(estimate.estimated_output_tokens), hint: `${tokens(estimate.estimated_output_tokens_per_question)} tokens/câu · ${estimate.model_name || 'model'}`, icon: 'sparkles' as const, tone: 'violet' as const },
    { label: 'Chi phí gốc', value: money(estimate.estimated_raw_cost_usd), hint: 'Chưa nhân safety factor', icon: 'money' as const, tone: 'amber' as const },
    { label: 'Chi phí an toàn', value: money(estimate.estimated_cost_usd), hint: vnd(estimate.estimated_cost_vnd), icon: 'shield' as const, tone: 'green' as const },
    { label: 'Nguồn đếm token input', value: estimate.token_source || estimate.estimate_token_source || '—', hint: estimate.quota_message || 'Quota hợp lệ', icon: 'server' as const, tone: 'cyan' as const },
    { label: 'Hiệu chỉnh output', value: estimate.output_calibration?.strategy || 'mặc định an toàn', hint: 'Dựa trên actual output/job trước nếu có', icon: 'analytics' as const, tone: 'slate' as const },
  ]
  return <div className="estimate-summary">{rows.map((row) => <div key={row.label}><VisualIcon label={row.label} icon={row.icon} tone={row.tone} size={16} /><div><span>{row.label}</span><b className="text-clip">{row.value}</b><small>{row.hint}</small></div></div>)}</div>
}
