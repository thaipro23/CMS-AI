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


# 1) AP internal API contract.
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

p = 'backend/app/core/config.py'
s = read(p)
s = must_replace(
    s,
    "academic_ap_get_campus_endpoint: str = '/get-campus'",
    "academic_ap_get_campus_endpoint: str = 'https://apitest.poly.edu.vn/api/cms/get-campus'",
    'campus API endpoint',
    1,
)
write(p, s)

# 2) Remove user-configured question-type quota from request schemas.
p = 'backend/app/schemas/question_bank.py'
s = read(p)
for name in ('BankReleaseQuizPreviewRequest', 'QuizAutoMapRequest', 'QuizBlueprintCreate'):
    s = s.replace(f'class {name}(QuestionTypeQuotaMixin):', f'class {name}(BaseModel):')
# Remove quota validator only from the three request models above. Difficulty validation stays.
for name in ('BankReleaseQuizPreviewRequest', 'QuizAutoMapRequest', 'QuizBlueprintCreate'):
    marker = f'class {name}(BaseModel):'
    if marker not in s:
        continue
    pos = s.index(marker)
    next_pos = s.find('\nclass ', pos + len(marker))
    if next_pos < 0:
        next_pos = len(s)
    block = s[pos:next_pos]
    block = block.replace('        self.validate_type_quota(self.total_questions)\n', '')
    # Type count fields came from the mixin, so inheritance removal is enough.
    s = s[:pos] + block + s[next_pos:]
write(p, s)

# 3) Planner: question type is automatic. Keep response types on Question records;
# they are no longer a quota/matrix axis. Legacy releases may rebalance requested
# Easy/Medium/Hard to the difficulty buckets that actually exist.
p = 'backend/app/services/question_bank/quiz_creation.py'
s = read(p)
# Both normal Quiz and Final test grouping become one automatic type bucket.
s = s.replace("            qtype = normalize_question_type(getattr(question, 'question_type', None))\n", "            qtype = 'auto'\n")
# Ignore explicit type counts even when old blueprint/database rows still contain them.
pattern = re.compile(
    r"        requested_types = exact_type_counts\(\n            total=total_questions,\n            single_select_count=single_select_count,\n            multi_select_count=multi_select_count,\n            text_input_count=text_input_count,\n            numerical_input_count=numerical_input_count,\n        \)"
)
s, n = pattern.subn("        requested_types = {'auto': int(total_questions)}", s)
if n < 2:
    raise SystemExit(f'Expected both Quiz and Final requested_types blocks, got {n}')

# Insert deterministic legacy difficulty rebalancing before availability is fed to matrix solver.
needle = "        availability = {\n            (diff, qtype): len(grouped_rows.get((diff, qtype), []))\n"
insert = """        # Legacy imports are allowed to miss one or more difficulty buckets. First use
        # unclassified legacy rows as flexible capacity, then move any remaining target
        # to classified buckets with spare rows. Native/manual/AI banks stay strict.
        legacy_mode = bool(rows) and all(is_legacy_quiz_question(questions[row.question_id]) for row in rows)
        if legacy_mode:
            order = ('easy', 'medium', 'hard')
            classified_capacity = {diff: len(grouped_rows.get((diff, 'auto'), [])) for diff in order}
            flex_left = len(flexible_rows.get('auto', []))
            effective = {diff: min(int(requested.get(diff, 0) or 0), classified_capacity[diff]) for diff in order}
            for diff in order:
                missing = max(0, int(requested.get(diff, 0) or 0) - effective[diff])
                used = min(missing, flex_left)
                effective[diff] += used
                flex_left -= used
            remaining = int(total_questions) - sum(effective.values())
            while remaining > 0:
                candidates = [diff for diff in order if classified_capacity[diff] > effective[diff]]
                if candidates:
                    target_diff = max(candidates, key=lambda diff: (classified_capacity[diff] - effective[diff], -order.index(diff)))
                    effective[target_diff] += 1
                    remaining -= 1
                    continue
                if flex_left > 0:
                    target_diff = min(order, key=lambda diff: (effective[diff], order.index(diff)))
                    effective[target_diff] += 1
                    flex_left -= 1
                    remaining -= 1
                    continue
                break
            if sum(effective.values()) != int(total_questions):
                raise ValueError(
                    f'Release legacy không đủ {int(total_questions)} câu để tạo Quiz; '
                    f'khả dụng theo độ khó={classified_capacity}, chưa phân loại={len(flexible_rows.get("auto", []))}.'
                )
            requested = effective
"""
if needle not in s:
    raise SystemExit('Regular planner availability anchor not found')
s = s.replace(needle, insert + needle, 1)

needle2 = "        availability = {\n            (diff, qtype): len(grouped.get((diff, qtype), []))\n"
insert2 = """        legacy_entries = [entry for values in grouped.values() for entry in values] + [entry for values in flexible.values() for entry in values]
        legacy_mode = bool(legacy_entries) and all(
            str(getattr(entry['question'], 'source_type', '') or '').strip().lower() == 'legacy_quiz_excel'
            for entry in legacy_entries
        )
        if legacy_mode:
            order = ('easy', 'medium', 'hard')
            classified_capacity = {diff: len(grouped.get((diff, 'auto'), [])) for diff in order}
            flex_left = len(flexible.get('auto', []))
            effective = {diff: min(int(requested.get(diff, 0) or 0), classified_capacity[diff]) for diff in order}
            for diff in order:
                missing = max(0, int(requested.get(diff, 0) or 0) - effective[diff])
                used = min(missing, flex_left)
                effective[diff] += used
                flex_left -= used
            remaining = int(total_questions) - sum(effective.values())
            while remaining > 0:
                candidates = [diff for diff in order if classified_capacity[diff] > effective[diff]]
                if candidates:
                    target_diff = max(candidates, key=lambda diff: (classified_capacity[diff] - effective[diff], -order.index(diff)))
                    effective[target_diff] += 1
                    remaining -= 1
                    continue
                if flex_left > 0:
                    target_diff = min(order, key=lambda diff: (effective[diff], order.index(diff)))
                    effective[target_diff] += 1
                    flex_left -= 1
                    remaining -= 1
                    continue
                break
            if sum(effective.values()) != int(total_questions):
                raise ValueError(
                    f'Final test legacy không đủ {int(total_questions)} câu; '
                    f'khả dụng theo độ khó={classified_capacity}, chưa phân loại={len(flexible.get("auto", []))}.'
                )
            requested = effective
"""
if needle2 not in s:
    raise SystemExit('Final planner availability anchor not found')
s = s.replace(needle2, insert2 + needle2, 1)

# User-facing wording: no more type quota contract.
s = s.replace('bank_release_difficulty_question_type_itembank_v4', 'bank_release_difficulty_itembank_v5')
s = s.replace('đúng quota difficulty × loại câu hỏi', 'đúng số câu theo độ khó hiệu lực')
s = s.replace('theo quota difficulty × loại câu hỏi', 'theo cấu hình độ khó')
s = s.replace('quota difficulty/loại hiện tại', 'cấu hình độ khó hiện tại')
write(p, s)

# 4) Quiz UI: only number of questions + difficulty + timer.
p = 'frontend/app/bank/quiz/page.tsx'
s = read(p)
for line in [
    '  singleSelectCount: number\n', '  multiSelectCount: number\n', '  textInputCount: number\n', '  numericalInputCount: number\n',
    '    singleSelectCount: 15,\n', '    multiSelectCount: 0,\n', '    textInputCount: 0,\n', '    numericalInputCount: 0,\n',
    '    singleSelectCount: 30,\n',
]:
    s = s.replace(line, '')
s = re.sub(r"\n  const quizTypeTotal = .*?\n  const finalTypeTotal = .*?\n", '\n', s)
for owner in ('quizConfig', 'finalConfig', 'config'):
    s = re.sub(rf"\n\s*single_select_count:\s*{owner}\.[^,]+,\n\s*multi_select_count:\s*{owner}\.[^,]+,\n\s*text_input_count:\s*{owner}\.[^,]+,\n\s*numerical_input_count:\s*{owner}\.[^,]+,", '', s)
s = s.replace(
    '    const quizInvalid = quizDifficultyTotal !== 100 || quizTypeTotal !== quizConfig.totalQuestions\n    const finalInvalid = finalDifficultyTotal !== 100 || finalTypeTotal !== finalConfig.totalQuestions\n',
    '    const quizInvalid = quizDifficultyTotal !== 100\n    const finalInvalid = finalDifficultyTotal !== 100\n',
)
s = re.sub(r"\n\s*if \(patch\.totalQuestions !== undefined\) \{.*?\n\s*\}\n", '\n', s, flags=re.S)
s = re.sub(r"\n\s*const typeTotal = config\.[^\n]+", '', s)
# Remove the whole visual question-type section, bounded by Timer heading.
s = re.sub(
    r"\n\s*<div className=\"section-heading compact-heading quiz-timer-subhead\">\s*<div><h3>Loại câu hỏi</h3>.*?(?=\n\s*<div className=\"section-heading compact-heading quiz-timer-subhead\">\s*<div><h3>Timer</h3>)",
    '\n', s, flags=re.S,
)
# Blueprint hydration no longer imports old count columns into config.
s = re.sub(r"\n\s*singleSelectCount:\s*Number\([^\n]+\),", '', s)
s = re.sub(r"\n\s*multiSelectCount:\s*Number\([^\n]+\),", '', s)
s = re.sub(r"\n\s*textInputCount:\s*Number\([^\n]+\),", '', s)
s = re.sub(r"\n\s*numericalInputCount:\s*Number\([^\n]+\),", '', s)
# Handle newer TypeQuotaDraft representation if present.
s = re.sub(r"\ntype TypeQuotaDraft = \{.*?\n\}\n", '\n', s, flags=re.S)
s = re.sub(r"\nfunction normalizeTypeQuotas\(.*?\n\}\n", '\n', s, flags=re.S)
s = re.sub(r"\nfunction sumTypeQuotas\(.*?\n\}\n", '\n', s, flags=re.S)
s = re.sub(r"\n\s*typeQuotas:\s*normalizeTypeQuotas\([^\n]+\),", '', s)
s = re.sub(r"\n\s*typeQuotas:\s*\{.*?\n\s*\},", '', s, flags=re.S)
s = re.sub(r"\n\s*typeQuotas:\s*config\.typeQuotas,", '', s)
s = re.sub(r"\n\s*const typeQuotaSum = sumTypeQuotas\(config\.typeQuotas\);", '', s)
s = s.replace(' || typeQuotaSum !== config.totalQuestions', '')
s = s.replace(' && typeQuotaSum === config.totalQuestions', '')
write(p, s)

# 5) Remove duplicate Udemy top notice only.
p = 'frontend/app/student-management/classes/[classId]/page.tsx'
s = read(p)
start = s.find('Lớp đang vận hành trên Udemy')
if start >= 0:
    # Prefer conditional wrapper if present.
    cond_start = s.rfind('{', max(0, start - 600), start)
    cond_end = s.find(': null}', start)
    if cond_start >= 0 and cond_end >= 0 and cond_end - cond_start < 2500:
        s = s[:cond_start] + s[cond_end + len(': null}'):]
    else:
        block_start = s.rfind('<div', max(0, start - 800), start)
        close1 = s.find('</div>', start)
        close2 = s.find('</div>', close1 + 6) if close1 >= 0 else -1
        end = close2 if close2 >= 0 and close2 - start < 2000 else close1
        if block_start < 0 or end < 0:
            raise SystemExit('Could not bound Udemy banner')
        s = s[:block_start] + s[end + 6:]
if 'Lớp đang vận hành trên Udemy' in s:
    raise SystemExit('Udemy top banner remains')
write(p, s)

# 6) AP UI explicit campus refresh.
p = 'frontend/app/ap-sync/page.tsx'
s = read(p)
s = s.replace("{loadingOptions ? 'Đang tải...' : 'Làm mới dữ liệu'}", "{loadingOptions ? 'Đang cập nhật...' : 'Cập nhật cơ sở'}")
s = s.replace("hint: 'Nhập thủ công tại trang Cơ sở'", "hint: 'Lấy từ API theo hệ POLY/PTCD'")
write(p, s)

# 7) RBAC: system admin permissions must be complete/future-proof; campus owner is
# a small-campus operator with catalog/sync/RBAC menu access but no bank authoring.
p = 'backend/app/services/business_rbac.py'
s = read(p)
s = must_replace(
    s,
    "    CAMPUS_OWNER: {'academic.view', 'academic.manage_campus', 'view_training_reports', 'jobs.view'},",
    "    CAMPUS_OWNER: {'academic.view', 'academic.manage_campus', 'view_training_reports', 'jobs.view', 'department.manage_all', 'subject.create', 'subject.update', 'course.sync', 'user.manage_all', 'rbac.view'},",
    'campus owner permissions',
    1,
)
old = """        if self.is_system_admin(user):
            permissions.update(ROLE_PERMISSIONS[SYSTEM_ADMIN])
"""
new = """        if self.is_system_admin(user):
            # Backend has_permission() already treats SYSTEM_ADMIN as unrestricted.
            # Return the same truth through /rbac/me so frontend can() does not hide
            # newly added permissions merely because ROLE_PERMISSIONS is stale.
            permissions.update(ROLE_PERMISSIONS[SYSTEM_ADMIN])
            permissions.update(
                str(row.code).strip()
                for row in self.db.query(RBACPermission).all()
                if str(getattr(row, 'code', '') or '').strip()
            )
"""
s = must_replace(s, old, new, 'system admin effective permissions', 1)
write(p, s)

# 8) Safe project-wide spacing contract loaded last. Only target established layout
# primitives; do not restyle arbitrary .card/label/content components.
p = 'frontend/app/layout.tsx'
s = read(p)
anchor = "import '../styles/subject-management-udemy.css'\n"
if 'project-spacing-contract.css' not in s:
    s = must_replace(s, anchor, anchor + "import '../styles/project-spacing-contract.css'\n", 'spacing import', 1)
write(p, s)

css = """/* ACMS project-wide spacing/layout contract. Loaded last on purpose.
   Keep this structural only: no colors, typography, arbitrary card margins or page-specific skin. */
:root {
  --acms-space-1: 4px;
  --acms-space-2: 8px;
  --acms-space-3: 12px;
  --acms-space-4: 16px;
  --acms-space-5: 20px;
  --acms-space-6: 24px;
}

*, *::before, *::after { box-sizing: border-box; }

.app-main, .app-content, .page-root, .page-stack,
.enterprise-standard-page, .bank-contract-page, .workspace-section,
.popup-action-panel, .enterprise-panel { min-width: 0; }

.page-stack, .bank-multipage, .enterprise-standard-page,
.quiz-creation-workbench, .ap-sync-page { gap: var(--acms-space-5); }

.section-heading, .enterprise-section-heading, .workspace-section-header,
.toolbar, .toolbar-actions, .section-actions, .header-actions,
.dialog-actions, .modal-actions, .button-row, .filter-actions {
  gap: var(--acms-space-3);
}

.toolbar, .toolbar-actions, .section-actions, .header-actions,
.dialog-actions, .modal-actions, .button-row, .filter-actions { flex-wrap: wrap; }

.settings-form-grid, .quiz-small-grid, .option-grid,
.compact-filter-grid, .filter-grid, .form-grid, .quiz-modal-grid {
  column-gap: var(--acms-space-4);
  row-gap: var(--acms-space-3);
}

.table-scroll, .enterprise-table-scroll, .data-table-scroll {
  max-width: 100%;
  min-width: 0;
  overflow-x: auto;
  overscroll-behavior-inline: contain;
}

[role='dialog'] { max-width: min(96vw, 1180px); }
[role='dialog'] .dialog-body, [role='dialog'] .modal-body {
  min-width: 0;
  overflow-x: hidden;
}
[role='dialog'] .dialog-footer, [role='dialog'] .modal-footer {
  gap: var(--acms-space-2);
}
.quiz-modal-grid { align-items: start; }
.quiz-timer-subhead { margin-top: var(--acms-space-4); }

@media (max-width: 960px) {
  .quiz-modal-grid, .settings-form-grid, .form-grid {
    grid-template-columns: minmax(0, 1fr) !important;
  }
  .page-stack, .bank-multipage, .enterprise-standard-page { gap: var(--acms-space-4); }
}

@media (max-width: 640px) {
  .toolbar, .toolbar-actions, .section-actions, .header-actions,
  .dialog-actions, .modal-actions, .button-row, .filter-actions { width: 100%; }
}
"""
write('frontend/styles/project-spacing-contract.css', css)

print('patch-v2 applied')
