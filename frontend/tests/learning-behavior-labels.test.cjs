const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const vm = require('node:vm')
const test = require('node:test')
const ts = require('typescript')

const source = fs.readFileSync(path.join(__dirname, '../lib/learning-behavior-labels.ts'), 'utf8')
const output = ts.transpileModule(source, {compilerOptions: {target: ts.ScriptTarget.ES2020, module: ts.ModuleKind.CommonJS}}).outputText
const context = {exports: {}}
vm.runInNewContext(output, context)
const {learningReasonText, learningReasonTexts, learningScoreText, watchDurationText} = context.exports

for (const [code, label] of Object.entries({
  LARGE_SEEK_JUMP: 'Tua video qua một đoạn dài',
  HIGH_COMPLETION_LOW_WATCH_TIME: 'Video gần hoàn thành nhưng thời gian xem rất ít',
  MANY_VIDEOS_COMPLETED_TOO_FAST: 'Nhiều video hoàn thành quá nhanh so với thời lượng',
  QUIZ_BEFORE_VIDEO: 'Làm Quiz trước khi xem video',
  DEADLINE_PATTERN_MATCHED: 'Hoạt động học khớp mốc thời hạn',
  WATCH_THEN_ATTEMPT_PROBLEM: 'Có xem video trước khi làm Quiz',
  REPEATED_HIGH_COMPLETION_LOW_WATCH: 'Lặp lại việc hoàn thành video với thời gian xem rất ít',
})) {
  test(`displays ${code} as a readable reason`, () => assert.equal(learningReasonText(code), label))
}
test('neutral deadline and video-before-quiz reasons are not called violations or late work', () => {
  for (const code of ['DEADLINE_PATTERN_MATCHED', 'WATCH_THEN_ATTEMPT_PROBLEM']) {
    assert.doesNotMatch(learningReasonText(code), /bất thường|vi phạm|sau hạn|trễ|muộn/)
  }
})
test('missing timing and obsolete rules explain the data limit', () => {
  assert.match(learningReasonText('MISSING_WATCH_TIMING'), /Thiếu mốc thời gian/)
  assert.match(learningReasonText('BEHAVIOR_RULES_UPDATED'), /tính lại/)
})
test('blank and future codes never leak technical snake-case labels', () => {
  assert.equal(learningReasonText(null), '')
  assert.equal(learningReasonText(''), '')
  assert.equal(learningReasonText('NEW_UNKNOWN_CODE'), 'Dấu hiệu khác cần đối chiếu thêm')
  assert.equal(learningReasonText(' large_seek_jump '), learningReasonText('LARGE_SEEK_JUMP'))
})
test('keeps all seven reasons, without duplicates', () => {
  const codes = ['LARGE_SEEK_JUMP', 'HIGH_COMPLETION_LOW_WATCH_TIME', 'MANY_VIDEOS_COMPLETED_TOO_FAST',
    'QUIZ_BEFORE_VIDEO', 'DEADLINE_PATTERN_MATCHED', 'WATCH_THEN_ATTEMPT_PROBLEM', 'REPEATED_HIGH_COMPLETION_LOW_WATCH']
  const labels = learningReasonTexts([...codes, codes[0]])
  assert.equal(labels.length, 7)
  assert.equal(new Set(labels).size, 7)
})
test('scores are points and missing is distinct from zero', () => {
  assert.equal(learningScoreText(0), '0/100')
  assert.equal(learningScoreText(35), '35/100')
  assert.equal(learningScoreText(null), 'Chưa có dữ liệu')
})
test('watch display distinguishes short viewing from an unknown duration', () => {
  assert.equal(watchDurationText(12), '12 giây')
  assert.equal(watchDurationText(0), '0 giây')
  assert.equal(watchDurationText(null), 'Chưa có dữ liệu')
  assert.equal(watchDurationText(90), '1 phút 30 giây')
})
