const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const vm = require('node:vm')
const test = require('node:test')
const ts = require('typescript')
const React = require('react')
const { renderToStaticMarkup } = require('react-dom/server')

// Execute the real table renderers and their page helpers; no API or grade mocks.
const source = fs.readFileSync(path.join(__dirname, '../app/student-management/classes/[classId]/page.tsx'), 'utf8')
const tree = ts.createSourceFile('page.tsx', source, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX)
const helpers = tree.statements.filter(node => ts.isFunctionDeclaration(node)
  && !node.modifiers?.some(modifier => modifier.kind === ts.SyntaxKind.DefaultKeyword))
const renderers = {}
function visit(node) {
  if (ts.isObjectLiteralExpression(node)) {
    const key = node.properties.find(property => ts.isPropertyAssignment(property) && property.name.getText(tree) === 'key')
    const render = node.properties.find(property => ts.isPropertyAssignment(property) && property.name.getText(tree) === 'render')
    if (key && render && ['progress', 'exam'].includes(key.initializer.text)) renderers[key.initializer.text] = render.initializer.getText(tree)
  }
  ts.forEachChild(node, visit)
}
visit(tree)
assert.deepEqual(Object.keys(renderers).sort(), ['exam', 'progress'])
const code = ts.transpileModule(`${helpers.map(node => node.getText(tree)).join('\n')}
({ progress: ${renderers.progress}, exam: ${renderers.exam} })`, {
  compilerOptions: { target: ts.ScriptTarget.ES2020, module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX },
}).outputText
const columns = vm.runInNewContext(code, { require, exports: {} })
const student = (changes = {}) => ({
  id: 'one', username: 'PH00001', match_status: 'matched', learning_enrollment_status: 'enrolled',
  learning_status: 'low_grade', learning_progress_percent: 100, learning_grade_percent: 80,
  exam_eligible: true, exam_status: 'eligible', exam_status_label: 'Chưa bị cấm thi',
  training_policy: { quiz_total: 8, all_quizzes_eligible: false }, ...changes,
})
const render = (row, column = 'progress') => renderToStaticMarkup(React.createElement(React.Fragment, null, columns[column](row)))

test('100% completion and pre-cutoff permission do not claim all quiz requirements met', () => {
  const html = render(student())
  assert.match(html, /<b>Xem video và Quiz: 100%<\/b>/)
  assert.match(html, /<b[^>]*>Điểm tổng: 8\/10<\/b>/)
  assert.match(html, />Chưa đủ điều kiện thi<\/span>/)
  assert.doesNotMatch(html, />Điểm thấp<|>Đủ điều kiện thi<|Hoàn thành:/)
  assert.match(render(student(), 'exam'), />Chưa đủ điều kiện thi<\/span>/)
})
test('all quiz scores at 100% qualify regardless of total average or completion percentage', () => {
  const row = student({ learning_progress_percent: 98, learning_grade_percent: 90,
    training_policy: { quiz_total: 8, all_quizzes_eligible: true } })
  for (const column of ['progress', 'exam']) {
    const html = render(row, column)
    assert.match(html, /status-pill success/)
    assert.match(html, />Đủ điều kiện thi<\/span>/)
  }
})
test('full score after the final day does not override official rejection or unverified submission', () => {
  for (const exam_status of ['not_eligible', 'insufficient_data']) {
    const row = student({ exam_status, exam_eligible: false,
      exam_reasons: ['Quiz 1 thiếu xác minh ngày nộp'],
      training_policy: { quiz_total: 8, all_quizzes_eligible: true } })
    for (const column of ['progress', 'exam']) {
      assert.match(render(row, column), />Chưa đủ điều kiện thi<\/span>/)
      assert.match(render(row, column), /Quiz 1 thiếu xác minh ngày nộp/)
    }
  }
})
test('missing quiz data, zero quizzes, and missing official decision remain unconfirmed', () => {
  for (const change of [
    { training_policy: undefined },
    { training_policy: { quiz_total: 0, all_quizzes_eligible: true } },
    { training_policy: { quiz_total: 8 } },
    { training_policy: { quiz_total: 8, all_quizzes_eligible: true }, exam_status: undefined },
  ]) {
    assert.match(render(student(change)), />Chưa đủ điều kiện thi<\/span>/)
  }
})
test('missing numeric data stays N/A and the existing CMS sync hint remains available', () => {
  const html = render(student({ learning_progress_percent: null, learning_grade_percent: null,
    match_status: 'not_checked', learning_status: 'not_synced', training_policy: undefined }))
  assert.match(html, /Xem video và Quiz: N\/A/)
  assert.match(html, /Điểm tổng: N\/A/)
  assert.match(html, /Cần đồng bộ full CMS/)
  assert.match(html, /Chưa đủ dữ liệu Quiz/)
})
