from __future__ import annotations

import re
from datetime import date, datetime, time
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

VN_TZ = ZoneInfo("Asia/Ho_Chi_Minh")
POLICY_VERSION = "v25.9.16.5.58"

from app.models.academic import (
    AcademicAssignmentDefenseScore,
    AcademicBlock,
    AcademicClass,
    AcademicQuizDeadlineOverride,
)


def _date_only(value: Any) -> date | None:
    if value is None or value == '':
        return None
    if isinstance(value, datetime):
        if value.tzinfo is not None:
            return value.astimezone(VN_TZ).date()
        return value.date()
    if isinstance(value, date):
        return value
    raw = str(value).strip()
    if not raw:
        return None
    try:
        dt = datetime.fromisoformat(raw.replace('Z', '+00:00'))
        if dt.tzinfo is not None:
            dt = dt.astimezone(VN_TZ)
        return dt.date()
    except Exception:
        pass
    for fmt in ('%Y-%m-%d', '%d/%m/%Y', '%d-%m-%Y'):
        try:
            return datetime.strptime(raw[:10], fmt).date()
        except Exception:
            continue
    return None


def _dt_from_date(value: date | datetime | str | None) -> datetime | None:
    parsed = _date_only(value)
    if not parsed:
        return None
    return datetime.combine(parsed, time.min)


def _number(value: Any) -> float | None:
    if value is None or value == '':
        return None
    try:
        return float(value)
    except Exception:
        return None


def _percent(value: Any) -> float | None:
    number = _number(value)
    if number is None:
        return None
    if 0 <= number <= 1:
        number *= 100.0
    return max(0.0, min(100.0, number))


def _score_percent(item: dict[str, Any] | None) -> float | None:
    if not isinstance(item, dict):
        return None
    percent = _percent(item.get('percent'))
    if percent is not None:
        return percent
    earned = _number(item.get('earned'))
    possible = _number(item.get('possible'))
    if earned is not None and possible and possible > 0:
        return max(0.0, min(100.0, earned / possible * 100.0))
    return None


def _quiz_numbers(value: Any) -> list[int]:
    text = str(value or '')
    numbers: list[int] = []
    patterns = [
        r'quiz\s*#?\s*(\d{1,3})',
        r'learning\s*check\s*#?\s*(\d{1,3})',
        r'\blc\s*#?\s*(\d{1,3})',
    ]
    for pattern in patterns:
        for match in re.finditer(pattern, text, flags=re.I):
            number = int(match.group(1))
            if 1 <= number <= 200 and number not in numbers:
                numbers.append(number)
    return sorted(numbers)


def _quiz_number(item: dict[str, Any]) -> int | None:
    raw = item.get('quiz_number') or item.get('quizNumber')
    try:
        if raw is not None and int(raw) > 0:
            return int(raw)
    except Exception:
        pass
    numbers = _quiz_numbers(' '.join(str(item.get(k) or '') for k in ('name', 'key', 'category', 'label')))
    return numbers[0] if numbers else None


def _is_assignment(item: dict[str, Any]) -> bool:
    text = ' '.join(str(item.get(k) or '') for k in ('name', 'key', 'category', 'label')).lower()
    return 'assignment' in text or 'asm' in text or 'bài tập' in text


def _identity(item: dict[str, Any]) -> str:
    number = _quiz_number(item)
    if number:
        return f'quiz:{number}'
    return re.sub(r'[^a-z0-9]+', '', str(item.get('key') or item.get('name') or '').lower())


class TrainingPolicyService:
    """Evaluate training rules derived from ACMS, using CMS/Open edX learning data.

    Core rule: every quiz must be submitted on/before deadline and score 100%.
    Assignment defense score is manually entered by teachers and is authoritative.
    Final-test rule is intentionally not applied until the business rule is confirmed.
    """

    def __init__(self, db: Session):
        self.db = db

    def deadline_overrides_for_class(self, class_id: str, course_id: str | None = None) -> dict[int, AcademicQuizDeadlineOverride]:
        query = self.db.query(AcademicQuizDeadlineOverride).filter(AcademicQuizDeadlineOverride.class_id == class_id)
        if course_id:
            query = query.filter((AcademicQuizDeadlineOverride.course_id == course_id) | (AcademicQuizDeadlineOverride.course_id.is_(None)))
        rows = query.order_by(AcademicQuizDeadlineOverride.quiz_number.asc().nullslast()).all()
        result: dict[int, AcademicQuizDeadlineOverride] = {}
        for row in rows:
            if row.quiz_number:
                result[int(row.quiz_number)] = row
        return result

    def assignment_scores_for_class(self, class_id: str, course_id: str | None = None) -> dict[str, AcademicAssignmentDefenseScore]:
        query = self.db.query(AcademicAssignmentDefenseScore).filter(AcademicAssignmentDefenseScore.class_id == class_id)
        if course_id:
            query = query.filter((AcademicAssignmentDefenseScore.course_id == course_id) | (AcademicAssignmentDefenseScore.course_id.is_(None)))
        rows = query.order_by(AcademicAssignmentDefenseScore.updated_at.desc().nullslast()).all()
        result: dict[str, AcademicAssignmentDefenseScore] = {}
        for row in rows:
            result.setdefault(row.student_id, row)
        return result

    def _deadline_mode_for_class(self, cls: AcademicClass | None, block: AcademicBlock | None = None) -> tuple[str, str | None]:
        start = _date_only(block.start_date if block else None) or _date_only(cls.start_date if cls else None)
        end = _date_only(block.end_date if block else None) or _date_only(cls.end_date if cls else None)
        if not start or not end:
            return 'manual_required', 'Thiếu ngày bắt đầu/kết thúc block hoặc lớp. Cần cấu hình deadline thủ công.'
        duration = (end - start).days + 1
        if duration > 49:
            return 'manual_required', 'Block dài hơn 7 tuần. Cần cấu hình deadline thủ công để tránh sai lịch nghỉ/lễ.'
        if start.weekday() != 0:
            return 'manual_required', 'Ngày bắt đầu block/lớp không phải Thứ 2. Cần cấu hình deadline thủ công.'
        return 'auto', None

    def _manual_required_for_class(self, cls: AcademicClass | None, block: AcademicBlock | None = None) -> bool:
        return self._deadline_mode_for_class(cls, block)[0] == 'manual_required'

    def _quiz_items(self, components: list[dict[str, Any]]) -> list[dict[str, Any]]:
        by_key: dict[str, dict[str, Any]] = {}
        for item in components or []:
            if not isinstance(item, dict):
                continue
            number = _quiz_number(item)
            if not number:
                continue
            key = f'quiz:{number}'
            current = by_key.get(key)
            candidate = dict(item)
            candidate['quiz_number'] = number
            # Prefer real score rows over planned shells.
            if current is None:
                by_key[key] = candidate
            elif current.get('planned') and not candidate.get('planned'):
                by_key[key] = candidate
            elif current.get('percent') is None and candidate.get('percent') is not None:
                merged = {**current, **candidate}
                by_key[key] = merged
            else:
                merged = {**candidate, **current}
                if not merged.get('deadline_date'):
                    merged['deadline_date'] = candidate.get('deadline_date')
                if not merged.get('available_from'):
                    merged['available_from'] = candidate.get('available_from')
                by_key[key] = merged
        return [by_key[k] for k in sorted(by_key, key=lambda key: int(key.split(':', 1)[1]))]

    def _assignment_expected(self, components: list[dict[str, Any]]) -> bool:
        return any(_is_assignment(item) for item in components or [] if isinstance(item, dict))

    def evaluate_student(
        self,
        *,
        cls: AcademicClass | None,
        student_id: str,
        components: list[dict[str, Any]],
        block: AcademicBlock | None = None,
        course_id: str | None = None,
        now: date | None = None,
        assignment_score: AcademicAssignmentDefenseScore | None = None,
        overrides: dict[int, AcademicQuizDeadlineOverride] | None = None,
    ) -> dict[str, Any]:
        today = now or date.today()
        quiz_items = self._quiz_items(components)
        override_map = overrides if overrides is not None else self.deadline_overrides_for_class(cls.id, course_id) if cls else {}
        deadline_mode, deadline_mode_note = self._deadline_mode_for_class(cls, block)
        manual_required = deadline_mode == 'manual_required'
        reasons: list[str] = []
        notes: list[str] = []
        if deadline_mode_note:
            notes.append(deadline_mode_note)
        passed = failed = late = not_attempted = early = missing_deadline = 0
        quiz_results: list[dict[str, Any]] = []
        for item in quiz_items:
            number = int(item.get('quiz_number') or 0)
            override = override_map.get(number)
            deadline = _date_only(override.deadline_date if override else None) or _date_only(item.get('deadline_date'))
            available_from = _date_only(override.start_date if override else None) or _date_only(item.get('available_from'))
            if available_from is None:
                available_from = _date_only(block.start_date if block else None) or _date_only(cls.start_date if cls else None)
            score = _score_percent(item)
            submitted = _date_only(item.get('submitted_at'))
            status = 'unknown'
            label = 'Chưa đủ dữ liệu'
            if manual_required and override is None:
                missing_deadline += 1
                status = 'manual_deadline_required'
                label = 'Cần chỉnh deadline tay'
                reasons.append(f'Quiz {number} cần cấu hình deadline thủ công do block dài hơn 7 tuần')
            elif not deadline:
                missing_deadline += 1
                status = 'missing_deadline'
                label = 'Thiếu deadline'
                reasons.append(f'Quiz {number} thiếu deadline')
            elif submitted and available_from and submitted < available_from:
                early += 1
                failed += 1
                status = 'early_before_start'
                label = 'Làm trước thời gian học'
                reasons.append(f'Quiz {number} làm trước thời gian học')
            elif score is None:
                not_attempted += 1
                if deadline and today > deadline:
                    late += 1
                    status = 'late_not_attempted'
                    label = 'Quá hạn chưa làm'
                    reasons.append(f'Quiz {number} chưa làm và đã quá deadline')
                else:
                    status = 'not_attempted'
                    label = 'Chưa làm'
                    reasons.append(f'Quiz {number} chưa làm')
            elif submitted is None:
                missing_deadline += 1
                status = 'missing_submission_time'
                label = 'Thiếu thời gian làm'
                reasons.append(f'Quiz {number} đạt {round(score, 2)}% nhưng thiếu thời gian làm/nộp để xét deadline')
            elif deadline and submitted > deadline:
                late += 1
                failed += 1
                status = 'late'
                label = 'Làm sau deadline'
                reasons.append(f'Quiz {number} làm sau deadline')
            elif score < 100:
                failed += 1
                status = 'not_100'
                label = 'Chưa đạt 100%'
                reasons.append(f'Quiz {number} đạt {round(score, 2)}%, yêu cầu 100%')
            else:
                passed += 1
                status = 'passed'
                label = 'Đạt'
            quiz_results.append({
                'quiz_number': number,
                'label': item.get('name') or f'Quiz {number}',
                'score_percent': round(score, 2) if score is not None else None,
                'score_10': round(score / 10.0, 2) if score is not None else None,
                'submitted_at': item.get('submitted_at'),
                'available_from': available_from.isoformat() if available_from else None,
                'deadline_date': deadline.isoformat() if deadline else None,
                'status': status,
                'status_label': label,
            })
        assignment_expected = self._assignment_expected(components)
        assignment_status = 'not_required'
        assignment_score_10: float | None = None
        if assignment_expected:
            if not assignment_score:
                assignment_status = 'not_graded'
                reasons.append('Chưa có điểm Assignment bảo vệ')
            elif assignment_score.defense_status == 'graded':
                if assignment_score.score_10 is None:
                    assignment_status = 'graded_missing_score'
                    reasons.append('Assignment đã đánh dấu đã chấm nhưng chưa có điểm')
                else:
                    assignment_status = 'graded'
                    assignment_score_10 = round(float(assignment_score.score_10), 2)
            else:
                assignment_status = assignment_score.defense_status or 'not_graded'
                reasons.append('Assignment bảo vệ chưa chấm xong')
        if not quiz_items:
            notes.append('CMS/Open edX chưa trả danh sách Quiz; chưa thể xét điều kiện quiz.')
        notes.append('Final test: Chưa áp dụng điều kiện chính thức')
        if missing_deadline:
            exam_status = 'insufficient_data'
            exam_label = 'Chưa đủ dữ liệu'
            exam_eligible = False
        elif not quiz_items:
            exam_status = 'insufficient_data'
            exam_label = 'Chưa đủ dữ liệu'
            exam_eligible = False
        elif failed or late or not_attempted or early:
            exam_status = 'not_eligible'
            exam_label = 'Không được thi'
            exam_eligible = False
        elif assignment_expected and not (assignment_status == 'graded' and assignment_score_10 is not None):
            exam_status = 'not_eligible'
            exam_label = 'Không được thi'
            exam_eligible = False
        else:
            exam_status = 'eligible'
            exam_label = 'Được thi'
            exam_eligible = True
        return {
            'policy_version': POLICY_VERSION,
            'quiz_rule': '100_percent_before_or_on_deadline',
            'final_test_rule': 'pending',
            'quiz_total': len(quiz_items),
            'quiz_passed_count': passed,
            'quiz_failed_count': failed,
            'quiz_late_count': late,
            'quiz_not_attempted_count': not_attempted,
            'quiz_early_count': early,
            'quiz_missing_deadline_count': missing_deadline,
            'all_quizzes_eligible': bool(quiz_items) and not any([failed, late, not_attempted, early, missing_deadline]),
            'assignment_expected': assignment_expected,
            'assignment_status': assignment_status,
            'assignment_score_10': assignment_score_10,
            'assignment_note': assignment_score.note if assignment_score else '',
            'exam_eligible': exam_eligible,
            'exam_status': exam_status,
            'exam_status_label': exam_label,
            'exam_reasons': reasons[:50],
            'exam_notes': notes,
            'quiz_results': quiz_results,
            'deadline_mode': deadline_mode,
            'deadline_mode_note': deadline_mode_note,
        }

    def evaluate_class_students(
        self,
        *,
        cls: AcademicClass,
        components_by_student: dict[str, list[dict[str, Any]]],
        block: AcademicBlock | None = None,
        course_id: str | None = None,
    ) -> dict[str, dict[str, Any]]:
        overrides = self.deadline_overrides_for_class(cls.id, course_id)
        assignment_scores = self.assignment_scores_for_class(cls.id, course_id)
        result: dict[str, dict[str, Any]] = {}
        for student_id, components in components_by_student.items():
            result[student_id] = self.evaluate_student(
                cls=cls,
                student_id=student_id,
                components=components,
                block=block,
                course_id=course_id,
                assignment_score=assignment_scores.get(student_id),
                overrides=overrides,
            )
        return result
