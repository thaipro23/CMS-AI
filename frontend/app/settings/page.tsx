'use client'

import { useEffect, useState } from 'react'
import { getRuntimeSettings, updateRuntimeSettings, testModelGateway, getRealtimePricing, testOpenEdxConnection } from '../../lib/api'
import { useAppContext } from '../../context/AppContext'
import { ROLE_LABELS, ROLE_PERMISSIONS, RuntimeSettings, RuntimeSettingsUpdate, PricingResponse } from '../../types'
import { ActionMessage, ActionMessageData, toUserError } from '../../components/ui/ActionMessage'
import { LoadingButton } from '../../components/ui/LoadingButton'
import { CoursePolicyPanel } from '../../components/settings/CoursePolicyPanel'

const defaultForm: RuntimeSettingsUpdate = {
  model: {
    model_provider: 'openai',
    openai_model: 'gpt-5-mini',
    openai_api_mode: 'responses',
    mock_llm: true,
    openai_api_key: '',
  },
  openedx: {
    use_mock_openedx: true,
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
    auth_mode: 'demo',
    allow_demo_role_header: true,
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
      auth_mode: settings.sso.auth_mode || 'demo',
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
  const [testing, setTesting] = useState(false)
  const [pricingLoading, setPricingLoading] = useState(false)

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

  async function testModel() {
    setTesting(true)
    setTestMessage(null)
    try {
      const data = await testModelGateway(authHeaders(true))
      setTestMessage({ type: 'success', title: 'Kiểm tra GPT thành công', body: `Đang gọi ${data.provider}/${data.model}${data.api_mode ? ` qua ${data.api_mode}` : ''}. Input ${data.input_tokens}, cached ${data.cached_input_tokens || 0}, output ${data.output_tokens}.`, detail: data.first_question ? `Câu test: ${data.first_question}` : undefined })
      await load()
    } catch (e) {
      setTestMessage(toUserError(e))
    } finally {
      setTesting(false)
    }
  }

  async function testOpenEdx() {
    setTesting(true)
    setTestMessage(null)
    try {
      const data: any = await testOpenEdxConnection(courseId, authHeaders(true))
      setTestMessage({ type: data?.ok === false ? 'warning' : 'success', title: 'Kiểm tra Open edX hoàn tất', body: data?.message || data?.status || 'Đã kiểm tra kết nối Open edX.', detail: data?.base_url ? `Base URL: ${data.base_url}` : undefined })
    } catch (e) {
      setTestMessage(toUserError(e))
    } finally {
      setTesting(false)
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
        <p className="helper">Role hiện tại là <b>{role}</b>. Backend cũng chặn bằng quyền <b>manage_settings</b>, nên teacher/reviewer/viewer không đọc hoặc sửa được API key, model, mock mode và SSO.</p>
      </section>
      <section className="card">
        <h2>RBAC hiện tại</h2>
        <div className="role-box large"><b>{ROLE_LABELS[role]}</b><small>{ROLE_PERMISSIONS[role].join(', ')}</small></div>
      </section>
    </div>
  }

  return <div className="page-stack">
    <section className="card page-intro">
      <div>
        <div className="eyebrow">Cấu hình quản trị</div>
        <h2>Cấu hình AI, Open edX connector và SSO</h2>
        <p className="helper">Chỉ admin được vào trang này. Secret/API key được mask khi đọc; để trống ô secret nếu muốn giữ giá trị cũ.</p>
      </div>
      <div className="button-row"><LoadingButton className="btn ghost" onClick={load}>Tải lại</LoadingButton><LoadingButton className="btn ghost" loading={testing} onClick={testModel}>Kiểm tra GPT</LoadingButton><LoadingButton className="btn ghost" loading={testing} onClick={testOpenEdx}>Kiểm tra Open edX</LoadingButton><LoadingButton className="btn ghost" loading={pricingLoading} onClick={fetchPricing}>Lấy giá</LoadingButton><LoadingButton className="btn" loading={saving} onClick={save}>Lưu cấu hình</LoadingButton></div>
    </section>

    <ActionMessage message={message} onClose={() => setMessage(null)} />
    <ActionMessage message={testMessage} onClose={() => setTestMessage(null)} />

    <CoursePolicyPanel courseId="__bank_chapter_default__" headers={authHeaders()} writeHeaders={authHeaders(true)} canEdit={can('manage_settings')} />


    <section className="grid grid-2">
      <div className="card">
        <div className="section-head"><div><h2>Cổng mô hình</h2><p className="helper">Điều khiển GPT thật hoặc mock LLM cho demo.</p></div></div>
        <div className="form-stack">
          <div><label>Nhà cung cấp mô hình</label><select className="input" value={form.model.model_provider} onChange={(e) => setForm(mergeField(form, 'model', 'model_provider', e.target.value))}><option value="openai">openai</option><option value="local">local</option><option value="auto">auto</option></select></div>
          <div><label>Tên mô hình</label><input className="input" value={form.model.openai_model} onChange={(e) => setForm(mergeField(form, 'model', 'openai_model', e.target.value))} placeholder="gpt-5-mini" /></div>
          <div><label>Chế độ OpenAI API</label><select className="input" value={form.model.openai_api_mode} onChange={(e) => setForm(mergeField(form, 'model', 'openai_api_mode', e.target.value))}><option value="responses">responses - mặc định GPT-5 mini</option><option value="chat_legacy">chat_legacy - fallback cũ</option></select></div>
          <label className="check-row"><input type="checkbox" checked={form.model.mock_llm} onChange={(e) => setForm(mergeField(form, 'model', 'mock_llm', e.target.checked))} /> Bật MOCK_LLM</label>
          <div><label>Khóa OpenAI API</label><input className="input" type="password" value="" disabled placeholder={settings?.model.has_openai_api_key ? `Env đã có key: ${settings?.model.openai_api_key_masked}` : 'Cấu hình bằng OPENAI_API_KEY trong env'} /></div>
          <p className="helper">Muốn gọi GPT thật: đặt OPENAI_API_KEY trong env, tắt MOCK_LLM, model giữ <b>gpt-5-mini</b>, API mode để <b>responses</b>. Chỉ đổi sang chat_legacy nếu cần fallback cho gateway cũ/local compatible.</p>
        </div>
      </div>

      <div className="card">
        <div className="section-head"><div><h2>Kết nối Open edX</h2><p className="helper">Bật/tắt mock Open edX và cấu hình OAuth/API bridge.</p></div></div>
        <div className="form-stack">
          <label className="check-row"><input type="checkbox" checked={form.openedx.use_mock_openedx} onChange={(e) => setForm(mergeField(form, 'openedx', 'use_mock_openedx', e.target.checked))} /> Dùng mock Open edX</label>
          <div><label>URL Open edX CMS/Studio</label><input className="input" value={form.openedx.openedx_cms_base_url || form.openedx.openedx_base_url} onChange={(e) => { const value = e.target.value; setForm({ ...form, openedx: { ...form.openedx, openedx_base_url: value, openedx_cms_base_url: value } }) }} placeholder="http://studio.local.openedx.io" /><p className="helper">Dùng cho connector Studio: sync draft content, handout, publish Library/Problem.</p></div>
          <div><label>URL Open edX LMS</label><input className="input" value={form.openedx.openedx_lms_base_url || ''} onChange={(e) => setForm(mergeField(form, 'openedx', 'openedx_lms_base_url' as any, e.target.value))} placeholder="http://local.openedx.io" /><p className="helper">Dùng cho OAuth/token và Course Blocks fallback trong Tutor.</p></div>
          <div><label>URL OAuth token host</label><input className="input" value={form.openedx.openedx_oauth_base_url || ''} onChange={(e) => setForm(mergeField(form, 'openedx', 'openedx_oauth_base_url' as any, e.target.value))} placeholder="http://local.openedx.io" /><p className="helper">Tutor thường có /oauth2/access_token/ ở LMS, không phải Studio.</p></div>
          <div><label>Client ID</label><input className="input" value={form.openedx.openedx_client_id || ''} onChange={(e) => setForm(mergeField(form, 'openedx', 'openedx_client_id', e.target.value))} /></div>
          <div><label>Client Secret</label><input className="input" type="password" value="" disabled placeholder={settings?.openedx.has_openedx_client_secret ? `Env đã có secret: ${settings?.openedx.openedx_client_secret_masked}` : 'Cấu hình bằng OPENEDX_CLIENT_SECRET trong env'} /></div>
          <div><label>Access token tùy chọn</label><input className="input" type="password" value="" disabled placeholder={settings?.openedx.has_openedx_access_token ? `Env đã có token: ${settings?.openedx.openedx_access_token_masked}` : 'Cấu hình bằng OPENEDX_ACCESS_TOKEN trong env nếu cần'} /></div>
        </div>
      </div>
    </section>

    <section className="card">
      <div className="section-head"><div><h2>GPT Parallel / Cache Scheduler</h2><p className="helper">Tăng tốc bằng controlled parallelism, nhưng vẫn warm-up prefix trước để tối đa cached input. Tail giữ riêng EASY/MEDIUM/HARD, không gom mixed prompt.</p></div></div>
      <div className="grid grid-3">
        <label className="check-row"><input type="checkbox" checked={form.worker?.openai_parallel_enabled ?? true} onChange={(e) => setForm(mergeField(form as any, 'worker' as any, 'openai_parallel_enabled' as any, e.target.checked))} /> Bật gọi GPT song song</label>
        <label className="check-row"><input type="checkbox" checked={form.worker?.openai_prompt_cache_warmup_enabled ?? true} onChange={(e) => setForm(mergeField(form as any, 'worker' as any, 'openai_prompt_cache_warmup_enabled' as any, e.target.checked))} /> Warm-up prompt cache trước khi chạy song song</label>
        <label className="check-row"><input type="checkbox" checked={form.worker?.generation_tail_batch_wait_enabled ?? true} onChange={(e) => setForm(mergeField(form as any, 'worker' as any, 'generation_tail_batch_wait_enabled' as any, e.target.checked))} /> Tail đợi primary và bù thiếu theo difficulty</label>
        <div><label>Số cuộc gọi GPT song song tối đa</label><input className="input" type="number" min="1" max="8" value={form.worker?.openai_max_parallel_calls ?? 3} onChange={(e) => setForm(mergeField(form as any, 'worker' as any, 'openai_max_parallel_calls' as any, Number(e.target.value)))} /></div>
        <div><label>Số lần thử lại</label><input className="input" type="number" min="1" max="8" value={form.worker?.openai_retry_max_attempts ?? 3} onChange={(e) => setForm(mergeField(form as any, 'worker' as any, 'openai_retry_max_attempts' as any, Number(e.target.value)))} /></div>
        <div><label>Số giây chờ khi retry</label><input className="input" type="number" min="0.1" step="0.5" value={form.worker?.openai_retry_base_seconds ?? 2} onChange={(e) => setForm(mergeField(form as any, 'worker' as any, 'openai_retry_base_seconds' as any, Number(e.target.value)))} /></div>
      </div>
      <p className="helper">Gợi ý production: giữ warm-up bật. Ví dụ 50 câu 50/30/20: primary chạy EASY 12 + EASY 12 + MEDIUM 12 + HARD 10; tail sẽ là EASY riêng và MEDIUM riêng nếu có phần lẻ hoặc phần thiếu.</p>
    </section>

    <section className="grid grid-2">
      <div className="card">
        <div className="section-head"><div><h2>Open edX endpoints</h2><p className="helper">Đường dẫn API có thể khác theo bản Open edX/Tutor/plugin.</p></div></div>
        <div className="form-stack">
          <div><label>OAuth token URL</label><input className="input" value={form.openedx.openedx_oauth_token_url} onChange={(e) => setForm(mergeField(form, 'openedx', 'openedx_oauth_token_url', e.target.value))} /></div>
          <div><label>Course Blocks API path</label><input className="input" value={form.openedx.openedx_course_blocks_path} onChange={(e) => setForm(mergeField(form, 'openedx', 'openedx_course_blocks_path', e.target.value))} /></div>
          <div><label>Legacy publish endpoint</label><input className="input" value={form.openedx.openedx_publish_endpoint} onChange={(e) => setForm(mergeField(form, 'openedx', 'openedx_publish_endpoint', e.target.value))} /></div>
          <div><label>Chapter Library endpoint</label><input className="input" value={form.openedx.openedx_library_endpoint} onChange={(e) => setForm(mergeField(form, 'openedx', 'openedx_library_endpoint', e.target.value))} /></div>
          <div><label>Import to Library endpoint</label><input className="input" value={form.openedx.openedx_library_import_endpoint} onChange={(e) => setForm(mergeField(form, 'openedx', 'openedx_library_import_endpoint', e.target.value))} /></div>
        </div>
      </div>

      <div className="card">
        <div className="section-head"><div><h2>SSO / phân quyền</h2><p className="helper">Production dùng JWT hoặc Open edX SSO/plugin proxy. UI không còn chỉnh role demo.</p></div></div>
        <div className="form-stack">
          <div><label>Auth mode</label><select className="input" value={form.sso.auth_mode} onChange={(e) => setForm(mergeField(form, 'sso', 'auth_mode', e.target.value))}><option value="demo">demo</option><option value="jwt">jwt</option><option value="openedx_sso">openedx_sso</option></select></div>
          <div><label>JWT secret</label><input className="input" type="password" value="" disabled placeholder={settings?.sso.has_jwt_secret ? `Env đã có secret: ${settings?.sso.jwt_secret_masked}` : 'Cấu hình bằng JWT_SECRET trong env'} /></div>
          <p className="helper">Secret không lưu runtime JSON. Khi chuyển sang openedx_sso cần bảo đảm verifier/plugin SSO đã hoạt động, nếu không API sẽ trả 401.</p>
        </div>
      </div>
    </section>

    <section className="card">
      <div className="section-head"><div><h2>Cost Metering / Pricing</h2><p className="helper">Estimate dùng input token endpoint + safety_factor. Actual cost dùng usage thật và không nhân safety_factor.</p></div><LoadingButton className="btn ghost" loading={pricingLoading} onClick={fetchPricing}>Lấy giá realtime</LoadingButton></div>
      <div className="grid grid-3">
        <div><label>Input $ / 1M</label><input className="input" type="number" step="0.001" value={form.cost?.cost_input_price_per_1m ?? 0} onChange={(e) => setForm(mergeField(form, 'cost', 'cost_input_price_per_1m', Number(e.target.value)))} /></div>
        <div><label>Đã cache input $ / 1M</label><input className="input" type="number" step="0.001" value={form.cost?.cost_cached_input_price_per_1m ?? 0} onChange={(e) => setForm(mergeField(form, 'cost', 'cost_cached_input_price_per_1m', Number(e.target.value)))} /></div>
        <div><label>Output $ / 1M</label><input className="input" type="number" step="0.001" value={form.cost?.cost_output_price_per_1m ?? 0} onChange={(e) => setForm(mergeField(form, 'cost', 'cost_output_price_per_1m', Number(e.target.value)))} /></div>
        <div><label>Safety factor</label><input className="input" type="number" step="0.1" min="1" value={form.cost?.cost_safety_factor ?? 1.5} onChange={(e) => setForm(mergeField(form, 'cost', 'cost_safety_factor', Number(e.target.value)))} /></div>
        <div><label>USD to VND</label><input className="input" type="number" step="1" value={form.cost?.usd_to_vnd ?? 26342} onChange={(e) => setForm(mergeField(form, 'cost', 'usd_to_vnd', Number(e.target.value)))} /></div>
      </div>
      {pricing && <div className="pricing-summary"><div><span>Model</span><b>{pricing.model}</b></div><div><span>Input</span><b>${pricing.input_price_per_1m}/1M</b></div><div><span>Cached</span><b>${pricing.cached_input_price_per_1m}/1M</b></div><div><span>Output</span><b>${pricing.output_price_per_1m}/1M</b></div><div><span>Nguồn</span><b>{pricing.source}</b></div></div>}
      <p className="helper">API realtime: <code>GET /api/cost/pricing/realtime?model={form.model.openai_model}&refresh=true</code>. Nếu không lấy được giá realtime hoặc model không có trên pricing page, backend dùng fallback/settings.</p>
    </section>

    <section className="card">
      <h2>Runtime file</h2>
      <p className="helper">Cấu hình demo được lưu trong file runtime dùng chung backend/worker: <code>{settings?.runtime_config_path || '/tmp/ai-openedx-runtime-settings.json'}</code>. Production vẫn nên cấu hình qua biến môi trường/secret manager.</p>
    </section>
  </div>
}
