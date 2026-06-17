from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import Any

import httpx
from sqlalchemy import and_, func
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.academic import (
    AcademicCampus,
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

# v25.9.16.2.1: AP credentials are read from environment settings.
# Never hardcode or log the AP API key.


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


def _parse_csv_codes(value: str | None) -> list[str]:
    if not value:
        return []
    seen: set[str] = set()
    items: list[str] = []
    for raw in re.split(r'[\n,;\s]+', value):
        item = _clean(raw).lower()
        if item and item not in seen:
            seen.add(item)
            items.append(item)
    return items


def _unique_upper(values: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for value in values or []:
        item = _clean(value).upper()
        if item and item not in seen:
            seen.add(item)
            out.append(item)
    return out


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
    def __init__(self, *, timeout_seconds: int | None = None, base_url: str | None = None, api_key: str | None = None):
        self.timeout_seconds = timeout_seconds or settings.academic_ap_request_timeout_seconds
        self.base_url = (base_url or settings.academic_ap_api_base_url or '').rstrip('/')
        self.api_key = (api_key or settings.academic_ap_api_key or '').strip()
        if not settings.academic_ap_sync_enabled:
            raise RuntimeError('AP sync đang bị tắt. Bật ACADEMIC_AP_SYNC_ENABLED=true nếu muốn đồng bộ AP.')
        if not self.base_url:
            raise RuntimeError('Thiếu ACADEMIC_AP_API_BASE_URL cho đồng bộ AP.')
        if not self.api_key:
            raise RuntimeError('Thiếu ACADEMIC_AP_API_KEY trong env. Không hardcode API key AP trong source.')

    def _headers(self, campus: str | None = None) -> dict[str, str]:
        headers = {
            'Authorization': f'Bearer {self.api_key}',
            'Content-Type': 'application/json',
        }
        if campus:
            headers['campus'] = campus
        return headers

    def get_subjects(self, *, branch: str, term_name: str, campus: str | None = None) -> list[dict[str, Any]]:
        # ACMS legacy contract: discover subjects by branch + term first, then call
        # /get-data-cms per campus x subject_code. Do not require operators to
        # maintain a full subject catalog in env for normal production sync.
        params = {'branch': _lower(branch) or 'poly', 'term_name': term_name}
        with httpx.Client(timeout=self.timeout_seconds) as client:
            response = client.get(
                f'{self.base_url}/get-course',
                headers=self._headers(),
                params=params,
            )
            response.raise_for_status()
            data = response.json()
        if isinstance(data, dict) and data.get('status') not in (None, 'success'):
            raise RuntimeError(f'AP get-course failed: {data.get("message") or data.get("status")}')
        root = data.get('data') if isinstance(data, dict) and isinstance(data.get('data'), (dict, list)) else data
        if isinstance(root, dict):
            items = root.get('course') or root.get('courses') or root.get('data') or []
        elif isinstance(root, list):
            items = root
        else:
            items = []
        if not isinstance(items, list):
            raise RuntimeError('AP get-course trả dữ liệu môn không đúng định dạng list.')
        subjects: list[dict[str, Any]] = []
        for item in items:
            if isinstance(item, dict):
                code = _clean(item.get('psubject_code') or item.get('subject_code') or item.get('id'))
                if code:
                    normalized = dict(item)
                    normalized.setdefault('subject_code', code)
                    subjects.append(normalized)
        if not subjects:
            raise RuntimeError(f'AP get-course không trả môn nào cho branch={branch}, term={term_name}.')
        return subjects

    def get_division(self, *, campus: str, term_name: str, subject_code: str) -> dict[str, Any]:
        body = {'campus': campus, 'term_name': term_name, 'subject_code': subject_code}
        with httpx.Client(timeout=self.timeout_seconds) as client:
            response = client.post(
                f'{self.base_url}/get-data-cms',
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
            current = run.counters_json if isinstance(run.counters_json, dict) else {}
            # Preserve sync planning metadata (campus/subject plan, warnings) that
            # sync_from_ap stored before finishing the run. Older code overwrote it
            # with plain counters only, making dry-run hard to inspect.
            run.counters_json = {**current, **counters.as_dict()} if current else counters.as_dict()
        if error:
            run.status = 'failed'
            run.error_message = error[:4000]
        else:
            run.status = 'completed'
        self.db.add(run)
        self.db.commit()
        self.db.refresh(run)
        return run


    def seed_campuses_from_settings(self, *, branch: str = 'poly') -> list[AcademicCampus]:
        """Seed/update campus master data from ACADEMIC_AP_CAMPUSES once.

        AP does not expose a campus listing endpoint. ACMS legacy solved this with
        admin_cms.premises. AI Server stores the same concept in academic_campuses
        so operators do not have to type campus codes for every sync.
        """
        normalized_branch = _lower(branch) or 'poly'
        rows: list[AcademicCampus] = []
        for index, code in enumerate(_parse_csv_codes(settings.academic_ap_campuses), start=1):
            item = self.db.query(AcademicCampus).filter(AcademicCampus.campus_code == code, AcademicCampus.branch == normalized_branch).first()
            if not item:
                item = AcademicCampus(
                    id=str(uuid.uuid4()),
                    campus_code=code,
                    branch=normalized_branch,
                    created_at=_now(),
                )
                self.db.add(item)
            item.campus_name = item.campus_name or code.upper()
            item.active = True
            item.sort_order = item.sort_order or index
            item.metadata_json = {'source': 'env.ACADEMIC_AP_CAMPUSES'}
            item.updated_at = _now()
            rows.append(item)
        self.db.commit()
        for item in rows:
            self.db.refresh(item)
        return rows

    def _campus_master_values(self, *, branch: str = 'poly', include_env: bool = True, include_seen_classes: bool = True) -> list[dict[str, Any]]:
        normalized_branch = _lower(branch) or 'poly'
        values: dict[str, dict[str, Any]] = {}
        for item in (
            self.db.query(AcademicCampus)
            .filter(AcademicCampus.active.is_(True), AcademicCampus.branch == normalized_branch)
            .order_by(AcademicCampus.sort_order.asc(), AcademicCampus.campus_code.asc())
            .all()
        ):
            code = _lower(item.campus_code)
            if code:
                values[code] = {
                    'value': code,
                    'label': item.campus_name or code.upper(),
                    'description': f'Cơ sở AP {code} · nguồn: academic_campuses',
                    'meta': {'source': 'academic_campuses', 'id': item.id, 'branch': item.branch, 'sort_order': item.sort_order},
                }
        if include_env:
            for index, code in enumerate(_parse_csv_codes(settings.academic_ap_campuses), start=1):
                if code and code not in values:
                    values[code] = {
                        'value': code,
                        'label': code.upper(),
                        'description': 'Cơ sở AP từ env ACADEMIC_AP_CAMPUSES; có thể seed vào bảng academic_campuses',
                        'meta': {'source': 'env', 'sort_order': 10000 + index},
                    }
        if include_seen_classes:
            db_campuses = (
                self.db.query(AcademicClass.campus)
                .filter(AcademicClass.campus.isnot(None), AcademicClass.campus != '')
                .distinct()
                .order_by(AcademicClass.campus.asc())
                .all()
            )
            for (item,) in db_campuses:
                code = _lower(item)
                if code and code not in values:
                    values[code] = {
                        'value': code,
                        'label': code.upper(),
                        'description': 'Cơ sở đã từng xuất hiện trong academic_classes',
                        'meta': {'source': 'academic_classes'},
                    }
        return sorted(values.values(), key=lambda item: (item.get('meta', {}).get('sort_order', 99999), item['value']))

    def _resolve_campuses(self, *, sync_scope: str, campus: str | None, campuses: list[str] | None, branch: str = 'poly') -> list[str]:
        scope = _lower(sync_scope or 'campus')
        requested = [_lower(item) for item in (campuses or []) if _lower(item)]
        if campus and _lower(campus) and _lower(campus) not in requested:
            requested.insert(0, _lower(campus))
        if scope == 'all':
            configured = requested or [item['value'] for item in self._campus_master_values(branch=branch)]
            if not configured:
                raise RuntimeError('sync_scope=all cần danh sách cơ sở. ACMS cũ lấy từ admin_cms.premises; AI Server lấy từ academic_campuses hoặc ACADEMIC_AP_CAMPUSES. Hãy seed cơ sở một lần trước khi dùng Tích tất cả.')
            return configured
        if scope in {'campus', 'subject'}:
            if not requested:
                raise RuntimeError('Đồng bộ theo cơ sở/môn cần chọn ít nhất một cơ sở từ dropdown.')
            return requested
        raise RuntimeError("sync_scope không hợp lệ. Dùng một trong: all, campus, subject.")


    def _configured_subject_codes(self) -> list[str]:
        # Optional fallback/debug catalog only. Normal production flow uses AP get-course.
        return _unique_upper(_parse_csv_codes(settings.academic_ap_subject_codes))

    def _subject_code_from_item(self, item: dict[str, Any]) -> str:
        return _clean(item.get('psubject_code') or item.get('subject_code') or item.get('id')).upper()

    def import_subject_catalog(self, items: list[dict[str, Any]], *, branch: str, counters: SyncCounters) -> None:
        for item in items:
            if not isinstance(item, dict):
                continue
            try:
                self._get_or_create_subject(item, branch, counters)
            except Exception:
                # Bad catalog rows should not stop class/student sync; get-data-cms rows will
                # still create subjects from psubject_code when they are valid.
                continue
        self.db.commit()

    def _resolve_subject_codes_for_campus(
        self,
        client: APAcademicClient,
        *,
        branch: str,
        term_name: str,
        campus: str,
        subject_codes: list[str],
        max_subjects: int,
        catalog_cache: dict[str, list[dict[str, Any]]],
    ) -> tuple[list[str], list[dict[str, Any]], str, str | None]:
        explicit = _unique_upper(subject_codes)
        if explicit:
            codes = explicit
            source = 'request.subject_codes'
            catalog: list[dict[str, Any]] = []
            warning = None
        else:
            cache_key = f'{_lower(branch) or "poly"}:{term_name}'
            warning = None
            try:
                if cache_key not in catalog_cache:
                    catalog_cache[cache_key] = client.get_subjects(branch=branch, term_name=term_name, campus=campus)
                catalog = catalog_cache[cache_key]
                codes = _unique_upper([self._subject_code_from_item(item) for item in catalog if isinstance(item, dict)])
                source = 'ap.get-course'
            except Exception as exc:
                fallback = self._configured_subject_codes()
                if not fallback:
                    raise RuntimeError(
                        f'Không lấy được danh sách môn từ AP get-course ({exc}). '
                        'Có thể dùng sync_scope=subject để truyền subject_codes, hoặc cấu hình '
                        'ACADEMIC_AP_SUBJECT_CODES làm fallback tạm thời.'
                    ) from exc
                catalog = []
                codes = fallback
                source = 'ACADEMIC_AP_SUBJECT_CODES_fallback'
                warning = f'AP get-course lỗi, dùng fallback env: {exc}'
        if max_subjects and max_subjects > 0:
            codes = codes[:max_subjects]
        return codes, catalog, source, warning


    def get_ap_sync_options(self, *, term_name: str | None = None, branch: str = 'poly', include_subjects: bool = True) -> dict[str, Any]:
        """Return safe dropdown options for AP sync.

        ACMS legacy stores campuses in admin_cms.premises and subjects in AP get-course.
        AI Server does not own the old premises table, so campuses are resolved from
        ACADEMIC_AP_CAMPUSES plus campuses already seen in academic_classes. Subjects
        are resolved from AP /get-course when a term is selected, with local DB/env as
        fallback to keep the UI usable when AP is temporarily unavailable.
        """
        normalized_branch = _lower(branch) or 'poly'
        warnings: list[str] = []

        branches = [
            {'value': 'poly', 'label': 'Poly', 'description': 'Branch ACMS cũ: poly', 'meta': {}},
            {'value': 'ptcd', 'label': 'PTCĐ', 'description': 'Branch ACMS cũ: ptcd', 'meta': {}},
        ]

        campuses = self._campus_master_values(branch=normalized_branch)
        if not campuses:
            warnings.append('Chưa có danh sách cơ sở. ACMS cũ lấy từ admin_cms.premises; AI Server cần seed một lần vào academic_campuses hoặc cấu hình ACADEMIC_AP_CAMPUSES=pt,hn,hcm,...')

        term_query = self.db.query(AcademicTerm).filter(AcademicTerm.active.is_(True))
        if normalized_branch:
            term_query = term_query.filter(AcademicTerm.branch == normalized_branch)
        term_rows = term_query.order_by(AcademicTerm.start_date.desc().nullslast(), AcademicTerm.term_name.desc()).limit(80).all()
        terms = [
            {
                'value': item.term_name,
                'label': item.term_name,
                'description': item.term_code or item.ap_term_id,
                'meta': {'id': item.id, 'branch': item.branch, 'start_date': item.start_date.isoformat() if item.start_date else None, 'end_date': item.end_date.isoformat() if item.end_date else None},
            }
            for item in term_rows
        ]
        if not terms:
            warnings.append('Chưa có kỳ trong AI Server. Lần đầu vẫn có thể nhập kỳ thủ công đúng như AP, ví dụ Summer 2026.')

        subjects: list[dict[str, Any]] = []
        if include_subjects:
            catalog: list[dict[str, Any]] = []
            if term_name and _clean(term_name):
                try:
                    catalog = APAcademicClient().get_subjects(branch=normalized_branch, term_name=_clean(term_name))
                except Exception as exc:
                    warnings.append(f'Không lấy được môn từ AP /get-course: {exc}. Đang dùng dữ liệu môn local/env nếu có.')
            if catalog:
                seen: set[str] = set()
                for item in catalog:
                    code = self._subject_code_from_item(item)
                    if not code or code in seen:
                        continue
                    seen.add(code)
                    name = _clean(item.get('subject_name') or item.get('psubject_name') or item.get('name'))
                    skill = _clean(item.get('skill_code'))
                    subjects.append({
                        'value': code,
                        'label': f'{code} — {name}' if name else code,
                        'description': skill or None,
                        'meta': {'source': 'ap.get-course', 'subject_name': name, 'skill_code': skill},
                    })
            else:
                q = self.db.query(AcademicSubject).filter(AcademicSubject.active.is_(True))
                if normalized_branch:
                    q = q.filter(AcademicSubject.branch == normalized_branch)
                local_rows = q.order_by(AcademicSubject.subject_code.asc()).limit(2000).all()
                seen: set[str] = set()
                for item in local_rows:
                    code = _clean(item.subject_code).upper()
                    if not code or code in seen:
                        continue
                    seen.add(code)
                    subjects.append({
                        'value': code,
                        'label': f'{code} — {item.subject_name}' if item.subject_name else code,
                        'description': item.skill_code,
                        'meta': {'source': 'local.academic_subjects', 'subject_id': item.id},
                    })
                for code in self._configured_subject_codes():
                    if code not in seen:
                        seen.add(code)
                        subjects.append({'value': code, 'label': code, 'description': 'Fallback env ACADEMIC_AP_SUBJECT_CODES', 'meta': {'source': 'env'}})
        return {'branches': branches, 'campuses': campuses, 'terms': terms, 'subjects': subjects, 'warnings': warnings}

    def sync_from_ap(
        self,
        *,
        requested_by: str | None,
        term_name: str,
        campus: str | None,
        branch: str,
        subject_codes: list[str],
        max_subjects: int,
        dry_run: bool = False,
        sync_scope: str = 'campus',
        campuses: list[str] | None = None,
    ) -> tuple[AcademicSyncRun, SyncCounters]:
        scope = _lower(sync_scope or 'campus')
        resolved_campuses = self._resolve_campuses(sync_scope=scope, campus=campus, campuses=campuses, branch=branch)
        run_campus = ','.join(resolved_campuses[:10]) + ('...' if len(resolved_campuses) > 10 else '')
        run = self.create_run(
            source='ap',
            mode=f'api_{scope}_dry_run' if dry_run else f'api_{scope}',
            requested_by=requested_by,
            term_name=term_name,
            campus=run_campus,
            branch=branch,
        )
        client = APAcademicClient()
        counters = SyncCounters()
        planned: dict[str, Any] = {
            'sync_scope': scope,
            'campuses': resolved_campuses,
            'campus_count': len(resolved_campuses),
            'max_subjects_per_campus': max_subjects or 0,
            'subject_source': None,
            'ap_subject_endpoint': '/get-course',
            'ap_division_endpoint': '/get-data-cms',
            'subjects_by_campus': {},
            'warnings': [],
        }
        catalog_cache: dict[str, list[dict[str, Any]]] = {}
        imported_catalog_keys: set[str] = set()
        try:
            for campus_code in resolved_campuses:
                codes, catalog, source, warning = self._resolve_subject_codes_for_campus(
                    client,
                    branch=branch,
                    term_name=term_name,
                    campus=campus_code,
                    subject_codes=subject_codes,
                    max_subjects=max_subjects,
                    catalog_cache=catalog_cache,
                )
                if not planned['subject_source']:
                    planned['subject_source'] = source
                if warning:
                    planned['warnings'].append({'campus': campus_code, 'message': warning})
                planned['subjects_by_campus'][campus_code] = {'count': len(codes), 'preview': codes[:20], 'source': source}
                if dry_run:
                    continue
                catalog_key = f'{_lower(branch) or "poly"}:{term_name}:{source}'
                if catalog and catalog_key not in imported_catalog_keys:
                    self.import_subject_catalog(catalog, branch=branch, counters=counters)
                    imported_catalog_keys.add(catalog_key)
                for code in codes:
                    try:
                        payload = client.get_division(campus=campus_code, term_name=term_name, subject_code=code)
                        if not payload:
                            self._error(run, counters, 'ap_subject', f'{campus_code}:{code}', 'AP trả payload rỗng', {'campus': campus_code, 'subject_code': code})
                            continue
                        imported = self.import_payload(payload, run=run, campus=campus_code, branch=branch)
                        for key, value in imported.as_dict().items():
                            setattr(counters, key, getattr(counters, key) + value)
                    except Exception as exc:
                        self._error(run, counters, 'ap_subject', f'{campus_code}:{code}', str(exc), {'campus': campus_code, 'subject_code': code})
            if dry_run:
                counters.subjects = sum(item['count'] for item in planned['subjects_by_campus'].values())
                run.counters_json = {**counters.as_dict(), 'plan': planned}
                return self.finish_run(run, counters), counters
            current = run.counters_json or {}
            run.counters_json = {**current, **counters.as_dict(), 'plan': planned}
            return self.finish_run(run, counters), counters
        except Exception as exc:
            self.db.rollback()
            return self.finish_run(run, counters, error=str(exc)), counters

