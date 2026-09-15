from pathlib import Path


def read(path: str) -> str:
    return Path(path).read_text(encoding='utf-8')


def write(path: str, text: str) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(text, encoding='utf-8')


def replace(path: str, old: str, new: str, *, count: int | None = None) -> None:
    text = read(path)
    actual = text.count(old)
    if actual == 0:
        raise SystemExit(f'MISSING PATCH TARGET: {path}: {old[:120]!r}')
    if count is not None and actual != count:
        raise SystemExit(f'PATCH COUNT MISMATCH {path}: expected {count}, got {actual}: {old[:120]!r}')
    write(path, text.replace(old, new))


write('backend/app/core/privacy.py', '''from __future__ import annotations

import re
from typing import Any

_EMAIL_PATTERN = re.compile(r'^[^\\s@]+@[^\\s@]+\\.[^\\s@]+$')


def normalize_email(value: Any) -> str | None:
    email = str(value or '').strip().lower()
    return email if email and _EMAIL_PATTERN.fullmatch(email) else None


def mask_email(value: Any) -> str | None:
    """Return an idempotent display-safe email value."""
    email = normalize_email(value)
    if not email:
        return None
    local, domain = email.rsplit('@', 1)
    if '***' in local:
        return email
    masked_local = f'{local[:1]}***' if len(local) <= 1 else f'{local[:1]}***{local[-1:]}'
    return f'{masked_local}@{domain}'
''')

write('frontend/lib/privacy.ts', '''export function maskEmailForDisplay(value?: string | null): string {
  const email = String(value || '').trim().toLowerCase()
  if (!email) return ''
  const at = email.lastIndexOf('@')
  if (at <= 0 || at === email.length - 1) return '***'
  const local = email.slice(0, at)
  const domain = email.slice(at + 1)
  if (local.includes('***')) return `${local}@${domain}`
  const maskedLocal = local.length <= 1
    ? `${local.slice(0, 1)}***`
    : `${local.slice(0, 1)}***${local.slice(-1)}`
  return `${maskedLocal}@${domain}`
}
''')

# Progress reminder content, shared privacy helper and trusted CMS link.
p = 'backend/app/services/academic/progress_email.py'
replace(p,
    "from app.core.config import settings\nfrom app.core.rbac import UserContext\n",
    "from app.core.config import settings\nfrom app.core.privacy import mask_email, normalize_email\nfrom app.core.rbac import UserContext\n",
    count=1,
)
replace(p,
'''def normalize_recipient_email(value: Any) -> str | None:
    email = str(value or '').strip().lower()
    return email if email and _EMAIL_PATTERN.fullmatch(email) else None


def mask_recipient_email(value: Any) -> str | None:
    email = normalize_recipient_email(value)
    if not email:
        return None
    local, domain = email.rsplit('@', 1)
    if len(local) <= 1:
        masked_local = f'{local[:1]}***'
    else:
        masked_local = f'{local[:1]}***{local[-1:]}'
    return f'{masked_local}@{domain}'
''',
'''def normalize_recipient_email(value: Any) -> str | None:
    return normalize_email(value)


def mask_recipient_email(value: Any) -> str | None:
    return mask_email(value)
''', count=1)
replace(p,
'''def plain_text_mail_template(value: str) -> str:
    """Convert teacher-authored plain text to conservative email HTML."""
    escaped = html.escape(str(value or '').strip(), quote=True)
    paragraphs = [item.strip() for item in re.split(r'\\n\\s*\\n', escaped) if item.strip()]
    if not paragraphs:
        return ''
    rendered = ''.join(f'<p>{item.replace(chr(10), "<br>")}</p>' for item in paragraphs)
    return f'<div style="font-family:Arial,sans-serif;font-size:14px;line-height:1.6;color:#172033">{rendered}</div>'
''',
'''CMS_LEARNER_DASHBOARD_URL = 'https://edx.cms.fpl.edu.vn/learner-dashboard/'


def plain_text_mail_template(value: str) -> str:
    """Escape authored text, then link the trusted literal CMS destination."""
    escaped = html.escape(str(value or '').strip(), quote=True)
    escaped = re.sub(
        r'\\bCMS\\b',
        f'<a href="{CMS_LEARNER_DASHBOARD_URL}" target="_blank" rel="noopener noreferrer">CMS</a>',
        escaped,
    )
    paragraphs = [item.strip() for item in re.split(r'\\n\\s*\\n', escaped) if item.strip()]
    if not paragraphs:
        return ''
    rendered = ''.join(f'<p>{item.replace(chr(10), "<br>")}</p>' for item in paragraphs)
    return f'<div style="font-family:Arial,sans-serif;font-size:14px;line-height:1.6;color:#172033">{rendered}</div>'
''', count=1)
replace(p,
    '''        return f'[AI Server] Nhắc tiến độ học tập{f" - {scope}" if scope else ""}'\n''',
    '''        return f'[CMS Server] Nhắc nhở tiến độ học tập{f" - {scope}" if scope else ""}'\n''',
    count=1,
)
replace(p,
'''        return (
            'Xin chào {{maHs}},\\n\\n'
            f'AI Server ghi nhận bạn đang chậm một hoặc nhiều mốc Quiz của {subject_label}, lớp {class_code}. '
            'Vui lòng vào CMS để kiểm tra và hoàn thành các nội dung còn thiếu.\\n\\n'
            'Deadline Quiz chỉ là mốc nhắc tiến độ học tập, không phải kết luận cấm thi. '
            'Điều kiện dự thi chỉ được đánh giá sau ngày học cuối chính thức của lớp/block.\\n\\n'
            'Nếu bạn vừa hoàn thành, dữ liệu sẽ được cập nhật ở lần đồng bộ tiếp theo.\\n\\n'
            'Trân trọng,\\nGiảng viên phụ trách'
        )
''',
'''        return (
            'Xin chào {{tên sinh viên}}-{{maHs}},\\n\\n'
            f'AI Server ghi nhận bạn đang chậm một hoặc nhiều mốc Quiz của {subject_label}, lớp {class_code}. '
            'Vui lòng vào CMS để kiểm tra và hoàn thành các nội dung còn thiếu.\\n\\n'
            'Nếu bạn vừa hoàn thành, dữ liệu sẽ được cập nhật ở lần đồng bộ tiếp theo.\\n\\n'
            'Trân trọng,\\nGiảng viên phụ trách'
        )
''', count=1)

# Frontend display masking.
for path, old, new in [
    ('frontend/app/student-management/classes/[classId]/page.tsx',
     "import { formatVNDate, formatVNDateTime, formatVNTimeDate } from '../../../../lib/time'\n",
     "import { formatVNDate, formatVNDateTime, formatVNTimeDate } from '../../../../lib/time'\nimport { maskEmailForDisplay } from '../../../../lib/privacy'\n"),
    ('frontend/app/student-management/classes/[classId]/page.tsx',
     "<small>{student.email || 'Chưa có email'}</small>",
     "<small>{maskEmailForDisplay(student.email) || 'Chưa có email'}</small>"),
    ('frontend/app/subject-management/[deliveryId]/udemy/page.tsx',
     "import { useAppContext } from '../../../../context/AppContext'\n",
     "import { useAppContext } from '../../../../context/AppContext'\nimport { maskEmailForDisplay } from '../../../../lib/privacy'\n"),
    ('frontend/app/subject-management/[deliveryId]/udemy/page.tsx',
     '<small>{row.email}</small>', '<small>{maskEmailForDisplay(row.email)}</small>'),
    ('frontend/components/student-management/UdemyClassProgressPanel.tsx',
     'import { getUdemyProgressStudents } from "../../lib/api";\n',
     'import { getUdemyProgressStudents } from "../../lib/api";\nimport { maskEmailForDisplay } from "../../lib/privacy";\n'),
    ('frontend/components/student-management/UdemyClassProgressPanel.tsx',
     '<small>{row.display_name || row.email}</small>\n              {row.email ? <small>{row.email}</small> : null}',
     '<small>{row.display_name || maskEmailForDisplay(row.email)}</small>\n              {row.email ? <small>{maskEmailForDisplay(row.email)}</small> : null}'),
    ('frontend/app/teacher-management/TeacherManagementPlatformPage.tsx',
     'import { useDebouncedValue } from "../../lib/useDebouncedValue";\n',
     'import { useDebouncedValue } from "../../lib/useDebouncedValue";\nimport { maskEmailForDisplay } from "../../lib/privacy";\n'),
    ('frontend/app/teacher-management/TeacherManagementPlatformPage.tsx',
     'item.teacher_email ? ` · ${item.teacher_email}` : ""',
     'item.teacher_email ? ` · ${maskEmailForDisplay(item.teacher_email)}` : ""'),
    ('frontend/app/users/page.tsx',
     "import { useDebouncedValue } from '../../lib/useDebouncedValue'\n",
     "import { useDebouncedValue } from '../../lib/useDebouncedValue'\nimport { maskEmailForDisplay } from '../../lib/privacy'\n"),
    ('frontend/app/users/page.tsx',
     "<small>{item.email || 'Chưa có email'}</small>",
     "<small>{maskEmailForDisplay(item.email) || 'Chưa có email'}</small>"),
]:
    replace(path, old, new, count=1)

# Academic API output serializers.
p = 'backend/app/schemas/academic.py'
replace(p, 'from pydantic import BaseModel, Field, field_validator\n',
        'from pydantic import BaseModel, Field, field_validator, field_serializer\n\nfrom app.core.privacy import mask_email\n', count=1)
replace(p,
'''    model_config = {'from_attributes': True}


class AcademicTrainingPolicyOut(BaseModel):
''',
'''    @field_serializer('email')
    def serialize_email(self, value: str | None) -> str | None:
        return mask_email(value)

    model_config = {'from_attributes': True}


class AcademicTrainingPolicyOut(BaseModel):
''', count=1)
text = read(p)
marker = "    assignment_score_10: float | None = None\n\n\nclass AcademicClassListOut(BaseModel):\n"
if marker not in text:
    raise SystemExit('AcademicClassStudentOut serializer marker missing')
text = text.replace(marker,
    "    assignment_score_10: float | None = None\n\n    @field_serializer('openedx_email')\n    def serialize_openedx_email(self, value: str | None) -> str | None:\n        return mask_email(value)\n\n\nclass AcademicClassListOut(BaseModel):\n", 1)
write(p, text)
text = read(p)
marker = "    diagnostic: str | None = None\n\n\nclass UdemyProgressStudentListOut(BaseModel):\n"
if marker not in text:
    raise SystemExit('UdemyProgressStudentOut serializer marker missing')
text = text.replace(marker,
    "    diagnostic: str | None = None\n\n    @field_serializer('email')\n    def serialize_email(self, value: str | None) -> str | None:\n        return mask_email(value)\n\n\nclass UdemyProgressStudentListOut(BaseModel):\n", 1)
write(p, text)

# RBAC output serializers; raw input request models are intentionally unchanged.
p = 'backend/app/schemas/rbac.py'
replace(p, 'from pydantic import BaseModel, Field, field_validator\n',
        'from pydantic import BaseModel, Field, field_validator, field_serializer\n\nfrom app.core.privacy import mask_email\n', count=1)
text = read(p)
marker = "    class Config:\n        from_attributes = True\n\n\nclass RoleAssignmentListOut(BaseModel):\n"
if marker not in text:
    raise SystemExit('RoleAssignmentOut serializer marker missing')
text = text.replace(marker,
    "    @field_serializer('email')\n    def serialize_email(self, value: str | None) -> str | None:\n        return mask_email(value)\n\n    class Config:\n        from_attributes = True\n\n\nclass RoleAssignmentListOut(BaseModel):\n", 1)
marker = "    assignment: RoleAssignmentOut | None = None\n\n\nclass RoleAssignmentImportOut(BaseModel):\n"
if marker not in text:
    raise SystemExit('RoleAssignmentImportRowOut serializer marker missing')
text = text.replace(marker,
    "    assignment: RoleAssignmentOut | None = None\n\n    @field_serializer('email')\n    def serialize_email(self, value: str | None) -> str | None:\n        return mask_email(value)\n\n\nclass RoleAssignmentImportOut(BaseModel):\n", 1)
write(p, text)

# Re-export shared mask from the existing Open edX helper module.
p = 'backend/app/services/openedx_student_insight.py'
replace(p, 'from app.core.config import settings\n', 'from app.core.config import settings\nfrom app.core.privacy import mask_email\n', count=1)
replace(p,
'''def mask_email(value: Any) -> str | None:
    raw = str(value or '').strip()
    if not raw or '@' not in raw:
        return raw or None
    name, domain = raw.split('@', 1)
    if len(name) <= 2:
        masked = name[0:1] + '***'
    else:
        masked = f'{name[:2]}***{name[-1:]}'
    return f'{masked}@{domain}'


''', '', count=1)

# Student JSON output already imports mask_email through openedx_student_insight.
p = 'backend/app/services/academic_service.py'
replace(p, "            'email': student.email,\n", "            'email': mask_email(student.email),\n", count=1)
replace(p, "            'openedx_email': mapping.openedx_email if mapping else None,\n",
        "            'openedx_email': mask_email(mapping.openedx_email) if mapping else None,\n", count=1)

# Teacher report presentation/cache rows.
p = 'backend/app/services/academic/teacher_report.py'
text = read(p)
if 'from app.core.privacy import mask_email' not in text:
    anchor = 'from app.core.config import settings\n'
    if anchor in text:
        text = text.replace(anchor, anchor + 'from app.core.privacy import mask_email\n', 1)
    else:
        token = 'from app.models.academic import (\n'
        text = text.replace(token, 'from app.core.privacy import mask_email\n' + token, 1)
text = text.replace("'teacher_email': teacher.email", "'teacher_email': mask_email(teacher.email)")
text = text.replace("'student_email': student.email", "'student_email': mask_email(student.email)")
write(p, text)

# Learning analytics fallback roster.
p = 'backend/app/services/learning_analytics/analytics_core_service.py'
text = read(p)
if 'from app.core.privacy import mask_email' not in text:
    token = 'from app.models.academic import (\n'
    text = text.replace(token, 'from app.core.privacy import mask_email\n' + token, 1)
text = text.replace("                'email': item.email,\n", "                'email': mask_email(item.email),\n", 1)
write(p, text)

# Identity diagnostics.
p = 'backend/app/services/academic/identity.py'
text = read(p)
if 'from app.core.privacy import mask_email' not in text:
    token = 'from app.models.academic import (\n'
    text = text.replace(token, 'from app.core.privacy import mask_email\n' + token, 1)
text = text.replace("                'email': student.email,\n", "                'email': mask_email(student.email),\n", 1)
write(p, text)

# Review actor labels.
p = 'backend/app/services/bank_search.py'
text = read(p)
if 'from app.core.privacy import mask_email' not in text:
    token = 'from app.models.'
    idx = text.find(token)
    if idx < 0:
        raise SystemExit('bank_search import anchor missing')
    text = text[:idx] + 'from app.core.privacy import mask_email\n' + text[idx:]
text = text.replace('            label = row.email or row.user_id\n', '            label = mask_email(row.email) or row.user_id\n', 1)
write(p, text)

# Udemy outbound API and spreadsheets. Matching/storage remains raw internally.
p = 'backend/app/services/academic/udemy_progress.py'
text = read(p)
if 'from app.core.privacy import mask_email' not in text:
    text = text.replace('from app.core.json_safe import json_safe_value\n', 'from app.core.json_safe import json_safe_value\nfrom app.core.privacy import mask_email\n', 1)
text = text.replace("                row.row_number, subject.subject_code, row.email or '', row.display_name or '',\n",
                    "                row.row_number, subject.subject_code, mask_email(row.email) or '', row.display_name or '',\n", 1)
text = text.replace("            'email': snapshot.email,\n", "            'email': mask_email(snapshot.email) or '',\n", 1)
text = text.replace("index, item.get('student_code'), item.get('student_username'), item.get('display_name'), item.get('email'),",
                    "index, item.get('student_code'), item.get('student_username'), item.get('display_name'), mask_email(item.get('email')),")
text = text.replace("warning_index, item.get('student_code'), item.get('student_username'), item.get('display_name'), item.get('email'),",
                    "warning_index, item.get('student_code'), item.get('student_username'), item.get('display_name'), mask_email(item.get('email')),")
write(p, text)

# Excel defense-in-depth.
p = 'backend/app/api/routes/academic.py'
text = read(p)
if 'from app.core.privacy import mask_email' not in text:
    text = text.replace('from app.core.json_safe import json_safe_value\n', 'from app.core.json_safe import json_safe_value\nfrom app.core.privacy import mask_email\n', 1)
text = text.replace("item.get('teacher_username'), item.get('teacher_email'),\n",
                    "item.get('teacher_username'), mask_email(item.get('teacher_email')),\n", 1)
text = text.replace("row.get('student_name'), row.get('student_email'), row.get('total_relearn')",
                    "row.get('student_name'), mask_email(row.get('student_email')), row.get('total_relearn')", 1)
text = text.replace("'Username', 'Họ tên', 'Email', 'Học lại'", "'Username', 'Họ tên', 'Email (đã che)', 'Học lại'", 1)
text = text.replace("'Hệ', 'Cơ sở', 'Giảng viên', 'Username', 'Email', 'Số môn'",
                    "'Hệ', 'Cơ sở', 'Giảng viên', 'Username', 'Email (đã che)', 'Số môn'", 1)
write(p, text)

# Tests.
write('backend/app/tests/test_email_privacy_contract.py', '''from pathlib import Path
from types import SimpleNamespace

from app.core.privacy import mask_email
from app.schemas.academic import AcademicStudentOut, UdemyProgressStudentOut
from app.schemas.rbac import RoleAssignmentOut
from app.services.academic.progress_email import AcademicProgressEmailService, plain_text_mail_template


def test_mask_email_is_deterministic_and_idempotent():
    assert mask_email('student01@fpt.edu.vn') == 's***1@fpt.edu.vn'
    assert mask_email('s***1@fpt.edu.vn') == 's***1@fpt.edu.vn'
    assert mask_email(None) is None


def test_academic_api_schemas_mask_student_email():
    student = AcademicStudentOut(id='s1', student_code='SV001', username='sv001', email='student01@fpt.edu.vn', full_name='Sinh Vien', active=True)
    assert student.model_dump()['email'] == 's***1@fpt.edu.vn'
    udemy = UdemyProgressStudentOut(
        id='u1', display_name='Sinh Vien', email='student01@fpt.edu.vn', progress_percent=10,
        status='late', status_label='Chậm', match_status='matched_roster', last_import_batch_id='b1',
        source_format='xlsx', last_imported_at='2026-09-15T00:00:00',
    )
    assert udemy.model_dump()['email'] == 's***1@fpt.edu.vn'


def test_progress_reminder_defaults_and_cms_link():
    cls = SimpleNamespace(class_code='GD2101')
    subject = SimpleNamespace(subject_code='COM1091', subject_name='Tin học và ứng dụng AI')
    assert AcademicProgressEmailService._default_subject(cls, subject) == '[CMS Server] Nhắc nhở tiến độ học tập - COM1091 · GD2101'
    body = AcademicProgressEmailService._default_body(cls, subject)
    assert body.startswith('Xin chào {{tên sinh viên}}-{{maHs}},')
    assert 'Deadline Quiz chỉ là mốc' not in body
    rendered = plain_text_mail_template(body)
    assert 'https://edx.cms.fpl.edu.vn/learner-dashboard/' in rendered
    assert '>CMS</a>' in rendered


def test_frontend_known_email_displays_use_mask_helper():
    root = Path(__file__).resolve().parents[3]
    expected = {
        'frontend/app/student-management/classes/[classId]/page.tsx': 'maskEmailForDisplay(student.email)',
        'frontend/app/subject-management/[deliveryId]/udemy/page.tsx': 'maskEmailForDisplay(row.email)',
        'frontend/components/student-management/UdemyClassProgressPanel.tsx': 'maskEmailForDisplay(row.email)',
        'frontend/app/teacher-management/TeacherManagementPlatformPage.tsx': 'maskEmailForDisplay(item.teacher_email)',
        'frontend/app/users/page.tsx': 'maskEmailForDisplay(item.email)',
    }
    for relative, marker in expected.items():
        assert marker in (root / relative).read_text(encoding='utf-8'), relative


def test_rbac_output_masks_email_without_breaking_raw_input_contract():
    row = RoleAssignmentOut(
        id='r1', user_id='teacher01', email='teacher01@fpt.edu.vn', role_code='SYSTEM_ADMIN',
        scope_type='SYSTEM', scope_id='*', created_at='2026-09-15T00:00:00', updated_at='2026-09-15T00:00:00',
    )
    assert row.model_dump()['email'] == 't***1@fpt.edu.vn'
''')

p = 'backend/app/tests/test_academic_progress_email.py'
replace(p, "    assert '<br>' in rendered\n",
        "    assert '<br>' in rendered\n    linked = plain_text_mail_template('Vui lòng vào CMS để kiểm tra')\n    assert 'https://edx.cms.fpl.edu.vn/learner-dashboard/' in linked\n    assert '>CMS</a>' in linked\n", count=1)

p = 'scripts/ci-backend-tests.sh'
text = read(p)
anchor = '  app/tests/test_learning_sync_preserves_confirmed_enrollment.py \\\n'
if anchor not in text:
    raise SystemExit('CI test-list marker missing')
text = text.replace(anchor, anchor + '  app/tests/test_email_privacy_contract.py \\\n  app/tests/test_academic_progress_email.py \\\n', 1)
write(p, text)

p = 'MASTER_CONTEXT_DASH_CMS.md'
text = read(p)
marker = '## Addendum 2026-09-15 — email display privacy'
if marker not in text:
    text += '''\n\n## Addendum 2026-09-15 — email display privacy\n\n- Mọi email hiển thị ra UI/API report/Excel phải được mask; student/teacher/RBAC/Udemy đều dùng cùng policy `first***last@domain`.\n- Email thật chỉ tồn tại ở storage và các luồng backend nội bộ thật sự cần nó (identity matching, enrollment, Mail Send recipients); không đưa recipient email thật vào public job/audit/log.\n- Progress-email mặc định dùng tiêu đề `[CMS Server] Nhắc nhở tiến độ học tập - {subject} · {class}` và chữ `CMS` trong body được render thành link cố định `https://edx.cms.fpl.edu.vn/learner-dashboard/` sau bước HTML escape.\n- Frontend vẫn mask lần cuối để phòng legacy API trả raw email; backend output serializers/exporters cũng mask để DevTools/API/Excel không lộ địa chỉ đầy đủ.\n'''
    write(p, text)
