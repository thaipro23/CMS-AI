const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const vm = require('node:vm')
const test = require('node:test')
const ts = require('typescript')

// Exercise the page's real quota/button calculations with API-shaped stats.
const source = fs.readFileSync(path.join(__dirname, '../app/bank/_components/pages/ChapterWorkspacePage.tsx'), 'utf8')
const tree = ts.createSourceFile('page.tsx', source, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX)
const names = new Set(['chapterQuestionLimit', 'usedQuestionCount', 'totalQuestionCount', 'remainingQuota', 'canGenerateNow', 'overQuota'])
const declarations = []
function visit(node) {
  if (ts.isVariableDeclaration(node) && names.has(node.name.getText(tree))) declarations.push(`const ${node.getText(tree)}`)
  ts.forEachChild(node, visit)
}
visit(tree)
const code = ts.transpileModule(declarations.join('\n'), {compilerOptions: {target: ts.ScriptTarget.ES2020}}).outputText

for (const [imported, generated, requested, remaining, enabled] of [
  [30, 0, 100, 100, true], [150, 0, 100, 100, true],
  [30, 20, 80, 80, true], [30, 20, 81, 80, false], [30, 100, 1, 0, false],
]) {
  test(`import ${imported}, AI ${generated}, request ${requested}`, () => {
    const actual = vm.runInNewContext(`${code}\n({usedQuestionCount, remainingQuota, canGenerateNow})`, {
      readiness: {stats: {chapter_question_limit: 100, chapter_total_count: imported + generated,
                          chapter_generated_count: generated, chapter_remaining_quota: remaining}},
      stats: {total: imported + generated}, numericGenerateCount: requested,
      chapterPublished: false, selectedBankVersion: {id: 'bank'}, materials: [{id: 'material'}],
      canGenerateQuestions: true, invalidDifficulty: false, invalidQuestionTypeMix: false,
    })
    assert.equal(actual.usedQuestionCount, generated)
    assert.equal(actual.remainingQuota, remaining)
    assert.equal(actual.canGenerateNow, enabled)
  })
}
