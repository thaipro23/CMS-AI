const assert = require('node:assert/strict')
const { test } = require('node:test')
const { readFileSync } = require('node:fs')
const { join } = require('node:path')

const fa26Css = readFileSync(join(__dirname, '../styles/fa26-layout-hotfix.css'), 'utf8')

test('student and analytics synchronized horizontal rail stays sticky at viewport bottom', () => {
  assert.match(fa26Css, /student-management-page \.enterprise-sticky-horizontal-scroll[\s\S]*position:\s*sticky\s*!important/)
  assert.match(fa26Css, /bottom:\s*0\s*!important/)
  assert.doesNotMatch(fa26Css, /enterprise-sticky-horizontal-scroll[\s\S]{0,220}position:\s*static\s*!important/)
})
