'use client'

import { useEffect, useState } from 'react'
import { createCmsQuizNode, downloadApprovedOlx, exportApprovedOlx, getCourseNodes, getPublishHistory, insertCmsProblemBanks, previewFamilyBankPlan, publishApprovedToOpenEdx, publishFamilyBankPlan, rollbackPublishBatch } from '../../lib/api'
import { useAppContext } from '../../context/AppContext'
import { ActionMessage, ActionMessageData, toUserError } from '../../components/ui/ActionMessage'
import { LoadingButton } from '../../components/ui/LoadingButton'
import { CmsProblemBankInsertResult, CmsQuizNodeResult, CourseNodeOption, FamilyBankPlan, FamilyBankSlot, PublishBatchSummary, PublishLibrarySummary, PublishResult } from '../../types'

type PublishMode = 'publish_new' | 'replace' | 'delete_reimport'

function statusLabel(status: string) {
  if (status === 'published' || status === 'verified' || status === 'success' || status === 'published_ok_stale_verify' || status === 'published_with_tag_warning') return 'Published'
  if (status === 'published_with_pending_changes' || status === 'warning') return 'Published with pending changes'
  if (status === 'imported_needs_manual_publish') return 'Imported but needs manual publish'
  if (status === 'imported_needs_manual_verify') return 'Imported but needs manual verify'
  if (status === 'failed') return 'Failed'
  return status || '—'
}

function statusClass(status: string) {
  const value = (status || '').toLowerCase()
  if (value.includes('failed') || value.includes('insufficient')) return 'status danger'
  if (value.includes('pending') || value.includes('manual') || value.includes('warning') || value.includes('repeat') || value.includes('optional')) return 'status warning'
  return 'status success'
}

function LibrarySummaryTable({ rows }: { rows: PublishLibrarySummary[] }) {
  if (!rows.length) return <div className="empty-state">Chưa có kết quả publish theo Library.</div>
  return <div className="table-wrap"><table className="data-table compact-table">
    <thead><tr><th>Library</th><th>Số câu</th><th>Trạng thái</th><th>Studio</th></tr></thead>
    <tbody>{rows.map((row) => <tr key={`${row.library_key}-${row.difficulty}`}>
      <td className="text-clip"><b>{row.library_display_name || row.library_key}</b><small>{row.library_key}</small></td>
      <td>{row.component_count} components<br /><small>{row.verified_count || 0} verified · {row.pending_count || 0} pending</small></td>
      <td><span className={statusClass(row.status)}>{statusLabel(row.status)}</span></td>
      <td>{row.studio_url ? <a className="btn small secondary" href={row.studio_url} target="_blank" rel="noreferrer">Mở</a> : <span className="muted">Không có link</span>}</td>
    </tr>)}</tbody>
  </table></div>
}

function formatCombination(value?: number) {
  if (!value) return '—'
  if (value >= 1000000000000) return '≥ 1.000.000.000.000'
  return Math.round(value).toLocaleString('vi-VN')
}

function CoverageTable({ plan }: { plan: FamilyBankPlan }) {
  return <div className="table-wrap"><table className="data-table compact-table">
    <thead><tr><th>Difficulty</th><th>Cần</th><th>Family có</th><th>Slot đã tạo</th><th>Trạng thái</th></tr></thead>
    <tbody>{plan.coverage.map((row) => <tr key={row.difficulty}>
      <td><b>{row.difficulty}</b></td>
      <td>{row.target_slots}</td>
      <td>{row.available_families}</td>
      <td>{row.selected_slots}<br /><small>{row.optional_family_count || 0} family phụ · {row.repeated_slot_count || 0} slot lặp</small></td>
      <td><span className={statusClass(row.status)}>{row.status}</span></td>
    </tr>)}</tbody>
  </table></div>
}

function SlotEditor({ plan, onChange }: { plan: FamilyBankPlan, onChange: (plan: FamilyBankPlan) => void }) {
  const hardLocked = Boolean(plan.require_all_approved)
  function removeSlot(slotNo: number) {
    const slots = plan.slots.filter((slot) => slot.slot_no !== slotNo).map((slot, index) => ({ ...slot, slot_no: index + 1 }))
    onChange({ ...plan, slots, total_questions: slots.length })
  }

  function moveFamily(fromSlotNo: number, familyId: string, toSlotNo: number) {
    if (fromSlotNo === toSlotNo) return
    const source = plan.slots.find((slot) => slot.slot_no === fromSlotNo)
    const moving = source?.families.find((family) => family.family_id === familyId)
    if (!source || !moving || source.families.length <= 1) return
    const rebuild = (slot: FamilyBankSlot, families: FamilyBankSlot['families']): FamilyBankSlot => {
      const questionIds = Array.from(new Set(families.flatMap((family) => family.question_ids || [])))
      return { ...slot, families, family_names: families.map((family) => family.family_name), question_ids: questionIds, variant_count: questionIds.length, rule: `random 1/${Math.max(questionIds.length, 1)} variants` }
    }
    const slots = plan.slots.map((slot) => {
      if (slot.slot_no === fromSlotNo) return rebuild(slot, slot.families.filter((family) => family.family_id !== familyId))
      if (slot.slot_no === toSlotNo) return rebuild(slot, [...slot.families.filter((family) => family.family_id !== familyId), moving])
      return slot
    })
    onChange({ ...plan, slots, hard_guard: undefined, message: 'Kế hoạch đã được giáo viên chỉnh; Hard Guard sẽ kiểm tra lại trước khi publish/insert.' })
  }

  function removeFamily(slotNo: number, familyId: string) {
    const slots = plan.slots.map((slot) => {
      if (slot.slot_no !== slotNo) return slot
      const families = slot.families.filter((family) => family.family_id !== familyId)
      const questionIds = families.flatMap((family) => family.question_ids || [])
      return {
        ...slot,
        families,
        family_names: families.map((family) => family.family_name),
        question_ids: Array.from(new Set(questionIds)),
        variant_count: Array.from(new Set(questionIds)).length,
        rule: `random 1/${Math.max(Array.from(new Set(questionIds)).length, 1)} variants`,
      }
    }).filter((slot) => slot.families.length > 0)
    onChange({ ...plan, slots, total_questions: slots.length })
  }

  if (!plan.slots.length) return <div className="empty-state">Chưa có slot nào trong kế hoạch.</div>
  return <div className="table-wrap"><table className="data-table compact-table family-slot-table">
    <thead><tr><th>Slot</th><th>Difficulty</th><th>Family trong Problem Bank</th><th>Variants</th><th>Rule</th><th>Sửa</th></tr></thead>
    <tbody>{plan.slots.map((slot: FamilyBankSlot) => <tr key={slot.slot_no}>
      <td><b>S{String(slot.slot_no).padStart(2, '0')}</b>{slot.repeated_family ? <small className="danger-text">Lặp family</small> : null}</td>
      <td>{slot.difficulty}</td>
      <td>{slot.families.map((family) => <span className="tag-chip" key={family.family_id}>
        {family.family_name}
        {hardLocked ? <select className="family-move-select" title="Di chuyển cụm sang slot khác" value={slot.slot_no} disabled={slot.families.length <= 1} onChange={(event) => moveFamily(slot.slot_no, family.family_id, Number(event.target.value))}>{plan.slots.map((target) => <option key={target.slot_no} value={target.slot_no}>S{String(target.slot_no).padStart(2, '0')}</option>)}</select> : <button type="button" title="Bỏ family khỏi slot" onClick={() => removeFamily(slot.slot_no, family.family_id)}>×</button>}
      </span>)}{slot.warning ? <small className="warning-text">{slot.warning}</small> : null}</td>
      <td>{slot.variant_count}</td>
      <td>{slot.rule}</td>
      <td>{hardLocked ? <small className="success-text">Được di chuyển cụm · không được xóa câu</small> : <button className="btn small secondary" type="button" onClick={() => removeSlot(slot.slot_no)}>Bỏ slot</button>}</td>
    </tr>)}</tbody>
  </table></div>
}

export default function ExportPage() {
  const { courseId, authHeaders, can } = useAppContext()
  const [olxPreview, setOlxPreview] = useState('')
  const [message, setMessage] = useState<ActionMessageData | null>(null)
  const [loadingAction, setLoadingAction] = useState<string | null>(null)
  const [publishMode, setPublishMode] = useState<PublishMode>('publish_new')
  const [result, setResult] = useState<PublishResult | null>(null)
  const [history, setHistory] = useState<PublishBatchSummary[]>([])
  const [plan, setPlan] = useState<FamilyBankPlan | null>(null)
  const [courseNodes, setCourseNodes] = useState<CourseNodeOption[]>([])
  const [targetNodeId, setTargetNodeId] = useState('')
  const [quizTitle, setQuizTitle] = useState('AI Learning Check')
  const [unitTitle, setUnitTitle] = useState('Quiz tự luyện')
  const [quizNodeResult, setQuizNodeResult] = useState<CmsQuizNodeResult | null>(null)
  const [problemBankResult, setProblemBankResult] = useState<CmsProblemBankInsertResult | null>(null)
  const [planPublished, setPlanPublished] = useState(false)
  const [totalQuestions, setTotalQuestions] = useState(10)
  const [easyPercent, setEasyPercent] = useState(50)
  const [mediumPercent, setMediumPercent] = useState(30)
  const [hardPercent, setHardPercent] = useState(20)

  useEffect(() => {
    const saved = window.localStorage.getItem('ai_openedx_olx_preview')
    if (saved) setOlxPreview(saved)
  }, [])

  useEffect(() => {
    setPlanPublished(false)
    setQuizNodeResult(null)
    setProblemBankResult(null)
    loadHistory()
    loadCourseNodes()
  }, [courseId])

  async function loadCourseNodes() {
    try {
      const rows = await getCourseNodes(courseId, authHeaders())
      const eligible = rows.filter((node) => ['course', 'chapter', 'sequential'].includes((node.block_type || '').toLowerCase()))
      setCourseNodes(eligible)
      setTargetNodeId((current) => current && eligible.some((node) => node.node_id === current) ? current : (eligible.find((node) => (node.block_type || '').toLowerCase() === 'chapter')?.node_id || eligible[0]?.node_id || ''))
    } catch {
      setCourseNodes([])
      setTargetNodeId('')
    }
  }

  async function loadHistory() {
    try {
      const data = await getPublishHistory(courseId, authHeaders())
      const batches = data.batches || []
      setHistory(batches)
      setPlanPublished(Boolean(batches.some((batch) => batch.summary?.family_bank_plan)))
    } catch {
      setHistory([])
    }
  }

  async function preview() {
    setLoadingAction('preview')
    try {
      const data = await exportApprovedOlx(courseId, authHeaders())
      setOlxPreview(data.olx)
      window.localStorage.setItem('ai_openedx_olx_preview', data.olx)
      setMessage({ type: 'success', body: `Đã preview ${data.question_count} câu hỏi approved.` })
    } catch (error) {
      setMessage(toUserError(error))
    } finally {
      setLoadingAction(null)
    }
  }

  async function buildPlan() {
    setLoadingAction('plan')
    try {
      const selectedPlanNode = courseNodes.find((node) => node.node_id === targetNodeId)
      const data = await previewFamilyBankPlan(courseId, {
        chapter_node_id: selectedPlanNode?.block_type?.toLowerCase() === 'chapter' ? targetNodeId : null,
        total_questions: totalQuestions,
        difficulty_distribution: { easy: easyPercent, medium: mediumPercent, hard: hardPercent },
        require_all_approved: true,
        shortage_policy: 'never_repeat_question',
        max_families_per_bank: 20,
      }, authHeaders(true)) as FamilyBankPlan
      setPlan(data)
      setPlanPublished(false)
      setQuizNodeResult(null)
      setProblemBankResult(null)
      const warnings = data.warnings?.length || 0
      setMessage({ type: warnings ? 'warning' : 'success', title: 'Đã tính kế hoạch Stable Family', body: `${data.planner_engine || 'stable_family_deterministic_v1'} · không gọi GPT · ${data.assigned_question_count || 0}/${data.eligible_question_count || 0} câu duy nhất dùng đúng một lần · ${data.stable_family_count || 0} stable family · ${data.slots.length} slot${warnings ? ` · ${warnings} cảnh báo` : ''}.` })
    } catch (error) {
      setMessage(toUserError(error))
    } finally {
      setLoadingAction(null)
    }
  }

  async function publishPlanToOpenEdx() {
    if (!plan) return
    setLoadingAction('publish-plan')
    try {
      const data = await publishFamilyBankPlan(courseId, plan, authHeaders(true), publishMode) as PublishResult
      setResult(data)
      await loadHistory()
      const warnings = data?.warnings || 0
      const failed = data?.failed || 0
      setPlanPublished(failed === 0 && (data?.published || 0) > 0)
      setMessage({
        type: failed ? 'warning' : warnings ? 'warning' : 'success',
        title: failed ? 'Publish kế hoạch chưa hoàn tất' : 'Đã publish kế hoạch',
        body: `Đã publish/import ${data.published || 0} variants từ ${plan.slots.length} slot. Warning ${warnings}, lỗi ${failed}.`,
      })
    } catch (error) {
      setMessage(toUserError(error, 'Publish Family Bank Plan thất bại.'))
    } finally {
      setLoadingAction(null)
    }
  }

  async function createQuizNodeInCms() {
    const latest = plan || result?.family_bank_plan || history[0]?.summary?.family_bank_plan || null
    if (!targetNodeId) {
      setMessage({ type: 'warning', title: 'Chưa chọn vị trí tạo Quiz', body: 'Hãy chọn Course, Chapter hoặc Subsection trong cây nội dung.' })
      return
    }
    if (!latest) {
      setMessage({ type: 'warning', title: 'Chưa có kế hoạch', body: 'Hoàn tất Bước 1: Tính kế hoạch trước.' })
      return
    }
    if (!planPublished) {
      setMessage({ type: 'warning', title: 'Thư viện chưa sẵn sàng', body: 'Hoàn tất Bước 2: Chuẩn bị thư viện trước khi tạo Quiz.' })
      return
    }
    setLoadingAction('create-quiz-node')
    try {
      const data = await createCmsQuizNode(courseId, {
        parent_node_id: targetNodeId,
        quiz_title: quizTitle,
        unit_title: unitTitle,
        plan: latest,
      }, authHeaders(true)) as CmsQuizNodeResult
      setQuizNodeResult(data)
      await loadCourseNodes()
      if (!data.leaf_unit_node_id) throw new Error('Open edX đã tạo cấu trúc nhưng không trả leaf Unit usage key.')

      try {
        const bankData = await insertCmsProblemBanks(courseId, {
          unit_node_id: data.leaf_unit_node_id,
          plan: latest,
          strict_component_selection: true,
        }, authHeaders(true)) as CmsProblemBankInsertResult
        setProblemBankResult(bankData)
        await loadCourseNodes()
        setMessage({
          type: 'success',
          title: 'Hoàn tất Quiz trên Open edX',
          body: `${bankData.message || 'Đã tạo native Problem Bank.'} ${bankData.slots_inserted}/${bankData.slots_requested} slot đã được xác minh.`,
        })
      } catch (insertError) {
        setProblemBankResult(null)
        setMessage(toUserError(insertError, `Unit Quiz đã được tạo nhưng Problem Bank chưa hoàn tất. Unit: ${data.leaf_unit_node_id}. Dùng mục “Thử lại Problem Bank” sau khi xử lý lỗi.`))
      }
    } catch (error) {
      setMessage(toUserError(error, 'Tạo Quiz trên Open edX thất bại. Không có trạng thái thành công giả.'))
    } finally {
      setLoadingAction(null)
    }
  }

  async function insertProblemBanksIntoCms() {
    const latest = plan || result?.family_bank_plan || history[0]?.summary?.family_bank_plan || null
    const unitNodeId = quizNodeResult?.leaf_unit_node_id
    if (!unitNodeId || !latest) {
      setMessage({ type: 'warning', title: 'Chưa thể thử lại', body: 'Chưa có Unit Quiz hoặc kế hoạch hợp lệ.' })
      return
    }
    setLoadingAction('insert-problem-banks')
    try {
      const data = await insertCmsProblemBanks(courseId, {
        unit_node_id: unitNodeId,
        plan: latest,
        strict_component_selection: true,
      }, authHeaders(true)) as CmsProblemBankInsertResult
      setProblemBankResult(data)
      await loadCourseNodes()
      setMessage({
        type: 'success',
        title: 'Đã hoàn tất Problem Bank',
        body: `${data.message || 'Hoàn tất.'} ${data.slots_inserted}/${data.slots_requested} slot đã được xác minh.`,
      })
    } catch (error) {
      setMessage(toUserError(error, 'Thử lại Problem Bank thất bại. Xem Audit Log/CMS connector log để biết lỗi thật.'))
    } finally {
      setLoadingAction(null)
    }
  }

  async function publishToOpenEdx() {
    setLoadingAction('publish')
    try {
      const data = await publishApprovedToOpenEdx(courseId, authHeaders(true), publishMode)
      setResult(data)
      await loadHistory()
      const published = data?.published ?? 0
      const failed = data?.failed ?? 0
      const warnings = data?.warnings ?? 0
      if (failed > 0) {
        const firstError = data?.errors?.[0]?.error ? ` Lỗi đầu tiên: ${data.errors[0].error}` : ''
        setMessage({ type: 'warning', title: 'Publish chưa hoàn tất', body: `Đã publish/import ${published} câu, warning ${warnings}, lỗi ${failed}.${firstError}` })
      } else if (warnings > 0) {
        setMessage({ type: 'warning', title: 'Đã import nhưng cần kiểm tra Studio', body: `Đã import ${published} câu. Có ${warnings} câu/library còn pending/manual verify. Xem bảng verify bên dưới.` })
      } else {
        setMessage({ type: 'success', title: 'Publish thành công', body: `Đã publish ${published} câu approved sang Open edX và verify xong.` })
      }
    } catch (error) {
      setMessage(toUserError(error, 'Publish thất bại. Kiểm tra USE_MOCK_OPENEDX, connector production và backend logs.'))
    } finally {
      setLoadingAction(null)
    }
  }

  async function download() {
    setLoadingAction('download')
    try {
      await downloadApprovedOlx(courseId, authHeaders())
      setMessage({ type: 'success', body: 'Đã tạo file XML để tải xuống.' })
    } catch (error) {
      setMessage(toUserError(error))
    } finally {
      setLoadingAction(null)
    }
  }

  async function rollback(batch: PublishBatchSummary, level: 'ai_server' | 'openedx') {
    if (!window.confirm(`Rollback batch ${batch.id.slice(0, 8)} ở mức ${level}?`)) return
    setLoadingAction(`rollback:${batch.id}:${level}`)
    try {
      const data: any = await rollbackPublishBatch(batch.id, level, authHeaders(true))
      const manual = data.manual_delete_required || 0
      const failed = data.failed_delete_count || 0
      const title = manual || failed ? 'Rollback một phần' : 'Đã rollback'
      const type = manual || failed ? 'warning' : 'success'
      setMessage({ type, title, body: `Reset ${data.reset_questions || 0} câu. Đã xóa Open edX: ${data.deleted_openedx_components || 0}. Cần xóa tay: ${manual}. Lỗi xóa: ${failed}.` })
      await loadHistory()
    } catch (error) {
      setMessage(toUserError(error))
    } finally {
      setLoadingAction(null)
    }
  }

  const latestRows = result?.libraries || history[0]?.summary?.libraries || []
  const latestPlan = plan || result?.family_bank_plan || history[0]?.summary?.family_bank_plan || null
  const selectedNode = courseNodes.find((node) => node.node_id === targetNodeId) || null

  return <div className="page-stack">
    <section className="card page-intro export-hero">
      <div>
        <h2>Tạo Quiz luyện tập trên Open edX</h2>
        <p className="helper">Thực hiện theo 3 bước. Hệ thống dùng native Problem Bank Beta của Ulmo.3 và chỉ báo hoàn tất sau khi xác minh đầy đủ.</p>
      </div>
      <details className="export-mode-box">
        <summary>Tùy chọn cập nhật thư viện</summary>
        <label>Chế độ cập nhật</label>
        <select className="input" value={publishMode} onChange={(event) => setPublishMode(event.target.value as PublishMode)}>
          <option value="publish_new">Chỉ thêm câu chưa có</option>
          <option value="replace">Cập nhật component đã có</option>
          <option value="delete_reimport">Xóa rồi import lại</option>
        </select>
      </details>
    </section>

    <ActionMessage message={message} onClose={() => setMessage(null)} />

    <section className="card">
      <div className="section-head"><div><h2>Quy trình 3 bước</h2><p className="helper">Mỗi bước chỉ mở khi bước trước đã sẵn sàng.</p></div></div>
      <div className="summary-grid">
        <div><span>Bước 1 · Kế hoạch</span><b>{latestPlan ? 'Đã có' : 'Chưa thực hiện'}</b></div>
        <div><span>Bước 2 · Thư viện</span><b>{planPublished ? 'Sẵn sàng' : 'Chưa sẵn sàng'}</b></div>
        <div><span>Bước 3 · Quiz</span><b>{problemBankResult?.status === 'native_itembanks_created_and_verified' ? 'Hoàn tất' : 'Chưa hoàn tất'}</b></div>
      </div>
    </section>

    <section className="card family-plan-card">
      <div className="section-head"><div><h2>Bước 1 · Tính kế hoạch câu hỏi</h2><p className="helper">Concept và family đã được xác định khi sinh câu hỏi. Bước này không gọi GPT lại: backend chuẩn hóa stable family, giữ nguyên một family trong một slot và dùng mọi câu duy nhất đã duyệt đúng một lần.</p></div></div>
      <div className="inline-form compact-form">
        <label>Tổng câu<input className="input mini-input" type="number" min={1} max={100} value={totalQuestions} onChange={(event) => setTotalQuestions(Number(event.target.value || 1))} /></label>
        <label>EASY %<input className="input mini-input" type="number" min={0} max={100} value={easyPercent} onChange={(event) => setEasyPercent(Number(event.target.value || 0))} /></label>
        <label>MEDIUM %<input className="input mini-input" type="number" min={0} max={100} value={mediumPercent} onChange={(event) => setMediumPercent(Number(event.target.value || 0))} /></label>
        <label>HARD %<input className="input mini-input" type="number" min={0} max={100} value={hardPercent} onChange={(event) => setHardPercent(Number(event.target.value || 0))} /></label>
        <LoadingButton className="btn" loading={loadingAction === 'plan'} disabled={!can('publish_to_openedx') || Boolean(loadingAction)} onClick={buildPlan}>Bước 1 · Tính kế hoạch</LoadingButton>
        <LoadingButton className="btn danger" loading={loadingAction === 'publish-plan'} disabled={!can('publish_to_openedx') || !latestPlan || Boolean(loadingAction)} onClick={publishPlanToOpenEdx}>Bước 2 · Chuẩn bị thư viện</LoadingButton>
      </div>
      {latestPlan && <div className="summary-grid">
        <div><span>Slot</span><b>{latestPlan.slots.length}</b></div>
        <div><span>Tổ hợp đề con</span><b>{formatCombination(latestPlan.combination_count_estimate)}</b></div>
        <div><span>Policy</span><b>{latestPlan.shortage_policy}</b></div>
        <div><span>Cảnh báo</span><b>{latestPlan.warnings?.length || 0}</b></div>
        <div><span>Planner</span><b>{latestPlan.planner_engine || '—'}</b></div>
        <div><span>Gọi GPT</span><b>{latestPlan.uses_llm ? 'Có' : 'Không'}</b></div>
        <div><span>Stable family</span><b>{latestPlan.stable_family_count || 0}</b></div>
        <div><span>Dùng câu duy nhất</span><b>{latestPlan.assigned_question_count || 0}/{latestPlan.eligible_question_count || 0}</b></div>
        <div><span>Loại bản ghi trùng</span><b>{latestPlan.exact_duplicate_record_count || 0}</b></div>
        <div><span>Hard Guard</span><b>{latestPlan.hard_guard?.valid ? 'PASS' : 'FAIL'}</b></div>
      </div>}
      {latestPlan?.hard_guard ? <div className={latestPlan.hard_guard.valid ? 'success-box' : 'warning-box'}>{latestPlan.hard_guard.summary}</div> : null}
      {latestPlan?.warnings?.length ? <div className="warning-box">{latestPlan.warnings.map((warning) => <div key={warning}>{warning}</div>)}</div> : null}
      {latestPlan && <CoverageTable plan={latestPlan} />}
      {latestPlan && <SlotEditor plan={latestPlan} onChange={setPlan} />}
    </section>

    <section className="card cms-quiz-card">
      <div className="section-head"><div><h2>Bước 3 · Tạo Quiz trên Open edX</h2><p className="helper">Hệ thống tự tạo Unit và native Problem Bank Beta. Mỗi slot hiển thị ngẫu nhiên 1 câu; mọi component đều được xác minh trước khi báo hoàn tất.</p></div></div>
      <div className="inline-form compact-form">
        <label>Vị trí tạo Quiz
          <select className="input wide-input" value={targetNodeId} onChange={(event) => setTargetNodeId(event.target.value)}>
            {!courseNodes.length ? <option value="">Chưa có node phù hợp, hãy sync course trước</option> : null}
            {courseNodes.map((node) => <option key={node.node_id} value={node.node_id}>{`${'— '.repeat(Math.min(node.depth, 4))}${node.title} (${node.block_type})`}</option>)}
          </select>
        </label>
        <label>Tên Quiz<input className="input" value={quizTitle} onChange={(event) => setQuizTitle(event.target.value)} /></label>
        <label>Tên Unit<input className="input" value={unitTitle} onChange={(event) => setUnitTitle(event.target.value)} /></label>
        <LoadingButton className="btn danger" loading={loadingAction === 'create-quiz-node'} disabled={!can('publish_to_openedx') || !latestPlan || !planPublished || !targetNodeId || Boolean(loadingAction)} onClick={createQuizNodeInCms}>Bước 3 · Tạo Quiz và Problem Bank</LoadingButton>
      </div>
      {selectedNode ? <p className="helper">Quiz sẽ được tạo dưới: <b>{selectedNode.path}</b>.</p> : null}
      {!planPublished ? <div className="warning-box">Hoàn tất Bước 2 để mở nút tạo Quiz.</div> : null}
      {quizNodeResult?.leaf_unit_node_id && !problemBankResult ? <details><summary>Xử lý nâng cao</summary><p className="helper">Dùng khi Unit đã tạo nhưng Problem Bank bị lỗi giữa chừng.</p><LoadingButton className="btn secondary" loading={loadingAction === 'insert-problem-banks'} disabled={Boolean(loadingAction)} onClick={insertProblemBanksIntoCms}>Thử lại Problem Bank</LoadingButton></details> : null}
      {quizNodeResult ? <div className="table-wrap"><table className="data-table compact-table">
        <thead><tr><th>Node</th><th>Type</th><th>Usage key</th><th>Trạng thái</th></tr></thead>
        <tbody>{quizNodeResult.created_nodes.map((node) => <tr key={node.usage_key}>
          <td>{node.display_name}</td>
          <td>{node.block_type}</td>
          <td className="text-clip"><small>{node.usage_key}</small></td>
          <td><span className={node.created ? 'status success' : 'status warning'}>{node.created ? 'created' : 'existing'}</span></td>
        </tr>)}</tbody>
      </table></div> : null}
      {problemBankResult ? <div className="table-wrap"><table className="data-table compact-table">
        <thead><tr><th>Problem Bank</th><th>Slot</th><th>Component</th><th>Xác minh</th></tr></thead>
        <tbody>{problemBankResult.problem_bank_blocks.map((block) => <tr key={block.usage_key}>
          <td><b>{block.display_name}</b><small>{block.usage_key}</small></td>
          <td>{block.slot_no} · {block.difficulty}</td>
          <td>{block.verification?.child_count || 0}/{block.verification?.expected_component_count || 0}</td>
          <td><span className={block.selection_verified ? 'status success' : 'status danger'}>{block.selection_verified ? 'Đã xác minh' : 'Chưa hợp lệ'}</span></td>
        </tr>)}</tbody>
      </table>
      {problemBankResult.warnings?.length ? <div className="warning-box">{problemBankResult.warnings.map((warning) => <div key={warning}>{warning}</div>)}</div> : null}
      </div> : null}
    </section>

    <details className="card">
      <summary>Công cụ xuất nâng cao</summary>
      <div className="action-strip">
        <LoadingButton className="btn" loading={loadingAction === 'preview'} disabled={!can('export_questions') || Boolean(loadingAction)} onClick={preview}>Xem trước OLX</LoadingButton>
        <LoadingButton className="btn secondary" loading={loadingAction === 'download'} disabled={!can('export_questions') || Boolean(loadingAction)} onClick={download}>Tải XML</LoadingButton>
        <LoadingButton className="btn secondary" loading={loadingAction === 'publish'} disabled={!can('publish_to_openedx') || Boolean(loadingAction)} onClick={publishToOpenEdx}>Publish tất cả approved</LoadingButton>
      </div>
    </details>

    <section className="card">
      <div className="section-head"><div><h2>Kết quả publish</h2><p className="helper">Các câu được publish vào cùng Library theo Chapter. Difficulty/family nằm ở tag của component.</p></div></div>
      {result && <div className="summary-grid">
        <div><span>Batch</span><b>{result.batch_id?.slice(0, 8) || '—'}</b></div>
        <div><span>Published/imported</span><b>{result.published}</b></div>
        <div><span>Warnings</span><b>{result.warnings || 0}</b></div>
        <div><span>Failed</span><b>{result.failed}</b></div>
      </div>}
      <LibrarySummaryTable rows={latestRows} />
    </section>

    <section className="card">
      <h2>Xem trước OLX</h2>
      <pre className="xml-preview">{olxPreview || 'Chưa có OLX preview. Hãy bấm Xem trước OLX hoặc preview từng câu từ Ngân hàng câu hỏi.'}</pre>
    </section>

    <section className="card">
      <div className="section-head"><div><h2>Lịch sử publish</h2><p className="helper">Rollback mức AI Server sẽ đưa câu về approved. Rollback Open edX sẽ cố gắng xóa component nếu connector hỗ trợ.</p></div><button className="btn secondary" onClick={loadHistory}>Tải lại</button></div>
      {!history.length ? <div className="empty-state">Chưa có lịch sử publish.</div> : <div className="table-wrap"><table className="data-table compact-table">
        <thead><tr><th>Batch</th><th>Mode</th><th>Kết quả</th><th>Thời gian</th><th>Rollback</th></tr></thead>
        <tbody>{history.map((batch) => <tr key={batch.id}>
          <td><b>{batch.id.slice(0, 8)}</b><small>{batch.actor_id}</small></td>
          <td>{batch.mode}</td>
          <td><span className={statusClass(batch.status)}>{batch.status}</span><br /><small>{batch.published_count} ok · {batch.warning_count} warning · {batch.failed_count} lỗi</small></td>
          <td>{batch.created_at ? new Date(batch.created_at).toLocaleString('vi-VN') : '—'}</td>
          <td className="button-row compact">
            <button className="btn small secondary" disabled={Boolean(loadingAction)} onClick={() => rollback(batch, 'ai_server')}>AI Server</button>
            <button className="btn small danger" disabled={Boolean(loadingAction)} onClick={() => rollback(batch, 'openedx')}>Open edX</button>
          </td>
        </tr>)}</tbody>
      </table></div>}
    </section>
  </div>
}
