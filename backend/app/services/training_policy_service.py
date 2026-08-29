from __future__ import annotations

import re
from datetime import date, datetime, time
from typing import Any
from sqlalchemy.orm import Session

from app.core.timezone import VN_TZ, to_vn_date

POLICY_VERSION = "v25.9.16.7.2.64.16.5.7.2.15"

from app.models.academic import (
    AcademicAssignmentDefenseScore,
    AcademicBlock,
    AcademicClass,
    AcademicQuizDeadlineOverride,
)


def _date_only(value: Any) -> date | None:
    return to_vn_date(value)


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
    # Parse only human-facing labels, not Open edX usage keys. Storage keys can
    # contain fragments like `quiz-14` and must not create a `Quiz 14` policy item.
    numbers = _quiz_numbers(' '.join(str(item.get(k) or '') for k in ('name', 'label', 'display_name', 'title')))
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

    Core rule: a learner is blocked from the exam only when a quiz deadline has
    expired and the learner had not reached 100% by that deadline. Slow progress,
    an unfinished quiz while its deadline is still open, or an early attempt are
    warnings only and must not create a false exam ban. Assignment defense remains
    visible in the report but is not an exam-blocking rule in this policy version.
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

    def assignment_scores_for_class(self, class_id: str, course_id: str | None = None, student_ids: list[str] | None = None) -> dict[str, AcademicAssignmentDefenseScore]:
        query = self.db.query(AcademicAssignmentDefenseScore).filter(AcademicAssignmentDefenseScore.class_id == class_id)
        if student_ids is not None:
            ids = [str(item).strip() for item in student_ids if str(item or '').strip()]
            if not ids:
                return {}
            query = query.filter(AcademicAssignmentDefenseScore.student_id.in_(ids))
        if course_id:
            query = query.filter((AcademicAssignmentDefenseScore.course_id == course_id) | (AcademicAssignmentDefenseScore.course_id.is_(None)))
        rows = query.order_by(AcademicAssignmentDefenseScore.updated_at.desc().nullslast()).all()
        result: dict[str, AcademicAssignmentDefenseScore] = {}
        for row in rows:
            result.setdefault(row.student_id, row)
        return result


    def _learning_week_schedule_from_block(self, block: AcademicBlock | None) -> list[dict[str, Any]]:
        if not block or not isinstance(block.metadata_json, dict):
            return []
        raw_weeks = block.metadata_json.get('learning_weeks') or block.metadata_json.get('week_schedule') or []
        if not isinstance(raw_weeks, list):
            return []
        weeks: list[dict[str, Any]] = []
        for idx, raw in enumerate(raw_weeks, start=1):
            if not isinstance(raw, dict):
                continue
            start = _date_only(raw.get('start_date') or raw.get('from_date') or raw.get('from'))
            end = _date_only(raw.get('end_date') or raw.get('to_date') or raw.get('to') or raw.get('deadline_date'))
            if not start or not end:
                continue
            weeks.append({'week_number': int(raw.get('week_number') or idx), 'from_date': start.isoformat(), 'due_date': end.isoformat()})
        weeks.sort(key=lambda item: int(item.get('week_number') or 0))
        return weeks

    def _deadline_mode_for_class(self, cls: AcademicClass | None, block: AcademicBlock | None = None) -> tuple[str, str | None]:
        configured_weeks = self._learning_week_schedule_from_block(block)
        if configured_weeks:
            return 'semester_week_config', None
        start = _date_only(block.start_date if block else None) or _date_only(cls.start_date if cls else None)
        end = _date_only(block.end_date if block else None) or _date_only(cls.end_date if cls else None)
        if not start or not end:
            return 'manual_required', 'Thiếu ngày bắt đầu/kết thúc block hoặc lớp. Hãy cấu hình tuần học tại /semesters.'
        duration = (end - start).days + 1
        if duration > 49:
            return 'manual_required', 'Block dài hơn 7 tuần. Hãy cấu hình tuần học tại /semesters để chia deadline quiz theo lịch nghỉ/lễ.'
        if start.weekday() != 0:
            return 'manual_required', 'Ngày bắt đầu block/lớp không phải Thứ 2. Hãy cấu hình tuần học tại /semesters.'
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

    @staticmethod
    def _exam_cutoff_date(cls: AcademicClass | None, block: AcademicBlock | None) -> tuple[date | None, str]:
        """Return the official final-day cutoff used for exam eligibility.

        Quiz deadlines are progress checkpoints only. The exam ban is evaluated
        only after the final day of the class/block. Prefer the class end date when
        AP provides one; otherwise fall back to the block end date.
        """
        class_end = _date_only(cls.end_date if cls else None)
        if class_end:
            return class_end, 'class_end_date'
        block_end = _date_only(block.end_date if block else None)
        if block_end:
            return block_end, 'block_end_date'
        return None, 'missing_final_day'

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
        today = now or datetime.now(VN_TZ).date()
        quiz_items = self._quiz_items(components)
        override_map = overrides if overrides is not None else self.deadline_overrides_for_class(cls.id, course_id) if cls else {}
        deadline_mode, deadline_mode_note = self._deadline_mode_for_class(cls, block)
        manual_required = deadline_mode == 'manual_required'
        exam_cutoff, exam_cutoff_source = self._exam_cutoff_date(cls, block)
        final_day_expired = bool(exam_cutoff and today > exam_cutoff)
        reasons: list[str] = []
        notes: list[str] = []
        if deadline_mode_note:
            notes.append(deadline_mode_note)

        passed = failed = late = not_attempted = early = missing_deadline = pending = 0
        final_day_missing_full = 0
        final_day_unverified = 0
        quiz_results: list[dict[str, Any]] = []
        for item in quiz_items:
            number = int(item.get('quiz_number') or 0)
            override = override_map.get(number)
            progress_deadline = _date_only(override.deadline_date if override else None) or _date_only(item.get('deadline_date'))
            available_from = _date_only(override.start_date if override else None) or _date_only(item.get('available_from'))
            if available_from is None:
                available_from = _date_only(block.start_date if block else None) or _date_only(cls.start_date if cls else None)
            score = _score_percent(item)
            submitted = _date_only(item.get('submitted_at'))
            status = 'unknown'
            label = 'Chưa đủ dữ liệu'

            is_early_attempt = bool(submitted and available_from and submitted < available_from)
            if is_early_attempt:
                early += 1
                notes.append(f'Quiz {number} được làm trước thời gian học; chỉ ghi cảnh báo, không cấm thi')

            progress_deadline_expired = bool(progress_deadline and today > progress_deadline)
            if manual_required and override is None:
                missing_deadline += 1
                notes.append(f'Quiz {number} cần cấu hình mốc tiến độ tại /semesters')
            elif not progress_deadline:
                missing_deadline += 1
                notes.append(f'Quiz {number} thiếu deadline tiến độ')

            # Progress deadlines are coaching checkpoints only. They may mark a
            # learner late for teacher follow-up, but they never create an exam ban.
            if score is None:
                not_attempted += 1
                if progress_deadline_expired:
                    late += 1
                    status = 'progress_deadline_missed_not_attempted'
                    label = 'Chậm tiến độ · chưa làm'
                    notes.append(f'Quiz {number} đã qua mốc tiến độ nhưng chưa làm')
                else:
                    pending += 1
                    status = 'pending_before_progress_deadline'
                    label = 'Còn thời gian theo tiến độ'
            elif score < 100:
                if progress_deadline_expired:
                    late += 1
                    status = 'progress_deadline_missed_not_100'
                    label = 'Chậm tiến độ · chưa đạt 100%'
                    notes.append(f'Quiz {number} đã qua mốc tiến độ và đang đạt {round(score, 2)}%')
                else:
                    pending += 1
                    status = 'in_progress_before_progress_deadline'
                    label = 'Đang theo tiến độ'
            else:
                passed += 1
                if submitted and progress_deadline and submitted > progress_deadline:
                    late += 1
                    status = 'completed_after_progress_deadline'
                    label = 'Đã 100% · hoàn thành sau mốc tiến độ'
                    notes.append(f'Quiz {number} đạt 100% sau mốc tiến độ; chỉ cảnh báo, không cấm thi')
                else:
                    status = 'passed_early' if is_early_attempt else 'passed'
                    label = 'Đạt 100%'

            # Exam eligibility is evaluated only after the official final day.
            if final_day_expired:
                if score is None or score < 100:
                    final_day_missing_full += 1
                    failed += 1
                    reasons.append(
                        f'Quiz {number} chưa đạt 100% khi đã hết ngày cuối {exam_cutoff.isoformat() if exam_cutoff else ""}'
                    )
                elif submitted is None:
                    passed = max(0, passed - 1)
                    final_day_unverified += 1
                    reasons.append(
                        f'Quiz {number} đã đạt 100% nhưng thiếu thời gian nộp để xác minh hoàn thành trước ngày cuối'
                    )
                elif exam_cutoff and submitted > exam_cutoff:
                    passed = max(0, passed - 1)
                    final_day_missing_full += 1
                    failed += 1
                    reasons.append(f'Quiz {number} chỉ đạt 100% sau ngày cuối {exam_cutoff.isoformat()}')

            quiz_results.append({
                'quiz_number': number,
                'label': item.get('name') or f'Quiz {number}',
                'score_percent': round(score, 2) if score is not None else None,
                'score_10': round(score / 10.0, 2) if score is not None else None,
                'submitted_at': item.get('submitted_at'),
                'available_from': available_from.isoformat() if available_from else None,
                'deadline_date': progress_deadline.isoformat() if progress_deadline else None,
                'deadline_kind': 'progress_checkpoint',
                'status': status,
                'status_label': label,
            })

        assignment_expected = self._assignment_expected(components)
        assignment_status = 'not_required'
        assignment_score_10: float | None = None
        if assignment_expected:
            if not assignment_score:
                assignment_status = 'not_graded'
                notes.append('Chưa có điểm Assignment bảo vệ; chỉ hiển thị theo dõi, không dùng để cấm thi')
            elif assignment_score.defense_status == 'graded':
                if assignment_score.score_10 is None:
                    assignment_status = 'graded_missing_score'
                    notes.append('Assignment đã đánh dấu đã chấm nhưng chưa có điểm; không dùng để cấm thi')
                else:
                    assignment_status = 'graded'
                    assignment_score_10 = round(float(assignment_score.score_10), 2)
            else:
                assignment_status = assignment_score.defense_status or 'not_graded'
                notes.append('Assignment bảo vệ chưa chấm xong; chỉ hiển thị theo dõi, không dùng để cấm thi')

        if not quiz_items:
            notes.append('CMS/Open edX chưa trả danh sách Quiz; chưa thể xác nhận trạng thái hoàn thành.')
        notes.append('Final test: Chưa áp dụng điều kiện chính thức')

        if not exam_cutoff:
            exam_status = 'insufficient_data'
            exam_label = 'Thiếu ngày cuối'
            exam_eligible = False
            reasons.append('Thiếu ngày cuối của lớp/block để xác định mốc cấm thi')
        elif not final_day_expired:
            # Before and throughout the final day, slow progress is only a warning.
            exam_status = 'eligible'
            exam_label = 'Chưa bị cấm thi'
            exam_eligible = True
        elif not quiz_items:
            exam_status = 'insufficient_data'
            exam_label = 'Chưa đủ dữ liệu'
            exam_eligible = False
        elif final_day_missing_full > 0:
            exam_status = 'not_eligible'
            exam_label = 'Không được thi'
            exam_eligible = False
        elif final_day_unverified > 0:
            exam_status = 'insufficient_data'
            exam_label = 'Chưa đủ dữ liệu'
            exam_eligible = False
        else:
            exam_status = 'eligible'
            exam_label = 'Được thi'
            exam_eligible = True

        return {
            'policy_version': POLICY_VERSION,
            'quiz_rule': 'progress_deadlines_are_warnings_final_day_blocks_exam',
            'final_test_rule': 'pending',
            'exam_cutoff_date': exam_cutoff.isoformat() if exam_cutoff else None,
            'exam_cutoff_source': exam_cutoff_source,
            'exam_cutoff_expired': final_day_expired,
            'quiz_total': len(quiz_items),
            'quiz_passed_count': passed,
            'quiz_failed_count': failed,
            'quiz_late_count': late,
            'quiz_not_attempted_count': not_attempted,
            'quiz_pending_count': pending,
            'quiz_early_count': early,
            'quiz_missing_deadline_count': missing_deadline,
            'all_quizzes_eligible': bool(quiz_items) and failed == 0 and final_day_unverified == 0 and all((_score_percent(item) or 0) >= 100 for item in quiz_items),
            'assignment_expected': assignment_expected,
            'assignment_status': assignment_status,
            'assignment_score_10': assignment_score_10,
            'assignment_note': assignment_score.note if assignment_score else '',
            'assignment_blocks_exam': False,
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
