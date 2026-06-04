'use client'

type DiversityReport = {
  total_questions?: number
  concept_count?: number
  diversity_score?: number
  overloaded_concepts?: Array<{ concept: string; count: number; sample?: string; difficulty_counts?: Record<string, number>; status_counts?: Record<string, number> }>
  family_count?: number
  multi_variant_family_count?: number
  top_families?: Array<{ family_id: string; count: number; concept_title?: string; question_ids?: string[] }>
  near_duplicate_group_count?: number
  near_duplicate_groups?: Array<{ size: number; representative_question_text?: string; question_ids?: string[]; statuses?: Record<string, number>; difficulties?: Record<string, number> }>
  top_concepts?: Array<{ concept: string; count: number; sample?: string }>
}

export function DiversityReportPanel({ report }: { report: DiversityReport | null }) {
  if (!report) return null
  const overloaded = report.overloaded_concepts || []
  const duplicates = report.near_duplicate_groups || []
  const topConcepts = report.top_concepts || []
  const topFamilies = report.top_families || []
  return <section className="card diversity-panel">
    <div className="section-head">
      <div>
        <h3>Độ đa dạng câu hỏi</h3>
        <p className="helper">Báo cáo độ đa dạng câu hỏi, nhóm concept bị lặp và nhóm gần trùng.</p>
      </div>
      <span className="badge">Điểm {report.diversity_score ?? 0}/100</span>
    </div>
    <div className="summary-grid compact-summary">
      <div><span>Tổng</span><b>{report.total_questions ?? 0}</b></div>
      <div><span>Concept</span><b>{report.concept_count ?? 0}</b></div>
      <div><span>Family</span><b>{report.family_count ?? 0}</b></div>
      <div><span>Family nhiều variant</span><b>{report.multi_variant_family_count ?? 0}</b></div>
      <div><span>Lặp nhiều</span><b>{overloaded.length}</b></div>
      <div><span>Gần trùng</span><b>{report.near_duplicate_group_count ?? duplicates.length}</b></div>
    </div>
    {topFamilies.length > 0 && <div className="report-block">
      <h4>Question family nhiều variant</h4>
      {topFamilies.filter((item) => item.count > 1).slice(0, 6).map((item) => <div className="report-row" key={item.family_id}>
        <b>{item.concept_title || item.family_id}</b><span>{item.count} variant</span><small>{item.family_id}</small>
      </div>)}
    </div>}
    {overloaded.length > 0 && <div className="report-block">
      <h4>Concept bị lặp nhiều</h4>
      {overloaded.slice(0, 6).map((item) => <div className="report-row" key={item.concept}>
        <b>{item.concept}</b><span>{item.count} câu</span><small>{item.sample}</small>
      </div>)}
    </div>}
    {duplicates.length > 0 && <div className="report-block">
      <h4>Nhóm câu gần trùng</h4>
      {duplicates.slice(0, 6).map((group, index) => <div className="report-row" key={`${group.representative_question_text}-${index}`}>
        <b>Nhóm {index + 1}: {group.size} câu</b><span>{(group.question_ids || []).slice(0, 4).map((id) => id.slice(0, 8)).join(', ')}</span><small>{group.representative_question_text}</small>
      </div>)}
    </div>}
    {overloaded.length === 0 && duplicates.length === 0 && <p className="helper success-text">Không thấy nhóm trùng lớn. Bộ câu hỏi đang khá đa dạng.</p>}
    {topConcepts.length > 0 && <details className="report-details"><summary>Xem concept nhiều nhất</summary><div className="report-block">{topConcepts.slice(0, 10).map((item) => <div className="report-row" key={item.concept}><b>{item.concept}</b><span>{item.count} câu</span><small>{item.sample}</small></div>)}</div></details>}
  </section>
}
