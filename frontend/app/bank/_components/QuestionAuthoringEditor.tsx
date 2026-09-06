'use client'

import type { BankQuestionContent, BankQuestionMedia } from '../../../types'
import type { BankQuestionEditForm } from './shared'
import { defaultQuestionContent } from './shared'
import { ContentNotice } from '../../../components/ui/ContentNotice'

export type PendingQuestionImage = { id: string; file: File; altText: string }

const TYPES = [
  ['single_select', 'Một đáp án'],
  ['multi_select', 'Nhiều đáp án'],
  ['dropdown_fill', 'Chọn và điền ô trống'],
  ['text_input', 'Trả lời ngắn'],
  ['numerical_input', 'Trả lời số'],
] as const
const BLANK_RE = /\[_{3,}\]/g
const oid = () => `opt-${Date.now()}-${Math.random().toString(16).slice(2, 8)}`

export function questionFormValidationError(form: BankQuestionEditForm): string | null {
  if (!form.question_text.trim()) return 'Hãy nhập nội dung câu hỏi.'
  const response: any = form.question_content_json?.response
  if (!response || response.type !== form.question_type) return 'Dữ liệu loại câu hỏi chưa đồng bộ.'
  if (['single_select', 'multi_select', 'dropdown_fill'].includes(form.question_type)) {
    const options = Array.isArray(response.options) ? response.options : []
    if (options.length < 2) return 'Câu lựa chọn cần ít nhất 2 đáp án.'
    if (options.some((item: any) => !String(item.text || '').trim())) return 'Không được để trống đáp án.'
    const normalized = options.map((item: any) => String(item.text || '').trim().toLocaleLowerCase('vi'))
    if (new Set(normalized).size !== normalized.length) return 'Các đáp án không được trùng nội dung.'
    if (form.question_type === 'dropdown_fill') {
      const correctIds = Array.isArray(response.correct_option_ids) ? response.correct_option_ids : []
      const blankCount = (form.question_text.match(BLANK_RE) || []).length
      if (!blankCount) return 'Hãy thêm ít nhất một ký hiệu [_____] vào nội dung câu hỏi.'
      if (blankCount !== correctIds.length) return `Có ${blankCount} ô trống nhưng mới cấu hình ${correctIds.length} đáp án theo thứ tự.`
      if (correctIds.some((id: string) => !options.some((item: any) => item.id === id))) return 'Đáp án của ô trống không còn trong danh sách lựa chọn.'
    } else {
      const correctCount = options.filter((item: any) => item.correct).length
      if (form.question_type === 'single_select' && correctCount !== 1) return 'Câu một đáp án phải có đúng 1 đáp án đúng.'
      if (form.question_type === 'multi_select' && correctCount < 2) return 'Câu nhiều đáp án phải có ít nhất 2 đáp án đúng.'
      if (form.question_type === 'multi_select' && correctCount === options.length) return 'Cần có ít nhất 1 đáp án sai.'
    }
  } else if (form.question_type === 'text_input') {
    const answers = Array.isArray(response.accepted_answers) ? response.accepted_answers : []
    if (!answers.length || answers.some((item: any) => !String(item.text || '').trim())) return 'Hãy nhập ít nhất 1 đáp án text.'
  } else {
    if (!String(response.answer ?? '').trim() || Number.isNaN(Number(response.answer))) return 'Đáp án số không hợp lệ.'
    if (Number.isNaN(Number(response.tolerance)) || Number(response.tolerance) < 0) return 'Sai số cho phép không hợp lệ.'
  }
  return null
}

export function QuestionAuthoringEditor({
  form,
  onChange,
  existingMedia = [],
  pendingMedia,
  onPendingMediaChange,
  mediaUrl,
  onDeleteMedia,
  disabled,
  showReviewStatus = true,
}: {
  form: BankQuestionEditForm
  onChange: (form: BankQuestionEditForm) => void
  existingMedia?: BankQuestionMedia[]
  pendingMedia: PendingQuestionImage[]
  onPendingMediaChange: (value: PendingQuestionImage[]) => void
  mediaUrl?: (media: BankQuestionMedia) => string
  onDeleteMedia?: (media: BankQuestionMedia) => void
  disabled?: boolean
  showReviewStatus?: boolean
}) {
  const response: any = form.question_content_json.response
  const options: any[] = Array.isArray(response.options) ? response.options : []
  const setResponse = (nextResponse: any) => onChange({
    ...form,
    question_content_json: { schema_version: 2, response: nextResponse } as BankQuestionContent,
  })
  const addBlank = () => onChange({
    ...form,
    question_text: `${form.question_text}${form.question_text.trim() ? ' ' : ''}[_____]`,
    question_content_json: {
      schema_version: 2,
      response: {
        ...response,
        correct_option_ids: [...(response.correct_option_ids || []), options[0]?.id].filter(Boolean),
      },
    } as BankQuestionContent,
  })
  const removeLastBlank = () => {
    const matches = Array.from(form.question_text.matchAll(BLANK_RE))
    const last = matches[matches.length - 1]
    if (!last || last.index === undefined) return
    onChange({
      ...form,
      question_text: `${form.question_text.slice(0, last.index)}${form.question_text.slice(last.index + last[0].length)}`.trim(),
      question_content_json: {
        schema_version: 2,
        response: { ...response, correct_option_ids: (response.correct_option_ids || []).slice(0, -1) },
      } as BankQuestionContent,
    })
  }
  const deleteChoice = (index: number) => {
    const removedId = options[index]?.id
    const nextOptions = options.filter((_, itemIndex) => itemIndex !== index)
    if (form.question_type !== 'dropdown_fill') {
      setResponse({ ...response, options: nextOptions })
      return
    }
    const fallbackId = nextOptions[0]?.id
    const nextCorrectIds = (response.correct_option_ids || []).map((id: string) => id === removedId ? fallbackId : id).filter(Boolean)
    setResponse({ ...response, options: nextOptions, correct_option_ids: nextCorrectIds })
  }

  return <div className="bank-question-edit-form question-authoring-editor">
    <div className="question-type-picker">
      {TYPES.map(([value, label]) => <button
        type="button"
        key={value}
        disabled={disabled}
        className={`question-type-card ${form.question_type === value ? 'selected' : ''}`}
        onClick={() => onChange({ ...form, question_type: value, question_content_json: defaultQuestionContent(value) })}
      ><b>{label}</b></button>)}
    </div>

    <div className="grid grid-3">
      <label>Độ khó<select className="input" disabled={disabled} value={form.difficulty} onChange={(event) => onChange({ ...form, difficulty: event.target.value })}><option value="easy">Dễ</option><option value="medium">Trung bình</option><option value="hard">Khó</option></select></label>
      <label>Mức nhận thức<select className="input" disabled={disabled} value={form.cognitive_level} onChange={(event) => onChange({ ...form, cognitive_level: event.target.value })}><option value="remember">Ghi nhớ</option><option value="understand">Hiểu</option><option value="recognize_example">Nhận diện ví dụ</option><option value="simple_apply">Áp dụng</option></select></label>
      {showReviewStatus
        ? <label>Trạng thái<select className="input" disabled={disabled} value={form.target_status} onChange={(event) => onChange({ ...form, target_status: event.target.value })}><option value="pending_review">Chờ duyệt</option><option value="approved">Đã duyệt</option><option value="rejected">Đã bỏ</option></select></label>
        : <label>Trạng thái<input className="input" disabled value="Chờ duyệt" /></label>}
    </div>
    <label>Mục tiêu học tập<input className="input" disabled={disabled} value={form.learning_objective} onChange={(event) => onChange({ ...form, learning_objective: event.target.value })} /></label>
    <label>Câu hỏi<textarea className="input" rows={3} disabled={disabled} value={form.question_text} onChange={(event) => onChange({ ...form, question_text: event.target.value })} /></label>

    {form.question_type === 'dropdown_fill' ? <div className="dropdown-blank-toolbar">
      <span>Dùng <code>[_____]</code> tại mỗi vị trí cần chọn đáp án.</span>
      <div><button className="btn secondary small" type="button" disabled={disabled || (response.correct_option_ids || []).length >= 10} onClick={addBlank}>+ Ô trống</button><button className="btn secondary small" type="button" disabled={disabled || !(response.correct_option_ids || []).length} onClick={removeLastBlank}>Xóa ô cuối</button></div>
    </div> : null}

    {['single_select', 'multi_select', 'dropdown_fill'].includes(form.question_type) ? <div>
      <div className="section-head compact-section-head"><h3>Danh sách lựa chọn</h3><button className="btn secondary small" type="button" disabled={disabled || options.length >= 12} onClick={() => setResponse({ ...response, options: [...options, { id: oid(), text: '', correct: false, feedback: '' }] })}>+ Đáp án</button></div>
      {options.map((option: any, index: number) => <div className="question-option-editor" key={option.id || index}>
        {form.question_type === 'dropdown_fill'
          ? <span className="dropdown-choice-index">{String.fromCharCode(65 + index)}</span>
          : <input type={form.question_type === 'single_select' ? 'radio' : 'checkbox'} name={form.question_type === 'single_select' ? 'correct-option' : undefined} checked={Boolean(option.correct)} disabled={disabled} onChange={(event) => setResponse({ ...response, options: options.map((item: any, itemIndex: number) => ({ ...item, correct: form.question_type === 'single_select' ? itemIndex === index : (itemIndex === index ? event.target.checked : item.correct) })) })} />}
        <span>{index + 1}</span>
        <input className="input" disabled={disabled} value={option.text || ''} placeholder={`Đáp án ${index + 1}`} onChange={(event) => setResponse({ ...response, options: options.map((item: any, itemIndex: number) => itemIndex === index ? { ...item, text: event.target.value } : item) })} />
        <input className="input" disabled={disabled} value={option.feedback || ''} placeholder="Feedback (tùy chọn)" onChange={(event) => setResponse({ ...response, options: options.map((item: any, itemIndex: number) => itemIndex === index ? { ...item, feedback: event.target.value } : item) })} />
        <button className="icon-button danger" type="button" disabled={disabled || options.length <= 2} onClick={() => deleteChoice(index)}>×</button>
      </div>)}
    </div> : null}

    {form.question_type === 'dropdown_fill' ? <div className="dropdown-blank-order">
      <div className="section-head compact-section-head"><h3>Đáp án đúng theo thứ tự ô trống</h3><span>{(response.correct_option_ids || []).length} ô</span></div>
      {(response.correct_option_ids || []).map((correctId: string, index: number) => <label key={`${index}-${correctId}`}><span>Ô {index + 1}</span><select className="input" disabled={disabled} value={correctId} onChange={(event) => setResponse({ ...response, correct_option_ids: response.correct_option_ids.map((id: string, itemIndex: number) => itemIndex === index ? event.target.value : id) })}>{options.map((option: any, optionIndex: number) => <option value={option.id} key={option.id}>{String.fromCharCode(65 + optionIndex)}. {option.text || `Đáp án ${optionIndex + 1}`}</option>)}</select></label>)}
    </div> : null}

    {form.question_type === 'text_input' ? <div>
      <label className="checkbox-line"><input type="checkbox" disabled={disabled} checked={Boolean(response.case_sensitive)} onChange={(event) => setResponse({ ...response, case_sensitive: event.target.checked, accepted_answers: response.accepted_answers.map((item: any) => ({ ...item, case_sensitive: event.target.checked })) })} />Phân biệt hoa/thường</label>
      {response.accepted_answers.map((answer: any, index: number) => <div className="question-option-editor text-answer" key={index}><span>{index + 1}</span><input className="input" disabled={disabled} value={answer.text || ''} onChange={(event) => setResponse({ ...response, accepted_answers: response.accepted_answers.map((item: any, itemIndex: number) => itemIndex === index ? { ...item, text: event.target.value } : item) })} /><button className="icon-button danger" type="button" disabled={disabled || response.accepted_answers.length <= 1} onClick={() => setResponse({ ...response, accepted_answers: response.accepted_answers.filter((_: any, itemIndex: number) => itemIndex !== index) })}>×</button></div>)}
      <button className="btn secondary small" type="button" disabled={disabled || response.accepted_answers.length >= 20} onClick={() => setResponse({ ...response, accepted_answers: [...response.accepted_answers, { text: '', case_sensitive: Boolean(response.case_sensitive) }] })}>+ Đáp án chấp nhận</button>
    </div> : null}
    {form.question_type === 'numerical_input' ? <div className="grid grid-3"><label>Đáp án số<input className="input" disabled={disabled} value={response.answer ?? ''} onChange={(event) => setResponse({ ...response, answer: event.target.value })} /></label><label>Sai số<input className="input" disabled={disabled} value={response.tolerance ?? '0'} onChange={(event) => setResponse({ ...response, tolerance: event.target.value })} /></label><label>Loại<select className="input" disabled={disabled} value={response.tolerance_type || 'absolute'} onChange={(event) => setResponse({ ...response, tolerance_type: event.target.value })}><option value="absolute">Tuyệt đối</option><option value="percent">%</option></select></label></div> : null}

    <div className="question-media-section"><h3>Ảnh trong câu hỏi</h3><p className="helper">Ảnh độc lập với kiểu trả lời. PNG/JPEG/WebP, tối đa 4 MB/ảnh; alt text bắt buộc.</p>{existingMedia.map((media) => <figure key={media.id}>{mediaUrl ? <img src={mediaUrl(media)} alt={media.alt_text} /> : null}<figcaption>{media.alt_text}</figcaption>{onDeleteMedia ? <button className="btn danger small" type="button" disabled={disabled} onClick={() => onDeleteMedia(media)}>Xóa</button> : null}</figure>)}{pendingMedia.map((item) => <div className="question-pending-media" key={item.id}><span>{item.file.name}</span><input className="input" disabled={disabled} value={item.altText} placeholder="Alt text (bắt buộc)" onChange={(event) => onPendingMediaChange(pendingMedia.map((candidate) => candidate.id === item.id ? { ...candidate, altText: event.target.value } : candidate))} /><button className="icon-button danger" type="button" onClick={() => onPendingMediaChange(pendingMedia.filter((candidate) => candidate.id !== item.id))}>×</button></div>)}<label className="btn secondary file-button">+ Thêm ảnh<input hidden type="file" accept="image/png,image/jpeg,image/webp" disabled={disabled || existingMedia.length + pendingMedia.length >= 4} onChange={(event) => { const file = event.target.files?.[0]; if (file) onPendingMediaChange([...pendingMedia, { id: `${Date.now()}-${file.name}`, file, altText: '' }]); event.currentTarget.value = '' }} /></label></div>
    <div className="grid grid-3"><label>Concept<input className="input" disabled={disabled} value={form.concept_title} onChange={(event) => onChange({ ...form, concept_title: event.target.value })} /></label><label>Family<input className="input" disabled={disabled} value={form.question_family_id} onChange={(event) => onChange({ ...form, question_family_id: event.target.value })} /></label><label>Nguồn<input className="input" disabled={disabled} value={form.source_ref} onChange={(event) => onChange({ ...form, source_ref: event.target.value })} /></label></div>
    <label>Giải thích<textarea className="input" rows={2} disabled={disabled} value={form.explanation} onChange={(event) => onChange({ ...form, explanation: event.target.value })} /></label>
    {questionFormValidationError(form) ? <ContentNotice tone="warning">{questionFormValidationError(form)}</ContentNotice> : <ContentNotice tone="success">Dữ liệu câu hỏi hợp lệ.</ContentNotice>}
  </div>
}

export function QuestionResponsePreview({
  questionType,
  content,
  legacyOptions,
  legacyCorrectAnswer,
  media = [],
  mediaUrl,
}: {
  questionType?: string | null
  content?: BankQuestionContent | null
  legacyOptions?: string[]
  legacyCorrectAnswer?: string | null
  media?: BankQuestionMedia[]
  mediaUrl?: (media: BankQuestionMedia) => string
}) {
  const type = questionType === 'single_choice' ? 'single_select' : (questionType || content?.response?.type || 'single_select')
  let response: any = content?.response
  if (!response || response.type !== type) {
    const values = legacyOptions || []
    const correct = String(legacyCorrectAnswer || 'A').toUpperCase()
    response = { type: 'single_select', options: values.map((text, index) => ({ id: `legacy-preview-${index}`, text, correct: correct === String.fromCharCode(65 + index), feedback: '' })) }
  }
  const optionById = new Map<string, any>((response.options || []).map((option: any) => [option.id, option]))
  return <div className="question-response-preview">
    {media.length ? <div className="question-media-grid preview-media-grid">{media.map((item) => <figure key={item.id}>{mediaUrl ? <img src={mediaUrl(item)} alt={item.alt_text} /> : null}<figcaption>{item.alt_text}</figcaption></figure>)}</div> : null}
    {(type === 'single_select' || type === 'multi_select') ? <div className="answer-grid review-answer-grid">{(response.options || []).map((option: any, index: number) => <div key={option.id || index} className={option.correct ? 'answer-option correct' : 'answer-option'}><span className="answer-letter">{String.fromCharCode(65 + index)}</span><span>{option.text || '—'}</span>{option.correct ? <small>Đúng</small> : null}</div>)}</div> : null}
    {type === 'dropdown_fill' ? <div className="dropdown-fill-preview"><b>Đáp án theo thứ tự ô trống</b>{(response.correct_option_ids || []).map((id: string, index: number) => <div key={`${index}-${id}`}><span>Ô {index + 1}</span><strong>{optionById.get(id)?.text || '—'}</strong></div>)}</div> : null}
    {type === 'text_input' ? <div className="accepted-answer-preview"><b>Đáp án chấp nhận</b>{(response.accepted_answers || []).map((answer: any, index: number) => <span className="soft-tag" key={`${answer.text}-${index}`}>{answer.text || '—'}</span>)}<small>{response.case_sensitive ? 'Phân biệt hoa/thường' : 'Không phân biệt hoa/thường'}</small></div> : null}
    {type === 'numerical_input' ? <div className="numerical-answer-preview"><div><span>Đáp án số</span><b>{String(response.answer ?? '—')}</b></div><div><span>Sai số</span><b>{String(response.tolerance ?? '0')}{response.tolerance_type === 'percent' ? '%' : ''}</b></div></div> : null}
  </div>
}
