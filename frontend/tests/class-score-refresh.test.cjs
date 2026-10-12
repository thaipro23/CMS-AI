const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const vm = require('node:vm')
const test = require('node:test')
const ts = require('typescript')

// Execute the actual page actions, replacing only API and UI boundaries.
const page = fs.readFileSync(path.join(__dirname, '../app/student-management/classes/[classId]/page.tsx'), 'utf8')
const tree = ts.createSourceFile('page.tsx', page, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX)
const declarations = []
function visit(node) {
  if (ts.isVariableDeclaration(node) && ['followExistingJobIfAny', 'runScoreUpdate'].includes(node.name.getText(tree))) {
    declarations.push(`const ${node.getText(tree)}`)
  }
  ts.forEachChild(node, visit)
}
visit(tree)
assert.equal(declarations.length, 2)
const code = ts.transpileModule(`${declarations.join('\n')}\nrunScoreUpdate()`, {compilerOptions: {target: ts.ScriptTarget.ES2020}}).outputText

async function run(activeJob) {
  const calls = {enqueued: 0, waited: [], refreshed: 0, errors: []}
  const context = {
    canRunFullCmsSync: true, classId: 'DOM1021.02', jsonHeaders: {},
    setSyncingScoreUpdate() {}, setMessage() {}, setActiveJob() {},
    setErrorModal(message) {calls.errors.push(message)},
    jobTypeLabel: value => value,
    isJobActive: job => ['queued', 'running'].includes(job.status),
    refreshSyncJobs: async () => activeJob ? [activeJob] : [],
    waitForSyncJob: async job => {
      calls.waited.push(job.job_type)
      return {...job, status: job.failure ? 'failed' : 'completed', error_message: job.failure, result_json: {updated: 30}}
    },
    refreshAfterDataChange: async () => {calls.refreshed++},
    enqueueAcademicClassLearningSyncJob: async (_headers, _classId, options) => {
      assert.equal(options.force, true)
      calls.enqueued++
      return {id: 'new-grade-job', job_type: 'learning_sync', status: 'queued', force: true}
    },
  }
  await vm.runInNewContext(code, context)
  return calls
}

for (const job_type of ['cms_sync_check', 'cms_enrollment_sync', 'full_cms_sync']) {
  test(`score update waits for ${job_type} then requests fresh grades`, async () => {
    const calls = await run({job_type, status: 'running', force: true})
    assert.equal(calls.enqueued, 1)
    assert.deepEqual(calls.waited, [job_type, 'learning_sync'])
    assert.deepEqual(calls.errors, [])
  })
}
test('partial learning sync does not replace forced score refresh', async () => {
  assert.equal((await run({job_type: 'learning_sync', status: 'running', force: false})).enqueued, 1)
})
test('existing forced learning sync satisfies the action after completion', async () => {
  const calls = await run({job_type: 'learning_sync', status: 'running', force: true})
  assert.equal(calls.enqueued, 0)
  assert.equal(calls.refreshed, 1)
})
test('failed preceding job is reported without a false score success', async () => {
  const calls = await run({job_type: 'cms_enrollment_sync', status: 'running', failure: 'enroll failed'})
  assert.equal(calls.enqueued, 0)
  assert.deepEqual(calls.errors, ['enroll failed'])
})
test('no active job starts a forced score refresh', async () => {
  assert.equal((await run(null)).enqueued, 1)
})
