'use client'

import { useEffect, useState } from 'react'
import { getRuntimeSettings, updateRuntimeSettings, getRealtimePricing } from '../../lib/api'
import { useAppContext } from '../../context/AppContext'
import { ROLE_LABELS, ROLE_PERMISSIONS, RuntimeSettings, RuntimeSettingsUpdate, PricingResponse } from '../../types'
import { ActionMessage, ActionMessageData, toUserError } from '../../components/ui/ActionMessage'
import { LoadingButton } from '../../components/ui/LoadingButton'
import { PageHeader } from '../../components/layout/PageHeader'
import { WorkspaceSection, WorkspaceTabs } from '../../components/operations/OperationsWorkspace'
import { CoursePolicyPanel } from '../../components/settings/CoursePolicyPanel'

const defaultForm: RuntimeSettingsUpdate = {
  model: {
    model_provider: 'openai',
    openai_model: 'gpt-5-mini',
    openai_api_mode: 'responses',
    mock_llm: false,
    openai_api_key: '',
  },
  openedx: {
    use_mock_openedx: false,
    openedx_base_url: 'http://studio.local.openedx.io',
    openedx_cms_base_url: 'http://studio.local.openedx.io',
    openedx_lms_base_url: 'http://local.openedx.io',
    openedx_oauth_base_url: 'http://local.openedx.io',
    openedx_client_id: '',
    openedx_client_secret: '',
    openedx_access_token: '',
    openedx_oauth_token_url: '/oauth2/access_token/',
    openedx_course_blocks_path: '/api/courses/v2/blocks/',
    openedx_publish_endpoint: '/api/ai-connector/v1/courses/{course_id}/problems',
    openedx_library_endpoint: '/api/ai-connector/v1/courses/{course_id}/libraries',
    openedx_library_import_endpoint: '/api/ai-connector/v1/libraries/{library_key}/problems',
  },
  sso: {
    auth_mode: 'openedx_sso',
    allow_demo_role_header: false,
    jwt_secret: '',
  },
  cost: {
    cost_input_price_per_1m: 0.25,
    cost_cached_input_price_per_1m: 0.025,
    cost_output_price_per_1m: 2.0,
    cost_safety_factor: 1.5,
    usd_to_vnd: 26342,
  },
  worker: {
    openai_parallel_enabled: true,
    openai_max_parallel_calls: 3,
    openai_retry_max_attempts: 3,
    openai_retry_base_seconds: 2,
    openai_prompt_cache_warmup_enabled: true,
    generation_tail_batch_wait_enabled: true,
  },
}

function toForm(settings: RuntimeSettings): RuntimeSettingsUpdate {
  return {
    model: {
      model_provider: settings.model.model_provider || 'openai',
      openai_model: settings.model.openai_model || 'gpt-5-mini',
      openai_api_mode: settings.model.openai_api_mode || 'responses',
      mock_llm: settings.model.mock_llm,
      openai_api_key: '',
    },
    openedx: {
      use_mock_openedx: settings.openedx.use_mock_openedx,
      openedx_base_url: settings.openedx.openedx_base_url || 'http://studio.local.openedx.io',
      openedx_cms_base_url: settings.openedx.openedx_cms_base_url || settings.openedx.openedx_base_url || 'http://studio.local.openedx.io',
      openedx_lms_base_url: settings.openedx.openedx_lms_base_url || 'http://local.openedx.io',
      openedx_oauth_base_url: settings.openedx.openedx_oauth_base_url || settings.openedx.openedx_lms_base_url || 'http://local.openedx.io',
      openedx_client_id: settings.openedx.openedx_client_id || '',
      openedx_client_secret: '',
      openedx_access_token: '',
      openedx_oauth_token_url: settings.openedx.openedx_oauth_token_url || '/oauth2/access_token/',
      openedx_course_blocks_path: settings.openedx.openedx_course_blocks_path || '/api/courses/v2/blocks/',
      openedx_publish_endpoint: settings.openedx.openedx_publish_endpoint || '/api/ai-connector/v1/courses/{course_id}/problems',
      openedx_library_endpoint: settings.openedx.openedx_library_endpoint || '/api/ai-connector/v1/courses/{course_id}/libraries',
      openedx_library_import_endpoint: settings.openedx.openedx_library_import_endpoint || '/api/ai-connector/v1/libraries/{library_key}/problems',
    },
    sso: {
      auth_mode: settings.sso.auth_mode || 'openedx_sso',
      allow_demo_role_header: settings.sso.allow_demo_role_header,
      jwt_secret: '',
    },
    cost: {
      cost_input_price_per_1m: settings.cost?.cost_input_price_per_1m ?? 0.25,
      cost_cached_input_price_per_1m: settings.cost?.cost_cached_input_price_per_1m ?? 0.025,
      cost_output_price_per_1m: settings.cost?.cost_output_price_per_1m ?? 2.0,
      cost_safety_factor: settings.cost?.cost_safety_factor ?? 1.5,
      usd_to_vnd: settings.cost?.usd_to_vnd ?? 26342,
    },
    worker: {
      openai_parallel_enabled: settings.worker?.openai_parallel_enabled ?? true,
      openai_max_parallel_calls: settings.worker?.openai_max_parallel_calls ?? 3,
      openai_retry_max_attempts: settings.worker?.openai_retry_max_attempts ?? 3,
      openai_retry_base_seconds: settings.worker?.openai_retry_base_seconds ?? 2,
      openai_prompt_cache_warmup_enabled: settings.worker?.openai_prompt_cache_warmup_enabled ?? true,
      generation_tail_batch_wait_enabled: settings.worker?.generation_tail_batch_wait_enabled ?? true,
    },
  }
}

function mergeField<T extends keyof RuntimeSettingsUpdate>(form: RuntimeSettingsUpdate, section: T, name: keyof RuntimeSettingsUpdate[T], value: string | boolean | number): RuntimeSettingsUpdate {
  return { ...form, [section]: { ...form[section], [name]: value } } as RuntimeSettingsUpdate
}


export default function SettingsPage() {
  const { courseId, role, authHeaders, can } = useAppContext()
  const [settings, setSettings] = useState<RuntimeSettings | null>(null)
  const [form, setForm] = useState<RuntimeSettingsUpdate>(defaultForm)
  const [message, setMessage] = useState<ActionMessageData | null>(null)
  const [testMessage, setTestMessage] = useState<ActionMessageData | null>(null)
  const [pricing, setPricing] = useState<PricingResponse | null>(null)
  const [saving, setSaving] = useState(false)
  const [pricingLoading, setPricingLoading] = useState(false)
  const [activeTab, setActiveTab] = useState('limits')

  async function load() {
    try {
      const data = await getRuntimeSettings(authHeaders())
      setSettings(data)
      setForm(toForm(data))
      setMessage(null)
    } catch (e) {
      setMessage(toUserError(e))
    }
  }

  async function save() {
    setSaving(true)
    try {
      const data = await updateRuntimeSettings(form, authHeaders(true))
      setSettings(data)
      setForm(toForm(data))
      setMessage({ type: 'success', body: 'Đã lưu cấu hình runtime. Các request generate/sync tiếp theo sẽ dùng cấu hình mới.' })
    } catch (e) {
      setMessage(toUserError(e))
    } finally {
      setSaving(false)
    }
  }


  async function fetchPricing() {
    setPricingLoading(true)
    setTestMessage(null)
    try {
      const data = await getRealtimePricing(form.model.openai_model || 'gpt-5-mini', authHeaders(true), true)
      setPricing(data)
      setTestMessage({ type: 'success', title: 'Đã lấy giá pricing', body: `${data.model}: input $${data.input_price_per_1m}/1M, cached $${data.cached_input_price_per_1m}/1M, output $${data.output_price_per_1m}/1M.`, detail: `Source: ${data.source}` })
    } catch (e) {
      setTestMessage(toUserError(e))
    } finally {
      setPricingLoading(false)
    }
  }

  useEffect(() => { if (can('manage_settings')) load() }, [role])

  if (!can('manage_settings')) {
    return <div className="page-stack">
      <section className="card warning-card">
        <div className="eyebrow">403 / Admin only</div>
        <h2>Trang Settings chỉ dành cho admin</h2>
        <p className="helper">Role hiện tại là <b>{role}</b>. Backend cũng chặn bằng quyền <b>manage_settings</b>, nên teacher/reviewer/viewer không đọc hoặc sửa được API key, model và SSO.</p>
      </section>
      <section className="card">
        <h2>RBAC hiện tại</h2>
        <div className="role-box large"><b>{ROLE_LABELS[role]}</b><small>{ROLE_PERMISSIONS[role].join(', ')}</small></div>
      </section>
    </div>
  }

  return <div className="page-stack settings-page">
    <PageHeader
      eyebrow="Quản trị"
      title="Cài đặt hệ thống"
      description="Cấu hình theo từng nhóm. Secret chỉ được quản lý qua biến môi trường hoặc secret manager."
      secondaryActions={<><LoadingButton className="btn secondary" onClick={load}>Tải lại</LoadingButton>{activeTab === 'cost' ? <LoadingButton className="btn secondary" loading={pricingLoading} onClick={fetchPricing}>Cập nhật giá</LoadingButton> : null}</>}
      primaryAction={<LoadingButton className="btn" loading={saving} onClick={save}>Lưu cấu hình</LoadingButton>}
    />

    <ActionMessage message={message} onClose={() => setMessage(null)} />
    <ActionMessage message={testMessage} onClose={() => setTestMessage(null)} />

    <section className="settings-workspace">
      <WorkspaceTabs active={activeTab} onChange={setActiveTab} tabs={[
        { key: 'limits', label: 'Giới hạn tạo câu hỏi' },
        { key: 'model', label: 'Mô hình & worker' },
        { key: 'openedx', label: 'Kết nối Open edX' },
        { key: 'auth', label: 'SSO & xác thực' },
        { key: 'cost', label: 'Chi phí & pricing' },
      ]} />

      <div className="settings-panel">
        {activeTab === 'limits' ? <>
          <CoursePolicyPanel courseId="__bank_chapter_default__" headers={authHeaders()} writeHeaders={authHeaders(true)} canEdit={can('manage_settings')} />
          <WorkspaceSection title="Nguyên tắc runtime" description="Các secret không được ghi vào runtime JSON.">
            <div className="settings-secret-note">API key, OAuth secret, JWT secret và token phải được cấp qua biến môi trường hoặc secret manager của hạ tầng production.</div>
          </WorkspaceSection>
        </> : null}

        {activeTab === 'model' ? <>
          <WorkspaceSection title="Cổng mô hình" description="Model dùng cho tác vụ sinh câu hỏi.">
            <div className="settings-form-grid">
              <label>Nhà cung cấp<select className="input" value={form.model.model_provider} onChange={(event) => setForm(mergeField(form, 'model', 'model_provider', event.target.value))}><option value="openai">OpenAI</option><option value="local">Local</option><option value="auto">Tự động</option></select></label>
              <label>Tên mô hình<input className="input" value={form.model.openai_model} onChange={(event) => setForm(mergeField(form, 'model', 'openai_model', event.target.value))} placeholder="gpt-5-mini" /></label>
              <label>Chế độ API<select className="input" value={form.model.openai_api_mode} onChange={(event) => setForm(mergeField(form, 'model', 'openai_api_mode', event.target.value))}><option value="responses">Responses API</option><option value="chat_legacy">Chat legacy</option></select></label>
              <label>OpenAI API key<input className="input" type="password" value="" disabled placeholder={settings?.model.has_openai_api_key ? `Env đã có key: ${settings?.model.openai_api_key_masked}` : 'Cấu hình bằng OPENAI_API_KEY'} /></label>
            </div>
          </WorkspaceSection>
          <WorkspaceSection title="Worker và retry" description="Giữ warm-up cache bật để giảm chi phí input lặp.">
            <div className="settings-form-grid">
              <label className="check-row"><input type="checkbox" checked={form.worker?.openai_parallel_enabled ?? true} onChange={(event) => setForm(mergeField(form as any, 'worker' as any, 'openai_parallel_enabled' as any, event.target.checked))} /> Gọi GPT song song</label>
              <label className="check-row"><input type="checkbox" checked={form.worker?.openai_prompt_cache_warmup_enabled ?? true} onChange={(event) => setForm(mergeField(form as any, 'worker' as any, 'openai_prompt_cache_warmup_enabled' as any, event.target.checked))} /> Warm-up prompt cache</label>
              <label className="check-row wide"><input type="checkbox" checked={form.worker?.generation_tail_batch_wait_enabled ?? true} onChange={(event) => setForm(mergeField(form as any, 'worker' as any, 'generation_tail_batch_wait_enabled' as any, event.target.checked))} /> Tail chờ primary và bù thiếu theo difficulty</label>
              <label>Cuộc gọi song song tối đa<input className="input" type="number" min="1" max="8" value={form.worker?.openai_max_parallel_calls ?? 3} onChange={(event) => setForm(mergeField(form as any, 'worker' as any, 'openai_max_parallel_calls' as any, Number(event.target.value)))} /></label>
              <label>Số lần retry<input className="input" type="number" min="1" max="8" value={form.worker?.openai_retry_max_attempts ?? 3} onChange={(event) => setForm(mergeField(form as any, 'worker' as any, 'openai_retry_max_attempts' as any, Number(event.target.value)))} /></label>
              <label>Chờ retry (giây)<input className="input" type="number" min="0.1" step="0.5" value={form.worker?.openai_retry_base_seconds ?? 2} onChange={(event) => setForm(mergeField(form as any, 'worker' as any, 'openai_retry_base_seconds' as any, Number(event.target.value)))} /></label>
            </div>
          </WorkspaceSection>
        </> : null}

        {activeTab === 'openedx' ? <>
          <WorkspaceSection title="Máy chủ Open edX" description="Tách rõ CMS, LMS và OAuth host.">
            <div className="settings-form-grid">
              <label className="wide">CMS / Studio URL<input className="input" value={form.openedx.openedx_cms_base_url || form.openedx.openedx_base_url} onChange={(event) => { const value = event.target.value; setForm({ ...form, openedx: { ...form.openedx, openedx_base_url: value, openedx_cms_base_url: value } }) }} /></label>
              <label>LMS URL<input className="input" value={form.openedx.openedx_lms_base_url || ''} onChange={(event) => setForm(mergeField(form, 'openedx', 'openedx_lms_base_url' as any, event.target.value))} /></label>
              <label>OAuth host<input className="input" value={form.openedx.openedx_oauth_base_url || ''} onChange={(event) => setForm(mergeField(form, 'openedx', 'openedx_oauth_base_url' as any, event.target.value))} /></label>
              <label>Client ID<input className="input" value={form.openedx.openedx_client_id || ''} onChange={(event) => setForm(mergeField(form, 'openedx', 'openedx_client_id', event.target.value))} /></label>
              <label>Client Secret<input className="input" type="password" value="" disabled placeholder={settings?.openedx.has_openedx_client_secret ? `Env đã có secret: ${settings?.openedx.openedx_client_secret_masked}` : 'Cấu hình bằng OPENEDX_CLIENT_SECRET'} /></label>
              <label className="wide">Access token tùy chọn<input className="input" type="password" value="" disabled placeholder={settings?.openedx.has_openedx_access_token ? `Env đã có token: ${settings?.openedx.openedx_access_token_masked}` : 'Cấu hình bằng OPENEDX_ACCESS_TOKEN nếu cần'} /></label>
            </div>
          </WorkspaceSection>
          <WorkspaceSection title="Đường dẫn connector" description="Chỉ thay đổi khi plugin hoặc phiên bản Open edX dùng endpoint khác.">
            <div className="settings-form-grid">
              <label>OAuth token path<input className="input" value={form.openedx.openedx_oauth_token_url} onChange={(event) => setForm(mergeField(form, 'openedx', 'openedx_oauth_token_url', event.target.value))} /></label>
              <label>Course Blocks path<input className="input" value={form.openedx.openedx_course_blocks_path} onChange={(event) => setForm(mergeField(form, 'openedx', 'openedx_course_blocks_path', event.target.value))} /></label>
              <label className="wide">Publish endpoint<input className="input" value={form.openedx.openedx_publish_endpoint} onChange={(event) => setForm(mergeField(form, 'openedx', 'openedx_publish_endpoint', event.target.value))} /></label>
              <label className="wide">Library endpoint<input className="input" value={form.openedx.openedx_library_endpoint} onChange={(event) => setForm(mergeField(form, 'openedx', 'openedx_library_endpoint', event.target.value))} /></label>
              <label className="wide">Library import endpoint<input className="input" value={form.openedx.openedx_library_import_endpoint} onChange={(event) => setForm(mergeField(form, 'openedx', 'openedx_library_import_endpoint', event.target.value))} /></label>
            </div>
          </WorkspaceSection>
        </> : null}

        {activeTab === 'auth' ? <WorkspaceSection title="SSO và xác thực" description="Production nên dùng Open edX SSO; demo role header không được bật.">
          <div className="settings-form-grid">
            <label>Auth mode<select className="input" value={form.sso.auth_mode} onChange={(event) => setForm(mergeField(form, 'sso', 'auth_mode', event.target.value))}><option value="openedx_sso">Open edX SSO</option><option value="jwt">JWT</option></select></label>
            <label>JWT secret<input className="input" type="password" value="" disabled placeholder={settings?.sso.has_jwt_secret ? `Env đã có secret: ${settings?.sso.jwt_secret_masked}` : 'Cấu hình bằng JWT_SECRET'} /></label>
            <div className="settings-secret-note wide">Sau khi đổi auth mode, cần xác minh bridge/plugin SSO và rollback plan trước khi áp dụng trên production.</div>
          </div>
        </WorkspaceSection> : null}

        {activeTab === 'cost' ? <WorkspaceSection title="Cost Metering & Pricing" description="Estimate dùng safety factor; actual cost dùng usage thật.">
          <div className="settings-form-grid">
            <label>Input $ / 1M<input className="input" type="number" step="0.001" value={form.cost?.cost_input_price_per_1m ?? 0} onChange={(event) => setForm(mergeField(form, 'cost', 'cost_input_price_per_1m', Number(event.target.value)))} /></label>
            <label>Cached input $ / 1M<input className="input" type="number" step="0.001" value={form.cost?.cost_cached_input_price_per_1m ?? 0} onChange={(event) => setForm(mergeField(form, 'cost', 'cost_cached_input_price_per_1m', Number(event.target.value)))} /></label>
            <label>Output $ / 1M<input className="input" type="number" step="0.001" value={form.cost?.cost_output_price_per_1m ?? 0} onChange={(event) => setForm(mergeField(form, 'cost', 'cost_output_price_per_1m', Number(event.target.value)))} /></label>
            <label>Safety factor<input className="input" type="number" step="0.1" min="1" value={form.cost?.cost_safety_factor ?? 1.5} onChange={(event) => setForm(mergeField(form, 'cost', 'cost_safety_factor', Number(event.target.value)))} /></label>
            <label>USD → VND<input className="input" type="number" step="1" value={form.cost?.usd_to_vnd ?? 26342} onChange={(event) => setForm(mergeField(form, 'cost', 'usd_to_vnd', Number(event.target.value)))} /></label>
          </div>
          {pricing ? <div className="pricing-summary"><div><span>Model</span><b>{pricing.model}</b></div><div><span>Input</span><b>${pricing.input_price_per_1m}/1M</b></div><div><span>Cached</span><b>${pricing.cached_input_price_per_1m}/1M</b></div><div><span>Output</span><b>${pricing.output_price_per_1m}/1M</b></div><div><span>Nguồn</span><b>{pricing.source}</b></div></div> : null}
        </WorkspaceSection> : null}
      </div>
    </section>
  </div>
}
