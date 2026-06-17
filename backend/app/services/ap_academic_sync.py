from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import Any

import httpx
from sqlalchemy import and_, func
from sqlalchemy.orm import Session

from app.models.academic import (
    AcademicBlock,
    AcademicClass,
    AcademicClassStudent,
    AcademicStudent,
    AcademicSubject,
    AcademicSyncError,
    AcademicSyncRun,
    AcademicTeacher,
    AcademicTeacherAssignment,
    AcademicTerm,
)

# v25.9.16.0: the AP token is intentionally kept as a code constant because the
# current deployment account cannot change the upstream AP API configuration.
# Do not log this value and do not return it in any API response.
AP_API_TOKEN = 'VXXbKr5ERSdxZhHkM6'
AP_API_BASE_URL = 'https://api_v2.poly.edu.vn'


@dataclass
class SyncCounters:
    terms: int = 0
    blocks: int = 0
    subjects: int = 0
    classes: int = 0
    teachers: int = 0
    students: int = 0
    teacher_assignments: int = 0
    class_students: int = 0
    errors: int = 0

    def as_dict(self) -> dict[str, int]:
        return asdict(self)


def _now() -> datetime:
    return datetime.utcnow()


def _clean(value: Any) -> str:
    return str(value or '').strip()


def _lower(value: Any) -> str:
    return _clean(value).lower()


def _parse_date(value: Any) -> datetime | None:
    raw = _clean(value)
    if not raw:
        return None
    try:
        raw = raw.replace('Z', '+00:00')
        parsed = datetime.fromisoformat(raw)
        if parsed.tzinfo:
            parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
        return parsed
    except Exception:
        return None


def _block_sort_order(name: str) -> int:
    match = re.search(r'(\d+)', name or '')
    return int(match.group(1)) if match else 0


def _term_code(term_name: str, branch: str) -> str:
    base = re.sub(r'\s+', '_', (term_name or '').strip().upper()) or 'UNKNOWN_TERM'
    return f'{base}:{branch or "poly"}'


def _safe_payload(value: Any) -> Any:
    """Return small debug payload without PII-heavy student rosters."""
    if isinstance(value, dict):
        out = {}
        for key, item in value.items():
            if key in {'student', 'students'}:
                out[key] = f'[{len(item) if isinstance(item, list) else "?"} students redacted]'
            elif key in {'email', 'phone'}:
                out[key] = '***REDACTED***'
            else:
                out[key] = _safe_payload(item)
        return out
    if isinstance(value, list):
        return [_safe_payload(item) for item in value[:5]]
    return value


class APAcademicClient:
    def __init__(self, *, timeout_seconds: int = 60):
        self.timeout_seconds = timeout_seconds

    def _headers(self, campus: str | None = None) -> dict[str, str]:
        headers = {
            'Authorization': f'Bearer {AP_API_TOKEN}',
            'Content-Type': 'application/json',
        }
        if campus:
            headers['campus'] = campus
        return headers

    def get_subjects(self, *, branch: str, term_name: str) -> list[dict[str, Any]]:
        with httpx.Client(timeout=self.timeout_seconds) as client:
            response = client.get(
                f'{AP_API_BASE_URL}/get-course',
                params={'branch': branch or 'poly', 'term_name': term_name},
                headers=self._headers(),
            )
            response.raise_for_status()
            data = response.json()
        if data.get('status') != 'success':
            raise RuntimeError(f'AP get-course failed: {data.get("message") or data.get("status")}')
        payload = data.get('data') or {}
        courses = payload.get('course') if isinstance(payload, dict) else None
        return courses or []

    def get_division(self, *, campus: str, term_name: str, subject_code: str) -> dict[str, Any]:
        body = {'campus': campus, 'term_name': term_name, 'subject_code': subject_code}
        with httpx.Client(timeout=self.timeout_seconds) as client:
            response = client.post(
                f'{AP_API_BASE_URL}/get-data-cms',
                headers=self._headers(campus=campus),
                json=body,
            )
            response.raise_for_status()
            data = response.json()
        if data.get('status') != 'success':
            raise RuntimeError(f'AP get-data-cms failed for {subject_code}: {data.get("message") or data.get("status")}')
        return data.get('data') or {}


class AcademicImportService:
    def __init__(self, db: Session):
        self.db = db

    def create_run(self, *, source: str, mode: str, requested_by: str | None = None, term_name: str | None = None, campus: str | None = None, branch: str | None = None) -> AcademicSyncRun:
        run = AcademicSyncRun(
            id=str(uuid.uuid4()),
            source=source,
            mode=mode,
            status='running',
            requested_by=requested_by,
            term_name=term_name,
            campus=_lower(campus) or None,
            branch=_lower(branch) or 'poly',
            counters_json={},
            started_at=_now(),
            created_at=_now(),
        )
        self.db.add(run)
        self.db.commit()
        self.db.refresh(run)
        return run

    def _error(self, run: AcademicSyncRun | None, counters: SyncCounters, entity_type: str, entity_key: str, message: str, payload: Any = None) -> None:
        counters.errors += 1
        self.db.add(AcademicSyncError(
            id=str(uuid.uuid4()),
            sync_run_id=run.id if run else None,
            source='ap',
            entity_type=entity_type,
            entity_key=entity_key[:255],
            message=message[:4000],
            payload_json=_safe_payload(payload) if payload is not None else None,
            created_at=_now(),
        ))

    def _get_or_create_term(self, term_payload: dict[str, Any], branch: str, counters: SyncCounters) -> AcademicTerm:
        term_name = _clean(term_payload.get('term_name') or term_payload.get('pterm_name') or term_payload.get('name')) or 'Unknown Term'
        ap_term_id = _clean(term_payload.get('id') or term_payload.get('term_id') or term_payload.get('pterm_id')) or None
        branch = _lower(branch) or 'poly'
        code = _term_code(term_name, branch)
        term = self.db.query(AcademicTerm).filter(AcademicTerm.term_code == code, AcademicTerm.branch == branch).first()
        if not term:
            term = AcademicTerm(id=str(uuid.uuid4()), term_code=code, term_name=term_name, branch=branch, created_at=_now(), updated_at=_now())
            counters.terms += 1
        term.ap_term_id = ap_term_id or term.ap_term_id
        term.term_name = term_name
        term.start_date = _parse_date(term_payload.get('startday') or term_payload.get('start_day') or term_payload.get('start_date')) or term.start_date
        term.end_date = _parse_date(term_payload.get('endday') or term_payload.get('end_day') or term_payload.get('end_date')) or term.end_date
        term.active = True
        term.metadata_json = {'source': 'ap', 'raw_keys': sorted(term_payload.keys())}
        term.updated_at = _now()
        self.db.add(term)
        self.db.flush()
        return term

    def _get_or_create_block(self, term: AcademicTerm, block_payload: dict[str, Any], counters: SyncCounters) -> AcademicBlock:
        name = _clean(block_payload.get('block_name') or block_payload.get('block') or block_payload.get('name')) or 'Block'
        ap_block_id = _clean(block_payload.get('id') or block_payload.get('block_id')) or None
        code = ap_block_id or name.lower().replace(' ', '-')
        block = self.db.query(AcademicBlock).filter(AcademicBlock.term_id == term.id, AcademicBlock.block_code == code).first()
        if not block:
            block = AcademicBlock(id=str(uuid.uuid4()), term_id=term.id, block_code=code, block_name=name, created_at=_now(), updated_at=_now())
            counters.blocks += 1
        block.ap_block_id = ap_block_id or block.ap_block_id
        block.block_name = name
        block.start_date = _parse_date(block_payload.get('start_day') or block_payload.get('start_date')) or block.start_date
        block.end_date = _parse_date(block_payload.get('end_day') or block_payload.get('end_date')) or block.end_date
        block.sort_order = _block_sort_order(name)
        block.active = True
        block.metadata_json = {'source': 'ap', 'raw_keys': sorted(block_payload.keys())}
        block.updated_at = _now()
        self.db.add(block)
        self.db.flush()
        return block

    def _get_or_create_subject(self, item: dict[str, Any], branch: str, counters: SyncCounters) -> AcademicSubject:
        branch = _lower(branch) or 'poly'
        subject_code = _clean(item.get('psubject_code') or item.get('subject_code') or item.get('id'))
        if not subject_code:
            raise ValueError('Thiếu subject_code')
        subject = self.db.query(AcademicSubject).filter(AcademicSubject.subject_code == subject_code, AcademicSubject.branch == branch).first()
        if not subject:
            subject = AcademicSubject(id=str(uuid.uuid4()), subject_code=subject_code, branch=branch, subject_name=subject_code, created_at=_now(), updated_at=_now())
            counters.subjects += 1
        subject.ap_subject_id = _clean(item.get('subject_id') or item.get('id')) or subject.ap_subject_id
        subject.subject_name = _clean(item.get('psubject_name') or item.get('subject_name') or item.get('short_name')) or subject.subject_name or subject_code
        subject.subject_name_en = _clean(item.get('subject_name_en')) or subject.subject_name_en
        subject.skill_code = _clean(item.get('skill_code')) or subject.skill_code
        subject.active = True
        subject.metadata_json = {'source': 'ap', 'raw_keys': sorted(item.keys())}
        subject.updated_at = _now()
        self.db.add(subject)
        self.db.flush()
        return subject

    def _get_or_create_teacher(self, username: str, campus: str | None, branch: str, counters: SyncCounters) -> AcademicTeacher:
        username = _lower(username)
        if not username:
            raise ValueError('Thiếu teacher username')
        teacher = self.db.query(AcademicTeacher).filter(func.lower(AcademicTeacher.username) == username).first()
        if not teacher:
            teacher = AcademicTeacher(id=str(uuid.uuid4()), username=username, full_name=username, created_at=_now(), updated_at=_now())
            counters.teachers += 1
        teacher.campus = _lower(campus) or teacher.campus
        teacher.branch = _lower(branch) or teacher.branch
        teacher.active = True
        teacher.updated_at = _now()
        self.db.add(teacher)
        self.db.flush()
        return teacher

    def _get_or_create_student(self, item: dict[str, Any], campus: str | None, branch: str, counters: SyncCounters) -> AcademicStudent:
        username = _lower(item.get('username'))
        if not username:
            raise ValueError('Thiếu student username')
        student = self.db.query(AcademicStudent).filter(func.lower(AcademicStudent.username) == username).first()
        if not student:
            student = AcademicStudent(id=str(uuid.uuid4()), username=username, full_name='', created_at=_now(), updated_at=_now())
            counters.students += 1
        student.student_code = _clean(item.get('student_code') or item.get('user_code')) or student.student_code
        student.email = _lower(item.get('email')) or student.email
        student.full_name = _clean(item.get('name') or item.get('full_name')) or student.full_name or username
        student.phone = _clean(item.get('phone')) or student.phone
        student.campus = _lower(campus) or student.campus
        student.branch = _lower(branch) or student.branch
        student.active = True
        student.metadata_json = {'source': 'ap'}
        student.updated_at = _now()
        self.db.add(student)
        self.db.flush()
        return student

    def import_payload(self, payload: dict[str, Any], *, run: AcademicSyncRun | None = None, campus: str | None = None, branch: str = 'poly') -> SyncCounters:
        counters = SyncCounters()
        branch = _lower(branch) or 'poly'
        campus = _lower(campus) or None
        term_payload = payload.get('term') if isinstance(payload.get('term'), dict) else {}
        class_items = payload.get('class') if isinstance(payload.get('class'), list) else []
        if class_items and not term_payload:
            first = class_items[0]
            term_payload = {'id': first.get('pterm_id'), 'term_name': first.get('pterm_name')}
        term = self._get_or_create_term(term_payload, branch, counters)
        blocks_by_ap: dict[str, AcademicBlock] = {}
        for raw_block in term_payload.get('block') or []:
            if not isinstance(raw_block, dict):
                continue
            block = self._get_or_create_block(term, raw_block, counters)
            if block.ap_block_id:
                blocks_by_ap[str(block.ap_block_id)] = block
        for raw in class_items:
            if not isinstance(raw, dict):
                self._error(run, counters, 'class', 'unknown', 'Class payload không phải object', raw)
                continue
            try:
                subject = self._get_or_create_subject(raw, branch, counters)
                raw_block_id = _clean(raw.get('block_id'))
                block = blocks_by_ap.get(raw_block_id)
                if not block and raw_block_id:
                    block = self._get_or_create_block(term, {'id': raw_block_id, 'block_name': raw.get('block_name') or f'Block {raw_block_id}'}, counters)
                    blocks_by_ap[raw_block_id] = block
                class_code = _clean(raw.get('group_name') or raw.get('class_code') or raw.get('classname'))
                if not class_code:
                    raise ValueError('Thiếu class/group_name')
                ap_class_id = _clean(raw.get('id')) or None
                cls = None
                if ap_class_id:
                    cls = self.db.query(AcademicClass).filter(AcademicClass.ap_class_id == ap_class_id).first()
                if not cls:
                    cls = self.db.query(AcademicClass).filter(
                        AcademicClass.term_id == term.id,
                        AcademicClass.block_id == (block.id if block else None),
                        AcademicClass.subject_id == subject.id,
                        AcademicClass.class_code == class_code,
                    ).first()
                if not cls:
                    cls = AcademicClass(id=str(uuid.uuid4()), term_id=term.id, block_id=block.id if block else None, subject_id=subject.id, class_code=class_code, created_at=_now(), updated_at=_now())
                    counters.classes += 1
                cls.ap_class_id = ap_class_id or cls.ap_class_id
                cls.class_name = _clean(raw.get('classname') or raw.get('class_name') or class_code) or class_code
                cls.campus = campus
                cls.branch = branch
                cls.start_date = _parse_date(raw.get('start_date')) or cls.start_date
                cls.end_date = _parse_date(raw.get('end_date')) or cls.end_date
                cls.active = True
                cls.metadata_json = {'source': 'ap', 'raw_keys': sorted(raw.keys())}
                cls.updated_at = _now()
                self.db.add(cls)
                self.db.flush()

                teacher_username = _clean(raw.get('teacher'))
                if teacher_username:
                    teacher = self._get_or_create_teacher(teacher_username, campus, branch, counters)
                    assignment = self.db.query(AcademicTeacherAssignment).filter(
                        AcademicTeacherAssignment.teacher_id == teacher.id,
                        AcademicTeacherAssignment.class_id == cls.id,
                        AcademicTeacherAssignment.subject_id == subject.id,
                        AcademicTeacherAssignment.term_id == term.id,
                        AcademicTeacherAssignment.block_id == (block.id if block else None),
                    ).first()
                    if not assignment:
                        assignment = AcademicTeacherAssignment(
                            id=str(uuid.uuid4()),
                            teacher_id=teacher.id,
                            class_id=cls.id,
                            subject_id=subject.id,
                            term_id=term.id,
                            block_id=block.id if block else None,
                            campus=campus,
                            branch=branch,
                            source='ap',
                            synced_at=_now(),
                        )
                        counters.teacher_assignments += 1
                    assignment.synced_at = _now()
                    assignment.campus = campus
                    assignment.branch = branch
                    self.db.add(assignment)
                for raw_student in raw.get('student') or raw.get('students') or []:
                    if not isinstance(raw_student, dict):
                        continue
                    try:
                        student = self._get_or_create_student(raw_student, campus, branch, counters)
                        link = self.db.query(AcademicClassStudent).filter(AcademicClassStudent.class_id == cls.id, AcademicClassStudent.student_id == student.id).first()
                        if not link:
                            link = AcademicClassStudent(id=str(uuid.uuid4()), class_id=cls.id, student_id=student.id, source='ap', synced_at=_now())
                            counters.class_students += 1
                        link.synced_at = _now()
                        self.db.add(link)
                    except Exception as exc:
                        self._error(run, counters, 'student', _clean(raw_student.get('username') or raw_student.get('user_code') or 'unknown'), str(exc), raw_student)
            except Exception as exc:
                self._error(run, counters, 'class', _clean(raw.get('id') or raw.get('group_name') or 'unknown'), str(exc), raw)
        if run:
            run.counters_json = counters.as_dict()
        self.db.commit()
        return counters

    def finish_run(self, run: AcademicSyncRun, counters: SyncCounters | None = None, error: str | None = None) -> AcademicSyncRun:
        run.finished_at = _now()
        if counters:
            run.counters_json = counters.as_dict()
        if error:
            run.status = 'failed'
            run.error_message = error[:4000]
        else:
            run.status = 'completed'
        self.db.add(run)
        self.db.commit()
        self.db.refresh(run)
        return run

    def sync_from_ap(self, *, requested_by: str | None, term_name: str, campus: str, branch: str, subject_codes: list[str], max_subjects: int, dry_run: bool = False) -> tuple[AcademicSyncRun, SyncCounters]:
        run = self.create_run(source='ap', mode='api_dry_run' if dry_run else 'api', requested_by=requested_by, term_name=term_name, campus=campus, branch=branch)
        client = APAcademicClient()
        counters = SyncCounters()
        try:
            codes = [code.strip().upper() for code in subject_codes if code.strip()]
            if not codes:
                courses = client.get_subjects(branch=branch, term_name=term_name)
                codes = [_clean(item.get('subject_code') or item.get('psubject_code')).upper() for item in courses]
                codes = [code for code in codes if code]
            codes = codes[:max_subjects]
            if dry_run:
                run.counters_json = {'subject_codes_found': len(codes), 'subject_codes_preview': codes[:20]}
                return self.finish_run(run, counters), counters
            merged: dict[str, Any] | None = None
            all_classes: list[dict[str, Any]] = []
            for code in codes:
                try:
                    payload = client.get_division(campus=campus, term_name=term_name, subject_code=code)
                    if not merged:
                        merged = {'term': payload.get('term') or {'term_name': term_name}, 'class': []}
                    all_classes.extend(payload.get('class') or [])
                except Exception as exc:
                    self._error(run, counters, 'ap_subject', code, str(exc), {'subject_code': code})
            if merged is None:
                merged = {'term': {'term_name': term_name}, 'class': []}
            merged['class'] = all_classes
            imported = self.import_payload(merged, run=run, campus=campus, branch=branch)
            # Preserve AP fetch errors and add imported counters.
            for key, value in imported.as_dict().items():
                setattr(counters, key, getattr(counters, key) + value)
            return self.finish_run(run, counters), counters
        except Exception as exc:
            self.db.rollback()
            return self.finish_run(run, counters, error=str(exc)), counters
