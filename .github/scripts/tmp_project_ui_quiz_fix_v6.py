from pathlib import Path


def read(path: str) -> str:
    return Path(path).read_text(encoding='utf-8')


def write(path: str, text: str) -> None:
    Path(path).write_text(text, encoding='utf-8')


def replace_exact(path: str, old: str, new: str, *, count: int = 1, label: str) -> None:
    text = read(path)
    actual = text.count(old)
    if actual != count:
        raise SystemExit(f'{label}: expected {count} anchors, got {actual}')
    write(path, text.replace(old, new, count))


# 1) Routes must not read fields removed from the Pydantic quiz request contract.
p = 'backend/app/api/routes/question_bank_v2.py'
s = read(p)
type_payload = """            single_select_count=payload.single_select_count,
            multi_select_count=payload.multi_select_count,
            text_input_count=payload.text_input_count,
            numerical_input_count=payload.numerical_input_count,
"""
if s.count(type_payload) != 2:
    raise SystemExit(f'quiz route type payload: expected 2, got {s.count(type_payload)}')
s = s.replace(type_payload, '')
write(p, s)


# 2) Remove the dead request mixin and all user-facing type-quota wording.
p = 'backend/app/schemas/question_bank.py'
s = read(p)
mixin = """class QuestionTypeQuotaMixin(BaseModel):
    single_select_count: int | None = Field(default=None, ge=0, le=200)
    multi_select_count: int | None = Field(default=None, ge=0, le=200)
    text_input_count: int | None = Field(default=None, ge=0, le=200)
    numerical_input_count: int | None = Field(default=None, ge=0, le=200)

    def validate_type_quota(self, total: int) -> None:
        values = [self.single_select_count, self.multi_select_count, self.text_input_count, self.numerical_input_count]
        if all(value is None for value in values):
            return
        resolved = [0 if value is None else int(value) for value in values]
        if sum(resolved) != int(total):
            raise ValueError(f'Tổng quota theo loại câu hỏi phải bằng tổng số câu ({sum(resolved)}/{int(total)}).')


"""
if s.count(mixin) != 1:
    raise SystemExit(f'QuestionTypeQuotaMixin block: expected 1, got {s.count(mixin)}')
s = s.replace(mixin, '')
s = s.replace(
    "raise ValueError('Blueprint theo quota loại câu hỏi hiện yêu cầu pick_count_per_slot=1.')",
    "raise ValueError('Blueprint hiện yêu cầu pick_count_per_slot=1 để giữ đúng số câu mỗi slot.')",
)
write(p, s)


# 3) Blueprint creation keeps legacy nullable DB columns only for migration compatibility;
# new blueprints never populate a hidden exact-type quota.
p = 'backend/app/services/question_bank_service.py'
s = read(p)
s = s.replace('from app.services.question_type_quota import exact_type_counts\n', '')
old = """        if int(pick_count_per_slot or 1)!=1: raise ValueError('Blueprint theo quota loại câu hỏi yêu cầu pick_count_per_slot=1.')
        type_counts=exact_type_counts(total=total_questions,single_select_count=single_select_count,multi_select_count=multi_select_count,text_input_count=text_input_count,numerical_input_count=numerical_input_count)
        item=QuizBlueprint(id=str(uuid.uuid4()),subject_id=subject_id,chapter_id=chapter_id,subject_offering_id=subject_offering_id,title=title,total_questions=total_questions,difficulty_easy=difficulty_easy,difficulty_medium=difficulty_medium,difficulty_hard=difficulty_hard,single_select_count=type_counts['single_select'],multi_select_count=type_counts['multi_select'],text_input_count=type_counts['text_input'],numerical_input_count=type_counts['numerical_input'],max_families_per_bank=max_families_per_bank,pick_count_per_slot=1)
"""
new = """        if int(pick_count_per_slot or 1)!=1: raise ValueError('Blueprint hiện yêu cầu pick_count_per_slot=1 để giữ đúng số câu mỗi slot.')
        # Legacy nullable type-count columns remain in the table for rolling-upgrade compatibility only.
        # New blueprints deliberately leave them NULL: response type is determined by the Release questions.
        item=QuizBlueprint(id=str(uuid.uuid4()),subject_id=subject_id,chapter_id=chapter_id,subject_offering_id=subject_offering_id,title=title,total_questions=total_questions,difficulty_easy=difficulty_easy,difficulty_medium=difficulty_medium,difficulty_hard=difficulty_hard,single_select_count=None,multi_select_count=None,text_input_count=None,numerical_input_count=None,max_families_per_bank=max_families_per_bank,pick_count_per_slot=1)
"""
if s.count(old) != 1:
    raise SystemExit(f'create_quiz_blueprint type quota block: expected 1, got {s.count(old)}')
s = s.replace(old, new)
write(p, s)


# 4) Quiz planner cleanup: no type-quota helper/import, no type-quota messages,
# and requested/effective difficulty remain distinguishable after legacy rebalancing.
p = 'backend/app/services/question_bank/quiz_creation.py'
s = read(p)
s = s.replace('from app.services.question_content import normalize_question_type\n', '')
s = s.replace('    exact_type_counts,\n', '')
s = s.replace(
    "'target_counts': {key.upper(): value for key, value in requested.items()},",
    "'target_counts': {key.upper(): value for key, value in requested_original.items()},",
)
s = s.replace('Hãy tăng số câu Final hoặc điều chỉnh quota loại/độ khó.', 'Hãy tăng số câu Final hoặc điều chỉnh tỷ lệ độ khó.')
s = s.replace('được phân bổ linh hoạt vào quota Final test.', 'được phân bổ linh hoạt vào cấu hình độ khó Final test.')
s = s.replace("'summary': 'Final test dùng toàn bộ Release nguồn làm candidate pool theo quota; mỗi ItemBank chỉ chứa component của đúng một Library.'", "'summary': 'Final test dùng toàn bộ Release nguồn làm candidate pool theo cấu hình độ khó; mỗi ItemBank chỉ chứa component của đúng một Library.'")
s = s.replace("f'learner nhận đúng {int(total_questions)} câu theo quota.'", "f'learner nhận đúng {int(total_questions)} câu theo cấu hình.'")
s = s.replace("f'Final test không đủ câu {diff.upper()} · {qtype} cho quota {target}.'", "f'Final test không đủ câu {diff.upper()} cho cấu hình {target} câu.'")
s = s.replace("f'cho {cell[\"difficulty\"].upper()} · {cell[\"question_type\"]}, cần pick {pick_count}.'", "f'cho {cell[\"difficulty\"].upper()}, cần pick {pick_count}.'")
s = s.replace("raise ValueError(f'Final test planner tạo {actual_total}/{int(total_questions)} câu; từ chối tạo cấu hình lệch quota.')", "raise ValueError(f'Final test planner tạo {actual_total}/{int(total_questions)} câu; từ chối tạo cấu hình lệch số câu.')")
s = s.replace('được phân bổ linh hoạt vào quota Easy/Medium/Hard.', 'được phân bổ linh hoạt vào cấu hình Easy/Medium/Hard.')
if 'quota loại' in s:
    raise SystemExit('quiz_creation.py still contains question-type quota wording')
write(p, s)


# 5) All-campus owner gets the requested operational/catalog/RBAC pages, but not
# global user.manage_all (which would also unlock unrelated user analytics/settings).
p = 'backend/app/services/business_rbac.py'
s = read(p)
old = """CAMPUS_OWNER_ALL_CAMPUS_PERMISSIONS: set[str] = {
    'department.manage_all', 'subject.create', 'subject.update', 'course.sync',
    'user.manage_all', 'rbac.view',
}
"""
new = """CAMPUS_OWNER_ALL_CAMPUS_PERMISSIONS: set[str] = {
    'department.manage_all', 'subject.create', 'subject.update', 'course.sync',
    'rbac.view',
}
"""
if s.count(old) != 1:
    raise SystemExit(f'all-campus permission bundle: expected 1, got {s.count(old)}')
s = s.replace(old, new)
write(p, s)


# 6) Focused regression tests for the all-campus role distinction and future admin permissions.
p = 'backend/app/tests/test_rbac_admin_campus_owner_contract.py'
write(p, """from types import SimpleNamespace

from app.models.rbac import RBACPermission
from app.services.business_rbac import (
    BusinessRBACService,
    CAMPUS_OWNER_ALL_CAMPUS_PERMISSIONS,
    _is_all_campus_assignment,
)


def assignment(scope_type: str, scope_id: str, role_code: str = 'CAMPUS_OWNER'):
    return SimpleNamespace(role_code=role_code, scope_type=scope_type, scope_id=scope_id)


def test_only_all_campus_owner_gets_small_campus_operations_bundle():
    assert _is_all_campus_assignment(assignment('CAMPUS', '*')) is True
    assert _is_all_campus_assignment(assignment('SYSTEM', '*')) is True
    assert _is_all_campus_assignment(assignment('CAMPUS', 'HN')) is False
    assert 'department.manage_all' in CAMPUS_OWNER_ALL_CAMPUS_PERMISSIONS
    assert 'rbac.view' in CAMPUS_OWNER_ALL_CAMPUS_PERMISSIONS
    assert 'user.manage_all' not in CAMPUS_OWNER_ALL_CAMPUS_PERMISSIONS


class _Query:
    def all(self):
        return [SimpleNamespace(code='future.permission')]


class _Db:
    def query(self, model):
        assert model is RBACPermission
        return _Query()


def test_system_admin_effective_permissions_include_future_catalog_permissions(monkeypatch):
    service = BusinessRBACService(_Db())
    monkeypatch.setattr(service, 'is_system_admin', lambda user: True)
    monkeypatch.setattr(service, 'active_assignments_for_actor', lambda user: [])
    monkeypatch.setattr(service, '_has_ap_teacher_assignment', lambda user: False)
    permissions = service.effective_permissions_for_user(SimpleNamespace())
    assert 'future.permission' in permissions
    assert 'rbac.view' in permissions
""")

print('patch-v6 applied')
