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


# ---------------------------------------------------------------------------
# 1) Internal Academic API contract: POLY/PTCD + term_name, campus from apitest.
# ---------------------------------------------------------------------------
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
    'campus endpoint',
    1,
)
write(p, s)


# ---------------------------------------------------------------------------
# 2) Question-type quota is not a user configuration anymore.
# Keep DB compatibility fields elsewhere; remove it from active request contracts.
# ---------------------------------------------------------------------------
p = 'backend/app/schemas/question_bank.py'
s = read(p)
for name in ('BankReleaseQuizPreviewRequest', 'QuizAutoMapRequest', 'QuizBlueprintCreate'):
    s = must_replace(s, f'class {name}(QuestionTypeQuotaMixin):', f'class {name}(BaseModel):', f'{name} inheritance', 1)
    marker = f'class {name}(BaseModel):'
    start = s.index(marker)
    end = s.find('\nclass ', start + len(marker))
    if end < 0:
        end = len(s)
    block = s[start:end]
    block = block.replace('        self.validate_type_quota(self.total_questions)\n', '')
    s = s[:start] + block + s[end:]
write(p, s)


# ---------------------------------------------------------------------------
# 3) Planner: type is automatic; legacy difficulty can rebalance to available rows.
# Actual Question.question_type/component behavior is preserved.
# ---------------------------------------------------------------------------
p = 'backend/app/services/question_bank/quiz_creation.py'
s = read(p)
qtype_old = "            qtype = normalize_question_type(getattr(question, 'question_type', None))\n"
qtype_count = s.count(qtype_old)
if qtype_count < 2:
    raise SystemExit(f'Expected >=2 qtype grouping anchors, got {qtype_count}')
s = s.replace(qtype_old, "            qtype = 'auto'\n")

requested_pattern = re.compile(
    r"        requested_types = exact_type_counts\(\n"
    r"            total=total_questions,\n"
    r"            single_select_count=single_select_count,\n"
    r"            multi_select_count=multi_select_count,\n"
    r"            text_input_count=text_input_count,\n"
    r"            numerical_input_count=numerical_input_count,\n"
    r"        \)"
)
s, requested_count = requested_pattern.subn("        requested_types = {'auto': int(total_questions)}", s)
if requested_count != 2:
    raise SystemExit(f'Expected 2 requested type blocks, got {requested_count}')

regular_anchor = """        availability = {
            (diff, qtype): len(grouped_rows.get((diff, qtype), []))
"""
regular_rebalance = """        # Legacy imports may legitimately have no classified Hard/Medium/Easy bucket.
        # Rebalance only legacy releases; native/manual/AI releases remain strict.
        legacy_mode = bool(rows) and all(is_legacy_quiz_question(questions[row.question_id]) for row in rows)
        if legacy_mode:
            order = ('easy', 'medium', 'hard')
            classified_capacity = {diff: len(grouped_rows.get((diff, 'auto'), [])) for diff in order}
            flexible_capacity = len(flexible_rows.get('auto', []))
            flex_left = flexible_capacity
            effective = {diff: min(int(requested.get(diff, 0) or 0), classified_capacity[diff]) for diff in order}
            for diff in order:
                deficit = max(0, int(requested.get(diff, 0) or 0) - effective[diff])
                used = min(deficit, flex_left)
                effective[diff] += used
                flex_left -= used
            remaining = int(total_questions) - sum(effective.values())
            while remaining > 0:
                spare = [diff for diff in order if classified_capacity[diff] > effective[diff]]
                if spare:
                    target = max(spare, key=lambda diff: (classified_capacity[diff] - effective[diff], -order.index(diff)))
                    effective[target] += 1
                    remaining -= 1
                    continue
                if flex_left > 0:
                    target = min(order, key=lambda diff: (effective[diff], order.index(diff)))
                    effective[target] += 1
                    flex_left -= 1
                    remaining -= 1
                    continue
                break
            if sum(effective.values()) != int(total_questions):
                raise ValueError(
                    f'Release legacy không đủ {int(total_questions)} câu để tạo Quiz; '
                    f'khả dụng theo độ khó={classified_capacity}, chưa phân loại={flexible_capacity}.'
                )
            requested = effective
"""
s = must_replace(s, regular_anchor, regular_rebalance + regular_anchor, 'regular legacy rebalance', 1)

final_anchor = """        availability = {
            (diff, qtype): len(grouped.get((diff, qtype), []))
"""
final_rebalance = """        legacy_entries = [entry for values in grouped.values() for entry in values] + [entry for values in flexible.values() for entry in values]
        legacy_mode = bool(legacy_entries) and all(
            str(getattr(entry['question'], 'source_type', '') or '').strip().lower() == 'legacy_quiz_excel'
            for entry in legacy_entries
        )
        if legacy_mode:
            order = ('easy', 'medium', 'hard')
            classified_capacity = {diff: len(grouped.get((diff, 'auto'), [])) for diff in order}
            flexible_capacity = len(flexible.get('auto', []))
            flex_left = flexible_capacity
            effective = {diff: min(int(requested.get(diff, 0) or 0), classified_capacity[diff]) for diff in order}
            for diff in order:
                deficit = max(0, int(requested.get(diff, 0) or 0) - effective[diff])
                used = min(deficit, flex_left)
                effective[diff] += used
                flex_left -= used
            remaining = int(total_questions) - sum(effective.values())
            while remaining > 0:
                spare = [diff for diff in order if classified_capacity[diff] > effective[diff]]
                if spare:
                    target = max(spare, key=lambda diff: (classified_capacity[diff] - effective[diff], -order.index(diff)))
                    effective[target] += 1
                    remaining -= 1
                    continue
                if flex_left > 0:
                    target = min(order, key=lambda diff: (effective[diff], order.index(diff)))
                    effective[target] += 1
                    flex_left -= 1
                    remaining -= 1
                    continue
                break
            if sum(effective.values()) != int(total_questions):
                raise ValueError(
                    f'Final test legacy không đủ {int(total_questions)} câu; '
                    f'khả dụng theo độ khó={classified_capacity}, chưa phân loại={flexible_capacity}.'
                )
            requested = effective
"""
s = must_replace(s, final_anchor, final_rebalance + final_anchor, 'final legacy rebalance', 1)

s = s.replace('bank_release_difficulty_question_type_itembank_v4', 'bank_release_difficulty_itembank_v5')
s = s.replace('đúng quota difficulty × loại câu hỏi', 'đúng số câu theo độ khó hiệu lực')
s = s.replace('theo quota difficulty × loại câu hỏi', 'theo cấu hình độ khó')
s = s.replace('quota difficulty/loại hiện tại', 'cấu hình độ khó hiện tại')
write(p, s)


# ---------------------------------------------------------------------------
# 4) Quiz UI: exact, bounded removals only. No broad JSX/brace regex.
# ---------------------------------------------------------------------------
p = 'frontend/app/bank/quiz/page.tsx'
s = read(p)
for line in (
    '  singleSelectCount: number\n',
    '  multiSelectCount: number\n',
    '  textInputCount: number\n',
    '  numericalInputCount: number\n',
    '    singleSelectCount: 15,\n',
    '    multiSelectCount: 0,\n',
    '    textInputCount: 0,\n',
    '    numericalInputCount: 0,\n',
    '    singleSelectCount: 30,\n',
):
    s = s.replace(line, '')

s = must_replace(
    s,
    "  const quizTypeTotal = quizConfig.singleSelectCount + quizConfig.multiSelectCount + quizConfig.textInputCount + quizConfig.numericalInputCount\n  const finalTypeTotal = finalConfig.singleSelectCount + finalConfig.multiSelectCount + finalConfig.textInputCount + finalConfig.numericalInputCount\n",
    '',
    'quiz type totals',
    1,
)

for owner in ('quizConfig', 'finalConfig', 'config'):
    block = (
        f"        single_select_count: {owner}.singleSelectCount,\n"
        f"        multi_select_count: {owner}.multiSelectCount,\n"
        f"        text_input_count: {owner}.textInputCount,\n"
        f"        numerical_input_count: {owner}.numericalInputCount,\n"
    )
    s = s.replace(block, '')

s = must_replace(
    s,
    "    const quizInvalid = quizDifficultyTotal !== 100 || quizTypeTotal !== quizConfig.totalQuestions\n    const finalInvalid = finalDifficultyTotal !== 100 || finalTypeTotal !== finalConfig.totalQuestions\n",
    "    const quizInvalid = quizDifficultyTotal !== 100\n    const finalInvalid = finalDifficultyTotal !== 100\n",
    'modal validation',
    1,
)

update_quota_block = """      if (patch.totalQuestions !== undefined) {
        const otherTypes = next.multiSelectCount + next.textInputCount + next.numericalInputCount
        if (otherTypes <= next.totalQuestions) next.singleSelectCount = next.totalQuestions - otherTypes
        else {
          next.singleSelectCount = next.totalQuestions
          next.multiSelectCount = 0
          next.textInputCount = 0
          next.numericalInputCount = 0
        }
      }
"""
s = must_replace(s, update_quota_block, '', 'updateConfig quota coupling', 1)
s = must_replace(
    s,
    "    const typeTotal = config.singleSelectCount + config.multiSelectCount + config.textInputCount + config.numericalInputCount\n",
    '',
    'ConfigPanel typeTotal',
    1,
)

quota_ui = """      <div className=\"section-heading compact-heading quiz-timer-subhead\">
        <div><h3>Loại câu hỏi</h3><p className=\"muted\">Quota là số câu chính xác, tổng phải bằng {config.totalQuestions}.</p></div>
        <span className={classNames('status', typeTotal === config.totalQuestions ? 'success' : 'warning')}>{typeTotal}/{config.totalQuestions}</span>
      </div>
      <div className=\"quiz-type-quota-grid\">
        <label>Một đáp án<input className=\"input\" type=\"number\" min={0} max={config.totalQuestions} disabled={lockedByBlueprint} value={config.singleSelectCount} onChange={(event) => updateConfig(kind, { singleSelectCount: normalizeNumber(Number(event.target.value), 0, 0, config.totalQuestions) })} /></label>
        <label>Nhiều đáp án<input className=\"input\" type=\"number\" min={0} max={config.totalQuestions} disabled={lockedByBlueprint} value={config.multiSelectCount} onChange={(event) => updateConfig(kind, { multiSelectCount: normalizeNumber(Number(event.target.value), 0, 0, config.totalQuestions) })} /></label>
        <label>Trả lời ngắn<input className=\"input\" type=\"number\" min={0} max={config.totalQuestions} disabled={lockedByBlueprint} value={config.textInputCount} onChange={(event) => updateConfig(kind, { textInputCount: normalizeNumber(Number(event.target.value), 0, 0, config.totalQuestions) })} /></label>
        <label>Trả lời số<input className=\"input\" type=\"number\" min={0} max={config.totalQuestions} disabled={lockedByBlueprint} value={config.numericalInputCount} onChange={(event) => updateConfig(kind, { numericalInputCount: normalizeNumber(Number(event.target.value), 0, 0, config.totalQuestions) })} /></label>
      </div>
      {typeTotal !== config.totalQuestions ? <div className=\"alert warning\">Tổng quota loại câu hỏi đang là {typeTotal}/{config.totalQuestions}. Hãy điều chỉnh trước khi tạo.</div> : null}
"""
s = must_replace(s, quota_ui, '', 'question type quota UI', 1)

blueprint_hydration = """      singleSelectCount: Number(blueprint.single_select_count ?? blueprint.total_questions),
      multiSelectCount: Number(blueprint.multi_select_count ?? 0),
      textInputCount: Number(blueprint.text_input_count ?? 0),
      numericalInputCount: Number(blueprint.numerical_input_count ?? 0),
"""
s = must_replace(s, blueprint_hydration, '', 'blueprint type hydration', 1)

s = must_replace(
    s,
    "    const typeTotal = config.singleSelectCount + config.multiSelectCount + config.textInputCount + config.numericalInputCount\n    if (difficultyTotal !== 100 || typeTotal !== config.totalQuestions) {\n",
    "    if (difficultyTotal !== 100) {\n",
    'blueprint validation',
    1,
)

blueprint_payload = """        single_select_count: config.singleSelectCount,
        multi_select_count: config.multiSelectCount,
        text_input_count: config.textInputCount,
        numerical_input_count: config.numericalInputCount,
"""
s = must_replace(s, blueprint_payload, '', 'blueprint payload types', 1)

preview_payload = """        single_select_count: config.singleSelectCount,
        multi_select_count: config.multiSelectCount,
        text_input_count: config.textInputCount,
        numerical_input_count: config.numericalInputCount,
"""
# Same text may have been removed once above; remove any remaining occurrence.
s = s.replace(preview_payload, '')

old_footer = """<small>Course ID: {normalizeOpenEdxCourseId(courseId) || '—'} · Quiz độ khó {quizConfig.easy}/{quizConfig.medium}/{quizConfig.hard} · loại {quizConfig.singleSelectCount}/{quizConfig.multiSelectCount}/{quizConfig.textInputCount}/{quizConfig.numericalInputCount} · Final loại {finalConfig.singleSelectCount}/{finalConfig.multiSelectCount}/{finalConfig.textInputCount}/{finalConfig.numericalInputCount}</small>"""
new_footer = """<small>Course ID: {normalizeOpenEdxCourseId(courseId) || '—'} · Quiz độ khó {quizConfig.easy}/{quizConfig.medium}/{quizConfig.hard} · Final độ khó {finalConfig.easy}/{finalConfig.medium}/{finalConfig.hard}</small>"""
s = must_replace(s, old_footer, new_footer, 'modal footer type quota text', 1)

write(p, s)


# ---------------------------------------------------------------------------
# 5) Remove exact duplicate Udemy notice; keep UdemyClassProgressPanel.
# ---------------------------------------------------------------------------
p = 'frontend/app/student-management/classes/[classId]/page.tsx'
s = read(p)
udemy_notice = """      {isUdemyClass ? <InlineNotice notice={{ ...noticeInfo('Điểm và tiến độ lấy từ file Udemy. Tiến độ từng sinh viên được hiển thị ngay bên dưới; chỉ mở quản lý môn khi cần import file hoặc chỉnh kế hoạch.', 'Lớp đang vận hành trên Udemy'), actionHref: classInfo?.subject_delivery_id ? udemyDashboardHref : undefined, actionLabel: classInfo?.subject_delivery_id ? 'Import / kế hoạch Udemy' : undefined }} /> : null}
"""
s = must_replace(s, udemy_notice, '', 'Udemy duplicate notice', 1)
write(p, s)


# ---------------------------------------------------------------------------
# 6) AP Sync explicit campus refresh action.
# ---------------------------------------------------------------------------
p = 'frontend/app/ap-sync/page.tsx'
s = read(p)
s = must_replace(
    s,
    "{loadingOptions ? 'Đang tải...' : 'Làm mới dữ liệu'}",
    "{loadingOptions ? 'Đang cập nhật...' : 'Cập nhật cơ sở'}",
    'campus refresh label',
    1,
)
s = s.replace("hint: 'Nhập thủ công tại trang Cơ sở'", "hint: 'Lấy từ API theo hệ POLY/PTCD'")
write(p, s)


# ---------------------------------------------------------------------------
# 7) RBAC.
# SYSTEM_ADMIN: /rbac/me must expose every current permission so frontend never
# hides a page that backend already permits.
# CAMPUS_OWNER: operational/catalog/RBAC view for small-campus ownership, no bank
# authoring/review/publish privileges. Scope enforcement still comes from assignment.
# ---------------------------------------------------------------------------
p = 'backend/app/services/business_rbac.py'
s = read(p)
s = must_replace(
    s,
    "    CAMPUS_OWNER: {'academic.view', 'academic.manage_campus', 'view_training_reports', 'jobs.view'},",
    "    CAMPUS_OWNER: {'academic.view', 'academic.manage_campus', 'view_training_reports', 'jobs.view', 'department.manage_all', 'subject.create', 'subject.update', 'course.sync', 'rbac.view'},",
    'campus owner permissions',
    1,
)
old_admin = """        if self.is_system_admin(user):
            permissions.update(ROLE_PERMISSIONS[SYSTEM_ADMIN])
"""
new_admin = """        if self.is_system_admin(user):
            permissions.update(ROLE_PERMISSIONS[SYSTEM_ADMIN])
            permissions.update(
                str(row.code).strip()
                for row in self.db.query(RBACPermission).all()
                if str(getattr(row, 'code', '') or '').strip()
            )
"""
s = must_replace(s, old_admin, new_admin, 'system admin effective permissions', 1)
write(p, s)


# ---------------------------------------------------------------------------
# 8) Final project-wide spacing/layout contract, structural only.
# ---------------------------------------------------------------------------
p = 'frontend/app/layout.tsx'
s = read(p)
anchor = "import '../styles/subject-management-udemy.css'\n"
if 'project-spacing-contract.css' not in s:
    s = must_replace(s, anchor, anchor + "import '../styles/project-spacing-contract.css'\n", 'final spacing import', 1)
write(p, s)

css = """/* ACMS project-wide spacing/layout contract. Loaded last intentionally.
   Structural only: no colors, typography, generic card margins or page-specific skin. */
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

print('patch-v3 applied safely')
