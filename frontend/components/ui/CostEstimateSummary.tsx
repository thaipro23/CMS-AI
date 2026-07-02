'use client'

import { CostEstimateLike } from '../../types'

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
  return <div className="estimate-summary">
    <div><span>Token input</span><b>{tokens(estimate.estimated_input_tokens)}</b><small>Đã cache: {tokens(estimate.estimated_cached_input_tokens)}</small></div>
    <div><span>Output dự kiến</span><b>{tokens(estimate.estimated_output_tokens)}</b><small>{tokens(estimate.estimated_output_tokens_per_question)} tokens/câu · {estimate.model_name || 'model'}</small></div>
    <div><span>Chi phí gốc</span><b>{money(estimate.estimated_raw_cost_usd)}</b><small>Chưa nhân safety factor</small></div>
    <div><span>Chi phí an toàn</span><b>{money(estimate.estimated_cost_usd)}</b><small>{vnd(estimate.estimated_cost_vnd)}</small></div>
    <div><span>Nguồn đếm token input</span><b className="text-clip">{estimate.token_source || estimate.estimate_token_source || '—'}</b><small>{estimate.quota_message || 'Quota hợp lệ'}</small></div>
    <div><span>Hiệu chỉnh output</span><b className="text-clip">{estimate.output_calibration?.strategy || 'mặc định an toàn'}</b><small>Dựa trên actual output/job trước nếu có</small></div>
  </div>
}
