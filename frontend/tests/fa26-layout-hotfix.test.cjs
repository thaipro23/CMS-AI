const assert = require('node:assert/strict')
const { test } = require('node:test')
const { readFileSync } = require('node:fs')
const { join } = require('node:path')

const css = readFileSync(join(__dirname, '../styles/fa26-layout-hotfix.css'), 'utf8')

test('student and analytics page stacks are content-sized flex columns', () => {
  assert.match(css, /page-stack\.student-management-page[\s\S]*display:\s*flex\s*!important/)
  assert.match(css, /page-stack\.analytics-learning-page[\s\S]*display:\s*flex\s*!important/)
  assert.match(css, /flex-direction:\s*column\s*!important/)
  assert.match(css, /align-items:\s*stretch\s*!important/)
})

test('top-level cards cannot be compressed into overlapping grid rows', () => {
  assert.match(css, /student-management-page\s*>\s*\.academic-unified-card[\s\S]*min-height:\s*max-content\s*!important/)
  assert.match(css, /analytics-learning-page\s*>\s*\.academic-unified-card[\s\S]*min-height:\s*max-content\s*!important/)
})
