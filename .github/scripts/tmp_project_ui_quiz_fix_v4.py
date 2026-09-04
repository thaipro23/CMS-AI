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


# 1) AP contract: get-all-subject is scoped by product + term_name.
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

p = 'backend/app/tests/test_academic_ap_internal_api.py'
s = read(p)
s = must_replace(s, 'def test_get_all_subject_is_global_keyless_catalog():', 'def test_get_all_subject_is_product_term_scoped_keyless_catalog():', 'AP subject test name', 1)
s = must_replace(s, "    assert not call.get('params')\n", "    assert call['params'] == {'product': 'POLY', 'term_name': 'Fall 2026'}\n", 'AP subject params assertion', 1)
write(p, s)


# 2) Quiz request schemas: exact question-type quotas are removed from user contract.
p = 'backend/app/schemas/question_bank.py'
s = read(p)
for name in ('QuizBlueprintCreate', 'BankReleaseQuizPreviewRequest', 'QuizAutoMapRequest'):
    s = must_replace(s, f'class {name}(QuestionTypeQuotaMixin):', f'class {name}(BaseModel):', f'{name} inheritance', 1)
for name in ('QuizBlueprintCreate', 'BankReleaseQuizPreviewRequest', 'QuizAutoMapRequest'):
    marker = f'class {name}(BaseModel):'
    start = s.index(marker)
    end = s.find('\nclass ', start + len(marker))
    if end < 0:
        end = len(s)
    block = s[start:end].replace('        self.validate_type_quota(self.total_questions)\n', '')
    s = s[:start] + block + s[end:]
write(p, s)


# 3) Planner: keep actual Question response types but remove type from quota/matrix axis.
p = 'backend/app/services/question_bank/quiz_creation.py'
s = read(p)
qtype_old = "            qtype = normalize_question_type(getattr(question, 'question_type', None))\n"
if s.count(qtype_old) < 2:
    raise SystemExit(f'Expected >=2 planner qtype anchors, got {s.count(qtype_old)}')
s = s.replace(qtype_old, "            qtype = 'auto'\n")

exact_type_pattern = re.compile(
    r"        requested_types = exact_type_counts\(\n"
    r"            total=total_questions,\n"
    r"            single_select_count=single_select_count,\n"
    r"            multi_select_count=multi_select_count,\n"
    r"            text_input_count=text_input_count,\n"
    r"            numerical_input_count=numerical_input_count,\n"
    r"        \)"
)
s, replaced = exact_type_pattern.subn("        requested_types = {'auto': int(total_questions)}", s)
if replaced != 2:
    raise SystemExit(f'Expected exactly two exact type quota blocks, got {replaced}')

requested_line = "        requested = self._target_counts_for_quiz(total_questions, difficulty_easy, difficulty_medium, difficulty_hard)\n"
if s.count(requested_line) != 2:
    raise SystemExit(f'Expected two difficulty target anchors, got {s.count(requested_line)}')
s = s.replace(requested_line, requested_line + "        requested_original = dict(requested)\n")

normal_anchor = "        availability = {\n            (diff, qtype): len(grouped_rows.get((diff, qtype), []))\n"
normal_insert = """        legacy_rebalanced = False
        legacy_mode = bool(rows) and all(is_legacy_quiz_question(questions[row.question_id]) for row in rows)
        if legacy_mode:
            order = ('easy', 'medium', 'hard')
            weights = {'easy': max(int(difficulty_easy or 0), 0), 'medium': max(int(difficulty_medium or 0), 0), 'hard': max(int(difficulty_hard or 0), 0)}
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
                    target_diff = min(candidates, key=lambda diff: (0 if weights[diff] > 0 else 1, effective[diff] / max(weights[diff], 1), order.index(diff)))
                    effective[target_diff] += 1
                    remaining -= 1
                    continue
                if flex_left > 0:
                    target_diff = min(order, key=lambda diff: (0 if weights[diff] > 0 else 1, effective[diff] / max(weights[diff], 1), order.index(diff)))
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
            legacy_rebalanced = effective != requested_original
            requested = effective
"""
if normal_anchor not in s:
    raise SystemExit('Normal planner availability anchor missing')
s = s.replace(normal_anchor, normal_insert + normal_anchor, 1)

final_anchor = "        availability = {\n            (diff, qtype): len(grouped.get((diff, qtype), []))\n"
final_insert = """        legacy_rebalanced = False
        legacy_entries = [entry for values in grouped.values() for entry in values] + [entry for values in flexible.values() for entry in values]
        legacy_mode = bool(legacy_entries) and all(
            str(getattr(entry['question'], 'source_type', '') or '').strip().lower() == 'legacy_quiz_excel'
            for entry in legacy_entries
        )
        if legacy_mode:
            order = ('easy', 'medium', 'hard')
            weights = {'easy': max(int(difficulty_easy or 0), 0), 'medium': max(int(difficulty_medium or 0), 0), 'hard': max(int(difficulty_hard or 0), 0)}
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
                    target_diff = min(candidates, key=lambda diff: (0 if weights[diff] > 0 else 1, effective[diff] / max(weights[diff], 1), order.index(diff)))
                    effective[target_diff] += 1
                    remaining -= 1
                    continue
                if flex_left > 0:
                    target_diff = min(order, key=lambda diff: (0 if weights[diff] > 0 else 1, effective[diff] / max(weights[diff], 1), order.index(diff)))
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
            legacy_rebalanced = effective != requested_original
            requested = effective
"""
if final_anchor not in s:
    raise SystemExit('Final planner availability anchor missing')
s = s.replace(final_anchor, final_insert + final_anchor, 1)

normal_warn_anchor = "        warnings: list[str] = []\n        unclassified_difficulty_count = sum(len(items) for items in flexible_rows.values())\n"
normal_warn_new = """        warnings: list[str] = []
        if legacy_rebalanced:
            warnings.append(
                f'Release CMS cũ không đủ phân bố độ khó đã yêu cầu; hệ thống tự cân lại '
                f'{requested_original} → {requested} nhưng vẫn giữ đúng {int(total_questions)} câu.'
            )
        unclassified_difficulty_count = sum(len(items) for items in flexible_rows.values())
"""
s = must_replace(s, normal_warn_anchor, normal_warn_new, 'normal legacy warning', 1)

final_warn_anchor = "        warnings: list[str] = []\n        unclassified_count = sum(len(items) for items in flexible.values())\n"
final_warn_new = """        warnings: list[str] = []
        if legacy_rebalanced:
            warnings.append(
                f'Final test CMS cũ không đủ phân bố độ khó đã yêu cầu; hệ thống tự cân lại '
                f'{requested_original} → {requested} nhưng vẫn giữ đúng {int(total_questions)} câu.'
            )
        unclassified_count = sum(len(items) for items in flexible.values())
"""
s = must_replace(s, final_warn_anchor, final_warn_new, 'final legacy warning', 1)

s = s.replace("'target_counts': {k.upper(): v for k, v in requested.items()},", "'target_counts': {k.upper(): v for k, v in requested_original.items()},")
s = s.replace("'question_type_target_counts': requested_types,", "'question_type_target_counts': {},")
s = re.sub(
    r"'question_type_coverage': \[\n\s*\{'question_type': qtype,.*?\n\s*for qtype in requested_types\n\s*\],",
    "'question_type_coverage': [],",
    s,
    flags=re.S,
)
s = s.replace("'matrix_target_counts': {f'{diff}:{qtype}': int(value) for (diff, qtype), value in matrix.items()},", "'matrix_target_counts': {diff.upper(): int(requested.get(diff, 0) or 0) for diff in ('easy', 'medium', 'hard')},")
s = s.replace('bank_release_difficulty_question_type_itembank_v4', 'bank_release_difficulty_itembank_v5')
s = s.replace('đúng quota difficulty × loại câu hỏi', 'đúng số câu theo độ khó hiệu lực')
s = s.replace('theo quota difficulty × loại câu hỏi', 'theo cấu hình độ khó')
s = s.replace('quota difficulty/loại hiện tại', 'cấu hình độ khó hiện tại')
write(p, s)


# 4) Quiz UI: number + difficulty + timer only. Exact bounded replacements.
p = 'frontend/app/bank/quiz/page.tsx'
s = read(p)
for line in (
    '  singleSelectCount: number\n', '  multiSelectCount: number\n', '  textInputCount: number\n', '  numericalInputCount: number\n',
    '    singleSelectCount: 15,\n', '    multiSelectCount: 0,\n', '    textInputCount: 0,\n', '    numericalInputCount: 0,\n',
    '    singleSelectCount: 30,\n',
):
    s = s.replace(line, '')

s = must_replace(s, "  const quizTypeTotal = quizConfig.singleSelectCount + quizConfig.multiSelectCount + quizConfig.textInputCount + quizConfig.numericalInputCount\n  const finalTypeTotal = finalConfig.singleSelectCount + finalConfig.multiSelectCount + finalConfig.textInputCount + finalConfig.numericalInputCount\n", '', 'quiz type totals', 1)

for owner in ('quizConfig', 'finalConfig', 'config'):
    block = (
        f"        single_select_count: {owner}.singleSelectCount,\n"
        f"        multi_select_count: {owner}.multiSelectCount,\n"
        f"        text_input_count: {owner}.textInputCount,\n"
        f"        numerical_input_count: {owner}.numericalInputCount,\n"
    )
    s = s.replace(block, '')

s = must_replace(s, "    const quizInvalid = quizDifficultyTotal !== 100 || quizTypeTotal !== quizConfig.totalQuestions\n    const finalInvalid = finalDifficultyTotal !== 100 || finalTypeTotal !== finalConfig.totalQuestions\n", "    const quizInvalid = quizDifficultyTotal !== 100\n    const finalInvalid = finalDifficultyTotal !== 100\n", 'modal validation', 1)

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
s = must_replace(s, "    const typeTotal = config.singleSelectCount + config.multiSelectCount + config.textInputCount + config.numericalInputCount\n", '', 'ConfigPanel type total', 1)

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
s = must_replace(s, "    const typeTotal = config.singleSelectCount + config.multiSelectCount + config.textInputCount + config.numericalInputCount\n    if (difficultyTotal !== 100 || typeTotal !== config.totalQuestions) {\n", "    if (difficultyTotal !== 100) {\n", 'blueprint validation', 1)

s = s.replace('quota/độ khó theo Blueprint', 'số câu/độ khó theo Blueprint')
s = s.replace('kiểm tra quota trên toàn bộ', 'kiểm tra khả năng đáp ứng trên toàn bộ')
s = s.replace('Release không đáp ứng quota câu hỏi đã chọn.', 'Release không đáp ứng số câu/độ khó đã chọn.')
s = s.replace('Kiểm tra quota với Release', 'Kiểm tra khả năng đáp ứng')
s = s.replace('Đang kiểm tra quota...', 'Đang kiểm tra...')
s = s.replace('Release đáp ứng quota.', 'Release đáp ứng cấu hình.')
s = s.replace('quota loại câu hỏi và khả năng đáp ứng của Release', 'số câu, tỷ lệ độ khó và khả năng đáp ứng của Release')
s = s.replace('Difficulty × type', 'Độ khó')
s = s.replace("{key.replace(':', ' · ')}", "{key.replace(':auto', '').toUpperCase()}")

old_preview = """          <div className=\"quiz-create-preview\"><b>Phạm vi xác nhận</b><span>{createModal.kind === 'all' ? `${readyRows.length} bài đủ điều kiện sẽ được tạo. Các dòng Không tạo hoặc còn thiếu điều kiện được bỏ qua.` : createModal.item.action === 'final_test' ? `Final test sẽ lấy candidate pool từ toàn bộ ${(createModal.item as any).source_release_ids?.length || 0} Release của các Bài đang chọn Tạo Quiz.` : `${createModal.item.chapter_title} sẽ được tạo bằng Release ${createModal.item.release_code || 'đã chọn'}.`}</span><small>Course ID: {normalizeOpenEdxCourseId(courseId) || '—'} · Quiz độ khó {quizConfig.easy}/{quizConfig.medium}/{quizConfig.hard} · loại {quizConfig.singleSelectCount}/{quizConfig.multiSelectCount}/{quizConfig.textInputCount}/{quizConfig.numericalInputCount} · Final loại {finalConfig.singleSelectCount}/{finalConfig.multiSelectCount}/{finalConfig.textInputCount}/{finalConfig.numericalInputCount}</small></div>
"""
new_preview = """          <div className=\"quiz-create-preview\"><b>Phạm vi xác nhận</b><span>{createModal.kind === 'all' ? `${readyRows.length} bài đủ điều kiện sẽ được tạo. Các dòng Không tạo hoặc còn thiếu điều kiện được bỏ qua.` : createModal.item.action === 'final_test' ? `Final test sẽ lấy candidate pool từ toàn bộ ${(createModal.item as any).source_release_ids?.length || 0} Release của các Bài đang chọn Tạo Quiz.` : `${createModal.item.chapter_title} sẽ được tạo bằng Release ${createModal.item.release_code || 'đã chọn'}.`}</span><small>Course ID: {normalizeOpenEdxCourseId(courseId) || '—'} · Quiz {quizConfig.totalQuestions} câu · độ khó {quizConfig.easy}/{quizConfig.medium}/{quizConfig.hard} · Final {finalConfig.totalQuestions} câu · độ khó {finalConfig.easy}/{finalConfig.medium}/{finalConfig.hard}</small></div>
"""
s = must_replace(s, old_preview, new_preview, 'modal preview type summary', 1)
s = must_replace(s, "          {(quizTypeTotal !== quizConfig.totalQuestions || finalTypeTotal !== finalConfig.totalQuestions) ? <div className=\"alert warning\">Tổng quota loại câu hỏi phải đúng bằng số câu của Quiz/Final tương ứng.</div> : null}\n", '', 'modal type warning', 1)

old_disabled = "disabled={busy || Boolean(creatingKey) || (createModal.kind === 'all' ? (quizDifficultyTotal !== 100 || finalDifficultyTotal !== 100 || quizTypeTotal !== quizConfig.totalQuestions || finalTypeTotal !== finalConfig.totalQuestions || !readyRows.length) : (createModal.item.action === 'final_test' ? (finalDifficultyTotal !== 100 || finalTypeTotal !== finalConfig.totalQuestions) : (quizDifficultyTotal !== 100 || quizTypeTotal !== quizConfig.totalQuestions)))}"
new_disabled = "disabled={busy || Boolean(creatingKey) || (createModal.kind === 'all' ? (quizDifficultyTotal !== 100 || finalDifficultyTotal !== 100 || !readyRows.length) : (createModal.item.action === 'final_test' ? finalDifficultyTotal !== 100 : quizDifficultyTotal !== 100))}"
s = must_replace(s, old_disabled, new_disabled, 'modal create button type validation', 1)

if any(token in s for token in ('Loại câu hỏi', 'singleSelectCount', 'multiSelectCount', 'textInputCount', 'numericalInputCount')):
    raise SystemExit('Question type quota references remain in quiz page')
write(p, s)


# 5) Frontend quiz API signatures no longer expose type quota fields.
p = 'frontend/lib/api.ts'
s = read(p)
for line in ('    single_select_count?: number | null;\n', '    multi_select_count?: number | null;\n', '    text_input_count?: number | null;\n', '    numerical_input_count?: number | null;\n'):
    s = s.replace(line, '')
write(p, s)


# 6) Udemy: remove top banner and top import CTA, keep progress-panel management action below.
p = 'frontend/app/student-management/classes/[classId]/page.tsx'
s = read(p)
old_primary = "      primaryAction={isUdemyClass ? (classInfo?.subject_delivery_id ? <Link className=\"btn primary\" href={udemyDashboardHref}>Import / kế hoạch Udemy</Link> : undefined) : <Link className=\"btn primary\" href={behaviorHref}>Phân tích học tập</Link>}\n"
new_primary = "      primaryAction={!isUdemyClass ? <Link className=\"btn primary\" href={behaviorHref}>Phân tích học tập</Link> : undefined}\n"
s = must_replace(s, old_primary, new_primary, 'Udemy header CTA', 1)
old_notice = "      {isUdemyClass ? <InlineNotice notice={{ ...noticeInfo('Điểm và tiến độ lấy từ file Udemy. Tiến độ từng sinh viên được hiển thị ngay bên dưới; chỉ mở quản lý môn khi cần import file hoặc chỉnh kế hoạch.', 'Lớp đang vận hành trên Udemy'), actionHref: classInfo?.subject_delivery_id ? udemyDashboardHref : undefined, actionLabel: classInfo?.subject_delivery_id ? 'Import / kế hoạch Udemy' : undefined }} /> : null}\n"
s = must_replace(s, old_notice, '', 'Udemy top notice', 1)
write(p, s)


# 7) AP Sync button wording.
p = 'frontend/app/ap-sync/page.tsx'
s = read(p)
s = must_replace(s, "{loadingOptions ? 'Đang tải...' : 'Làm mới dữ liệu'}", "{loadingOptions ? 'Đang cập nhật...' : 'Cập nhật cơ sở'}", 'AP refresh label', 1)
s = s.replace("hint: 'Nhập thủ công tại trang Cơ sở'", "hint: 'Lấy từ API theo hệ POLY/PTCD'")
write(p, s)


# 8) RBAC: admin full rights + all-campus owner operational bundle only when scope is all campuses.
p = 'backend/app/services/business_rbac.py'
s = read(p)
permission_anchor = "\nLEGACY_PERMISSION_BRIDGE: dict[str, set[str]] = {\n"
extra_permissions = """
CAMPUS_OWNER_ALL_CAMPUS_PERMISSIONS: set[str] = {
    'department.manage_all', 'subject.create', 'subject.update', 'course.sync',
    'user.manage_all', 'rbac.view',
}


def _is_all_campus_assignment(assignment: Any) -> bool:
    role_code = str(getattr(assignment, 'role_code', '') or '').upper()
    scope_type = str(getattr(assignment, 'scope_type', '') or '').upper()
    scope_id = str(getattr(assignment, 'scope_id', '') or '').strip()
    return role_code in {CAMPUS_OWNER, CAMPUS_MANAGER} and (
        scope_type == 'SYSTEM' or (scope_type == 'CAMPUS' and scope_id == '*')
    )

"""
s = must_replace(s, permission_anchor, '\n' + extra_permissions + 'LEGACY_PERMISSION_BRIDGE: dict[str, set[str]] = {\n', 'all-campus permission anchor', 1)

old_identity = """    def active_assignments_for_identity(self, user_id: str | None, email: str | None = None, username: str | None = None) -> list[UserRoleAssignment]:
        values = {str(item).strip() for item in [user_id, username] if str(item or '').strip()}
        filters = []
        if values:
            filters.append(UserRoleAssignment.user_id.in_(sorted(values)))
        if email:
            filters.append(UserRoleAssignment.email == email)
        if not filters:
            return []
        return self.active_assignments_query().filter(or_(*filters)).all()
"""
new_identity = """    def active_assignments_for_identity(self, user_id: str | None, email: str | None = None, username: str | None = None) -> list[UserRoleAssignment]:
        values = {
            str(item).strip().lower()
            for item in [user_id, username, email]
            if str(item or '').strip()
        }
        filters = []
        if values:
            filters.append(func.lower(UserRoleAssignment.user_id).in_(sorted(values)))
            filters.append(func.lower(UserRoleAssignment.email).in_(sorted(values)))
        if not filters:
            return []
        return self.active_assignments_query().filter(or_(*filters)).all()
"""
s = must_replace(s, old_identity, new_identity, 'case-insensitive RBAC identity', 1)

old_effective = """    def effective_permissions_for_user(self, user: Any) -> set[str]:
        permissions: set[str] = set()
        if self.is_system_admin(user):
            permissions.update(ROLE_PERMISSIONS[SYSTEM_ADMIN])
        for assignment in self.active_assignments_for_actor(user):
            if assignment.role_code == SYSTEM_ADMIN and not self.is_system_admin(user):
                continue
            permissions.update(ROLE_PERMISSIONS.get(assignment.role_code, set()))
        if self._has_ap_teacher_assignment(user):
            permissions.update(ROLE_PERMISSIONS[TEACHER_ASSIGNED])
        return permissions
"""
new_effective = """    def effective_permissions_for_user(self, user: Any) -> set[str]:
        permissions: set[str] = set()
        system_admin = self.is_system_admin(user)
        if system_admin:
            permissions.update(ROLE_PERMISSIONS[SYSTEM_ADMIN])
            permissions.update(
                str(row.code).strip()
                for row in self.db.query(RBACPermission).all()
                if str(getattr(row, 'code', '') or '').strip()
            )
        for assignment in self.active_assignments_for_actor(user):
            if assignment.role_code == SYSTEM_ADMIN and not system_admin:
                continue
            permissions.update(ROLE_PERMISSIONS.get(assignment.role_code, set()))
            if _is_all_campus_assignment(assignment):
                permissions.update(CAMPUS_OWNER_ALL_CAMPUS_PERMISSIONS)
        if self._has_ap_teacher_assignment(user):
            permissions.update(ROLE_PERMISSIONS[TEACHER_ASSIGNED])
        return permissions
"""
s = must_replace(s, old_effective, new_effective, 'effective permissions', 1)

serialize_anchor = "    def serialize_assignment(self, item: UserRoleAssignment) -> dict[str, Any]:\n"
serialize_helper = """    @staticmethod
    def assignment_permission_codes(item: UserRoleAssignment) -> list[str]:
        permissions = set(ROLE_PERMISSIONS.get(item.role_code, set()))
        if _is_all_campus_assignment(item):
            permissions.update(CAMPUS_OWNER_ALL_CAMPUS_PERMISSIONS)
        return sorted(permissions)

"""
s = must_replace(s, serialize_anchor, serialize_helper + serialize_anchor, 'assignment permission helper', 1)
s = must_replace(s, "            'permission_codes': sorted(ROLE_PERMISSIONS.get(item.role_code, set())),\n", "            'permission_codes': self.assignment_permission_codes(item),\n", 'serialized assignment permissions', 1)
write(p, s)

p = 'frontend/context/AppContext.tsx'
s = read(p)
s = must_replace(s, "  view_dashboard: ['bank.view', 'audit.view'],\n", "  view_dashboard: ['bank.view', 'audit.view', 'academic.view', 'view_training_reports'],\n", 'frontend dashboard permission bridge', 1)
write(p, s)


# 9) Project-wide structural spacing/layout contract loaded last.
p = 'frontend/app/layout.tsx'
s = read(p)
anchor = "import '../styles/subject-management-udemy.css'\n"
if 'project-spacing-contract.css' not in s:
    s = must_replace(s, anchor, anchor + "import '../styles/project-spacing-contract.css'\n", 'spacing contract import', 1)
write(p, s)

css = """/* ACMS project-wide spacing/layout contract. Loaded last intentionally.
   Structural only: spacing, flow, overflow and responsive behavior. */
:root {
  --acms-space-1: 4px;
  --acms-space-2: 8px;
  --acms-space-3: 12px;
  --acms-space-4: 16px;
  --acms-space-5: 20px;
  --acms-space-6: 24px;
}

*, *::before, *::after { box-sizing: border-box; }

.app-main, .app-content, .enterprise-content, .page-root, .page-stack,
.enterprise-standard-page, .bank-contract-page, .workspace-section,
.popup-action-panel, .enterprise-panel, .academic-unified-card,
.training-workspace-section, .bank-section-body { min-width: 0; }

.page-stack, .bank-multipage, .enterprise-standard-page,
.quiz-creation-workbench, .ap-sync-page { gap: var(--acms-space-5); }

.section-heading, .enterprise-section-heading, .workspace-section-header,
.enterprise-content-section-head, .toolbar, .toolbar-actions, .section-actions,
.header-actions, .button-row, .filter-actions, .settings-actions,
.class-action-row { gap: var(--acms-space-3); }

.toolbar, .toolbar-actions, .section-actions, .header-actions,
.button-row, .filter-actions, .settings-actions, .class-action-row,
.accessible-dialog-footer { flex-wrap: wrap; }

.settings-form-grid, .quiz-small-grid, .option-grid,
.compact-filter-grid, .filter-grid, .form-grid, .quiz-modal-grid {
  column-gap: var(--acms-space-4);
  row-gap: var(--acms-space-3);
}

.table-scroll, .enterprise-table-scroll, .data-table-scroll,
.enterprise-data-table-scroll { max-width: 100%; min-width: 0; overflow-x: auto; overscroll-behavior-inline: contain; }

.accessible-dialog-surface { max-width: min(96vw, 1180px); max-height: min(92vh, 960px); min-width: 0; }
.accessible-dialog-header, .accessible-dialog-footer { gap: var(--acms-space-3); }
.accessible-dialog-body { min-width: 0; overflow: auto; overscroll-behavior: contain; }
.quiz-modal-grid { align-items: start; }
.quiz-timer-subhead { margin-top: var(--acms-space-4); }

@media (max-width: 960px) {
  .quiz-modal-grid, .settings-form-grid, .form-grid { grid-template-columns: minmax(0, 1fr) !important; }
  .page-stack, .bank-multipage, .enterprise-standard-page { gap: var(--acms-space-4); }
}

@media (max-width: 640px) {
  .toolbar, .toolbar-actions, .section-actions, .header-actions,
  .button-row, .filter-actions, .settings-actions, .class-action-row,
  .accessible-dialog-footer { width: 100%; }
}
"""
write('frontend/styles/project-spacing-contract.css', css)

print('patch-v4 applied')
