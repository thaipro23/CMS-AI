from pathlib import Path
import re


def read(path: str) -> str:
    return Path(path).read_text(encoding='utf-8')


def write(path: str, text: str) -> None:
    Path(path).write_text(text, encoding='utf-8')


def must_replace(text: str, old: str, new: str, label: str, count: int | None = None) -> str:
    actual = text.count(old)
    if actual == 0:
        raise SystemExit(f'Missing patch anchor: {label}')
    if count is not None and actual != count:
        raise SystemExit(f'Unexpected anchor count {label}: {actual} != {count}')
    return text.replace(old, new)


# AP gateway: product is POLY/PTCD and subject catalog is scoped by term.
p = 'backend/app/services/ap_academic_sync.py'
s = read(p)
old = """        # get-all-subject is intentionally global/keyless. Do not send the legacy
        # branch/term query parameters; scope is applied locally when fields exist.
        with httpx.Client(timeout=self.timeout_seconds, verify=self._verify_config(endpoint)) as http:
            response = http.get(endpoint, headers=self._headers())
"""
new = """        product = 'POLY' if normalized_branch == 'poly' else 'PTCD'
        params = {'product': product}
        if normalized_term:
            params['term_name'] = normalized_term
        with httpx.Client(timeout=self.timeout_seconds, verify=self._verify_config(endpoint)) as http:
            response = http.get(endpoint, headers=self._headers(), params=params)
"""
s = must_replace(s, old, new, 'get-all-subject product/term', 1)
write(p, s)

# Quiz request schemas: type quota is no longer part of preview/create/auto-map contract.
p = 'backend/app/schemas/question_bank.py'
s = read(p)
s = must_replace(s, 'class BankReleaseQuizPreviewRequest(QuestionTypeQuotaMixin):', 'class BankReleaseQuizPreviewRequest(BaseModel):', 'release preview schema', 1)
marker = 'class BankReleaseQuizPreviewRequest(BaseModel):'
pos = s.index(marker)
tail = s[pos:]
oldv = "        self.validate_type_quota(self.total_questions)\n        return self\n"
if oldv not in tail:
    raise SystemExit('Missing release type validator')
tail = tail.replace(oldv, "        return self\n", 1)
s = s[:pos] + tail
s = must_replace(s, 'class QuizAutoMapRequest(QuestionTypeQuotaMixin):', 'class QuizAutoMapRequest(BaseModel):', 'automap schema', 1)
pos = s.index('class QuizAutoMapRequest(BaseModel):')
tail = s[pos:]
if oldv not in tail:
    raise SystemExit('Missing automap type validator')
tail = tail.replace(oldv, "        return self\n", 1)
s = s[:pos] + tail
write(p, s)

# Quiz UI: remove question-type quota controls and payload fields.
p = 'frontend/app/bank/quiz/page.tsx'
s = read(p)
for line in [
    '  singleSelectCount: number\n', '  multiSelectCount: number\n',
    '  textInputCount: number\n', '  numericalInputCount: number\n',
    '    singleSelectCount: 15,\n', '    multiSelectCount: 0,\n',
    '    textInputCount: 0,\n', '    numericalInputCount: 0,\n',
    '    singleSelectCount: 30,\n',
]:
    s = s.replace(line, '')
s = re.sub(r"\n  const quizTypeTotal = quizConfig\.singleSelectCount \+ quizConfig\.multiSelectCount \+ quizConfig\.textInputCount \+ quizConfig\.numericalInputCount\n  const finalTypeTotal = finalConfig\.singleSelectCount \+ finalConfig\.multiSelectCount \+ finalConfig\.textInputCount \+ finalConfig\.numericalInputCount", '', s)
for owner in ('quizConfig', 'finalConfig', 'config'):
    s = re.sub(
        rf"\n\s*single_select_count: {owner}\.singleSelectCount,\n\s*multi_select_count: {owner}\.multiSelectCount,\n\s*text_input_count: {owner}\.textInputCount,\n\s*numerical_input_count: {owner}\.numericalInputCount,",
        '', s,
    )
s = s.replace(
    "    const quizInvalid = quizDifficultyTotal !== 100 || quizTypeTotal !== quizConfig.totalQuestions\n    const finalInvalid = finalDifficultyTotal !== 100 || finalTypeTotal !== finalConfig.totalQuestions\n",
    "    const quizInvalid = quizDifficultyTotal !== 100\n    const finalInvalid = finalDifficultyTotal !== 100\n",
)
s = re.sub(r"\n      if \(patch\.totalQuestions !== undefined\) \{\n        const otherTypes = next\.multiSelectCount \+ next\.textInputCount \+ next\.numericalInputCount\n        if \(otherTypes <= next\.totalQuestions\) next\.singleSelectCount = next\.totalQuestions - otherTypes\n        else \{\n          next\.singleSelectCount = next\.totalQuestions\n          next\.multiSelectCount = 0\n          next\.textInputCount = 0\n          next\.numericalInputCount = 0\n        \}\n      \}", '', s)
s = re.sub(r"\n    const typeTotal = config\.singleSelectCount \+ config\.multiSelectCount \+ config\.textInputCount \+ config\.numericalInputCount", '', s)
s = re.sub(
    r"\n      <div className=\"section-heading compact-heading quiz-timer-subhead\">\n        <div><h3>Loại câu hỏi</h3>.*?\n      \{typeTotal !== config\.totalQuestions \? <div className=\"alert warning\">.*?</div> : null\}",
    '', s, flags=re.S,
)
s = re.sub(r"\n      singleSelectCount: Number\(blueprint\.single_select_count \?\? blueprint\.total_questions\),\n      multiSelectCount: Number\(blueprint\.multi_select_count \?\? 0\),\n      textInputCount: Number\(blueprint\.text_input_count \?\? 0\),\n      numericalInputCount: Number\(blueprint\.numerical_input_count \?\? 0\),", '', s)
s = re.sub(r"\n    const typeTotal = config\.singleSelectCount \+ config\.multiSelectCount \+ config\.textInputCount \+ config\.numericalInputCount\n    if \(difficultyTotal !== 100 \|\| typeTotal !== config\.totalQuestions\) \{", "\n    if (difficultyTotal !== 100) {", s)
if 'Loại câu hỏi' in s or 'singleSelectCount' in s or 'quizTypeTotal' in s:
    raise SystemExit('Quiz type quota references remain in page.tsx')
write(p, s)

# Remove only the duplicate top Udemy notice; keep the import button in the progress section.
p = 'frontend/app/student-management/classes/[classId]/page.tsx'
s = read(p)
start = s.find('Lớp đang vận hành trên Udemy')
if start < 0:
    raise SystemExit('Udemy banner text not found')
# The current banner is an academic-class-platform-notice JSX block.
block_start = s.rfind('<div', 0, start)
block_end = s.find('</div>', start)
if block_start < 0 or block_end < 0:
    raise SystemExit('Udemy banner JSX bounds not found')
# Include nested copy div: advance to the closing wrapper after the first nested close.
next_close = s.find('</div>', block_end + 6)
if next_close > 0 and next_close - start < 1800:
    block_end = next_close
s = s[:block_start] + s[block_end + len('</div>'):]
if 'Lớp đang vận hành trên Udemy' in s:
    raise SystemExit('Udemy top banner remains')
write(p, s)

# Explicit campus refresh action on AP Sync.
p = 'frontend/app/ap-sync/page.tsx'
s = read(p)
s = s.replace("{loadingOptions ? 'Đang tải...' : 'Làm mới dữ liệu'}", "{loadingOptions ? 'Đang cập nhật...' : 'Cập nhật cơ sở'}", 1)
write(p, s)

# Project-wide spacing/layout contract loaded last.
p = 'frontend/app/layout.tsx'
s = read(p)
anchor = "import '../styles/subject-management-udemy.css'\n"
if 'project-spacing-contract.css' not in s:
    s = must_replace(s, anchor, anchor + "import '../styles/project-spacing-contract.css'\n", 'root final spacing import', 1)
write(p, s)

css = """/* Final project-wide spacing/layout contract. Loaded after all existing visual layers. */
:root {
  --acms-space-1: 4px;
  --acms-space-2: 8px;
  --acms-space-3: 12px;
  --acms-space-4: 16px;
  --acms-space-5: 20px;
  --acms-space-6: 24px;
}

*, *::before, *::after { box-sizing: border-box; }
main, section, article, form, fieldset, .app-main, .app-content, .page-root,
.workspace-section, .bank-contract-page, .enterprise-standard-page { min-width: 0; }

.page-stack, .bank-multipage, .enterprise-standard-page,
.quiz-creation-workbench, .ap-sync-page { gap: var(--acms-space-5); }

.workspace-section, .popup-action-panel, .bank-section,
.enterprise-panel, .settings-card, .card { min-width: 0; }

.workspace-section > * + *, .popup-action-panel > * + *,
.settings-card > * + * { margin-top: var(--acms-space-4); }

.section-heading, .enterprise-section-heading, .workspace-section-header {
  gap: var(--acms-space-3);
  align-items: flex-start;
}
.section-heading h2, .section-heading h3, .workspace-section h2,
.workspace-section h3, .popup-action-panel h2, .popup-action-panel h3 { margin-block: 0; }

label:not(.toggle-line):not(.check-row) > .input,
label:not(.toggle-line):not(.check-row) > select,
label:not(.toggle-line):not(.check-row) > textarea { margin-top: 6px; }

.settings-form-grid, .quiz-small-grid, .option-grid,
.compact-filter-grid, .filter-grid, .form-grid { gap: var(--acms-space-3) var(--acms-space-4); }

.toolbar, .toolbar-actions, .section-actions, .header-actions,
.dialog-actions, .modal-actions, .button-row, .filter-actions {
  gap: var(--acms-space-2);
  flex-wrap: wrap;
}
.toggle-line, .check-row { gap: var(--acms-space-2); }
.alert, .academic-inline-notice, .inline-notice { margin-block: var(--acms-space-3); }

.table-scroll, .enterprise-table-scroll, .data-table-scroll {
  max-width: 100%;
  overflow-x: auto;
  overscroll-behavior-inline: contain;
}

[role='dialog'] .dialog-body, [role='dialog'] .modal-body {
  min-width: 0;
  padding-block: var(--acms-space-4);
}
[role='dialog'] .dialog-footer, [role='dialog'] .modal-footer {
  gap: var(--acms-space-2);
  padding-top: var(--acms-space-3);
}
.quiz-modal-grid { gap: var(--acms-space-4); align-items: start; }
.quiz-timer-subhead { margin-top: var(--acms-space-4); }

@media (max-width: 960px) {
  .quiz-modal-grid, .settings-form-grid, .form-grid { grid-template-columns: minmax(0, 1fr); }
  .page-stack, .bank-multipage, .enterprise-standard-page { gap: var(--acms-space-4); }
}
@media (max-width: 640px) {
  .toolbar, .toolbar-actions, .section-actions, .header-actions,
  .dialog-actions, .modal-actions, .button-row, .filter-actions { width: 100%; }
  .toolbar-actions > .btn, .dialog-actions > .btn, .modal-actions > .btn { max-width: 100%; }
}
"""
write('frontend/styles/project-spacing-contract.css', css)
