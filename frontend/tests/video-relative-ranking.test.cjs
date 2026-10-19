const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const Module = require('node:module')
const test = require('node:test')
const ts = require('typescript')
const React = require('react')
const { renderToStaticMarkup } = require('react-dom/server')

const compile = (mod, filename) => mod._compile(ts.transpileModule(fs.readFileSync(filename, 'utf8'), {
  compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX, esModuleInterop: true },
}).outputText, filename)
const originalTS = require.extensions['.ts']
require.extensions['.ts'] = compile
const filename = path.resolve(__dirname, '../components/analytics/MLAnalysisCard.tsx')
const mod = new Module(filename, module)
mod.filename = filename
mod.paths = module.paths
compile(mod, filename)
require.extensions['.ts'] = originalTS
const Card = mod.exports.default
const analysis = { family: 'video', status: 'SCORED', reference_count: 35, confidence: 'LOW',
  primary_method: 'median_mad', comparison_status: 'AGREES', comparison_percentile: 94.,
  reference_percentile: 95., calculated_at: null, reason_codes: [],
  measurement: { observed_playback_rate: 2, measured_videos: 3, pooled_course_count: 2 },
  deviations: [{ feature: 'watch_ratio', value: .2, reference_median: .8, difference: -.6,
    reference_mad: .1, robust_deviation: 4.05 }] }
const render = (changes = {}) => renderToStaticMarkup(React.createElement(Card, { analysis: { ...analysis, ...changes } }))

test('renders neutral relative ranking, low confidence, speed and MAD explanation', () => {
  const html = render()
  assert.match(html, /Điểm xếp hạng tương đối/)
  assert.match(html, /Độ tin cậy thấp/)
  assert.match(html, /Trung vị và MAD/)
  assert.match(html, /2\.00×/)
  assert.match(html, /20\.0%/)
  assert.doesNotMatch(html, /bất thường|gian lận|Khác biệt so với nhóm tham chiếu/i)
})
test('shows comparison percentile only when the methods differ', () => {
  assert.doesNotMatch(render(), /94\.0\/100/)
  assert.match(render({ comparison_status: 'DIFFERS' }), /94\.0\/100/)
})
test('global off hides persisted scores; missing data does not display a rank', () => {
  assert.equal(render({ status: 'DISABLED' }), '')
  assert.doesNotMatch(render({ status: 'INSUFFICIENT_DATA' }), /95\.0\/100/)
})
