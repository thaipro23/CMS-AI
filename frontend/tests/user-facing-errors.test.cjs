const assert = require('node:assert/strict')
const { test } = require('node:test')
const { readFileSync } = require('node:fs')
const ts = require('typescript')

// Execute the actual TypeScript modules without adding a browser/test framework.
for (const extension of ['.ts', '.tsx']) {
  require.extensions[extension] = (module, filename) => module._compile(ts.transpileModule(readFileSync(filename, 'utf8'), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020, jsx: ts.JsxEmit.ReactJSX, esModuleInterop: true },
  }).outputText, filename)
}
require.extensions['.css'] = (module) => { module.exports = { __esModule: true, default: new Proxy({}, { get: (_, key) => key }) } }
const { userFacingError, userFacingValidation } = require('../lib/userFacingError.ts')
const { parseResponse, ApiRequestError } = require('../lib/api.ts')
const React = require('react')
const { renderToStaticMarkup } = require('react-dom/server')
const { PersistentJobNotice } = require('../components/ui/PersistentJobNotice.tsx')
const { ActionMessage } = require('../components/ui/ActionMessage.tsx')
const { ContentNotice } = require('../components/ui/ContentNotice.tsx')

test('rich notices keep title, body and lists together beside one decorative icon', () => {
  const markup = renderToStaticMarkup(React.createElement(ContentNotice, { tone: 'success' },
    React.createElement('b', null, 'Đã đưa bộ đề lên CMS.'),
    'Tạo phiên bản mới nếu cần chỉnh sửa.',
    React.createElement('ul', null, React.createElement('li', null, 'Một mục'))))
  assert.equal((markup.match(/<svg/g) || []).length, 1)
  assert.match(markup, /<div class="content"><b>Đã đưa bộ đề lên CMS\.<\/b>Tạo phiên bản mới/)
  assert.match(markup, /role="status"/)
  assert.doesNotMatch(markup, /class="alert/)
})

test('legacy danger tone has an error role and a readable message', () => {
  const markup = renderToStaticMarkup(React.createElement(ContentNotice, { tone: 'danger' }, 'Không đủ câu hỏi. [BANK_OPERATION_FAILED]'))
  assert.match(markup, /role="alert"/)
  assert.match(markup, /Không đủ câu hỏi/)
  assert.doesNotMatch(markup, /BANK_OPERATION_FAILED/)
})

test('preserves a complete actionable difficulty error without its diagnostic suffix', () => {
  const message = 'Không đủ câu hỏi. Cần Dễ: 7, Trung bình: 5, Khó: 3. Hãy điều chỉnh tỷ lệ độ khó.'
  assert.equal(userFacingError(new Error(`${message} [BANK_OPERATION_FAILED]`)), message)
})

test('technical failures and missing errors have useful fallback text', () => {
  for (const raw of ['Traceback (most recent call last): ...', '<html>Bad Gateway</html>', 'TypeError: cannot read properties', undefined]) {
    assert.equal(userFacingError(raw, 'Không tải được danh sách.'), 'Không tải được danh sách.')
  }
  assert.match(userFacingError(new Error('Failed to fetch')), /Không kết nối/)
})

test('validation translates fields, bounds and custom Vietnamese messages', () => {
  assert.equal(userFacingValidation({ loc: ['body', 'total_questions'], type: 'greater_than_equal', ctx: { ge: 1 } }), 'Số câu hỏi: Giá trị phải từ 1 trở lên.')
  assert.equal(userFacingValidation({ loc: ['body', 'campus_name'], type: 'missing', msg: 'Field required' }), 'Tên cơ sở: Cần nhập hoặc chọn giá trị.')
  assert.equal(userFacingValidation({ type: 'value_error', msg: 'Value error, Tổng tỷ lệ độ khó phải bằng 100%.' }), 'Tổng tỷ lệ độ khó phải bằng 100%.')
})

test('API errors retain status, code and request ID outside visible text', async () => {
  await assert.rejects(parseResponse(new Response(JSON.stringify({ error: { code: 'BANK_OPERATION_FAILED', message: 'Chưa đủ câu hỏi.' } }), {
    status: 409, headers: { 'X-Request-ID': 'request-test' },
  })), (error) => error instanceof ApiRequestError && error.message === 'Chưa đủ câu hỏi.' && error.code === 'BANK_OPERATION_FAILED' && error.status === 409 && error.requestId === 'request-test')
})

test('unsupported platform is not mislabeled as an unsupported file', async () => {
  await assert.rejects(parseResponse(new Response(JSON.stringify({ detail: 'Nền tảng chưa được hỗ trợ.' }), { status: 400 })), { message: 'Nền tảng chưa được hỗ trợ.' })
})

test('FastAPI validation renders Vietnamese while preserving structured details', async () => {
  const details = [{ loc: ['body', 'term_name'], type: 'missing', msg: 'Field required' }]
  await assert.rejects(parseResponse(new Response(JSON.stringify({ error: { code: 'VALIDATION_ERROR', message: 'Dữ liệu gửi lên không hợp lệ.', details } }), { status: 422 })), (error) => {
    assert.match(error.message, /Tên học kỳ: Cần nhập/)
    assert.doesNotMatch(error.message, /Field required|term_name/)
    assert.deepEqual(error.details, details)
    return true
  })
})

test('failed background job displays the failure instead of its running description', () => {
  const markup = renderToStaticMarkup(React.createElement(PersistentJobNotice, {
    job: { status: 'failed', error_message: 'Tệp thiếu cột tiến độ.', progress_current: 2, progress_total: 10 },
    title: 'Nhập tiến độ', description: 'Đang nhập dữ liệu.',
  }))
  assert.match(markup, /Tệp thiếu cột tiến độ/)
  assert.doesNotMatch(markup, /Đang nhập dữ liệu/)
  assert.match(markup, /role="alert"/)
})

test('error notice keeps technical detail out of UI; success remains a status', () => {
  const error = renderToStaticMarkup(React.createElement(ActionMessage, { message: { type: 'error', body: 'Hãy chọn học kỳ. [VALIDATION_ERROR]', detail: 'Traceback debug' } }))
  assert.match(error, /Hãy chọn học kỳ/)
  assert.doesNotMatch(error, /Traceback|VALIDATION_ERROR/)
  const success = renderToStaticMarkup(React.createElement(ActionMessage, { message: { type: 'success', body: 'Đã lưu học kỳ.' } }))
  assert.match(success, /role="status"/)
  assert.match(success, /notice-success/)
})
