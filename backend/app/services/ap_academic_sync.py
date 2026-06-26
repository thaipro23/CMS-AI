from __future__ import annotations

import json
import hashlib
import re
import ssl
import uuid
from dataclasses import dataclass, asdict
from datetime import datetime, timezone, timedelta
from pathlib import Path
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
    AcademicClassCourseMapping,
    AcademicStudentLearningSnapshot,
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
    skipped_empty_classes: int = 0
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


def _legacy_term_code(term_name: str, branch: str) -> str:
    base = re.sub(r'\s+', '_', (term_name or '').strip().upper()) or 'UNKNOWN_TERM'
    return f'{base}:{branch or "poly"}'


def _term_code(term_name: str, branch: str) -> str:
    # Keep the code identical to the operator-visible AP term name. Earlier builds
    # generated SUMMER_2026:poly, which created duplicate terms next to the
    # /semesters-managed "Summer 2026" rows and made /student-management look empty.
    return _clean(term_name) or _legacy_term_code(term_name, branch)


def _text_key(value: Any) -> str:
    return re.sub(r'[^a-z0-9]+', '', str(value or '').strip().lower())


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


def _safe_filename_part(value: Any, *, default: str = 'unknown') -> str:
    item = re.sub(r'[^a-zA-Z0-9_.-]+', '_', _clean(value))
    item = item.strip('._-')
    return item[:120] or default


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
        self.tls_mode = (getattr(settings, 'academic_ap_tls_mode', 'strict') or 'strict').strip().lower()
        if not settings.academic_ap_sync_enabled:
            raise RuntimeError('AP sync đang bị tắt. Bật ACADEMIC_AP_SYNC_ENABLED=true nếu muốn đồng bộ AP.')
        if not self.base_url:
            raise RuntimeError('Thiếu ACADEMIC_AP_API_BASE_URL cho đồng bộ AP.')
        if not self.api_key:
            raise RuntimeError('Thiếu ACADEMIC_AP_API_KEY trong env. Không hardcode API key AP trong source.')


    def _verify_config(self) -> bool | ssl.SSLContext:
        """Return httpx TLS verify configuration for the legacy AP API.

        strict     -> default httpx verification: CA chain + hostname.
        chain_only -> verify CA chain but skip hostname validation. This is a
                      controlled compatibility mode for legacy AP hostnames such
                      as api_v2.poly.edu.vn where the certificate chain is valid
                      but Python/OpenSSL rejects the underscore hostname.
        off        -> disable all TLS verification. UAT emergency fallback only.
        """
        mode = self.tls_mode
        if mode in {'off', 'false', '0', 'no', 'disabled'}:
            return False
        if mode in {'chain_only', 'chain-only', 'chainonly'}:
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_REQUIRED
            return ctx
        return True

    def _headers(self, campus: str | None = None) -> dict[str, str]:
        headers = {
            'Authorization': f'Bearer {self.api_key}',
            'Content-Type': 'application/json',
        }
        if campus:
            headers['campus'] = campus
        return headers

    def _subject_cache_enabled(self) -> bool:
        return bool(getattr(settings, 'academic_ap_get_course_file_cache_enabled', True))

    def _subject_cache_refresh(self) -> bool:
        return bool(getattr(settings, 'academic_ap_get_course_file_cache_refresh', False))

    def _subject_cache_ttl_seconds(self) -> int:
        raw = getattr(settings, 'academic_ap_get_course_file_cache_ttl_seconds', 86400)
        try:
            return max(0, int(raw))
        except Exception:
            return 86400

    def _subject_cache_dir(self) -> Path:
        raw = _clean(getattr(settings, 'academic_ap_get_course_file_cache_dir', '/tmp/ai-server-ap-cache/get-course'))
        return Path(raw or '/tmp/ai-server-ap-cache/get-course')

    def _subject_cache_file(self, *, branch: str, term_name: str) -> Path:
        # The AP discovery endpoint always uses branch=poly. The requested branch
        # is intentionally not part of the file name so ptcd/poly UI choices reuse
        # the same canonical course catalog and do not create duplicate files.
        discovery_branch = 'poly'
        base_hash = hashlib.sha1(self.base_url.encode('utf-8')).hexdigest()[:10]
        term_part = _safe_filename_part(term_name, default='term')
        return self._subject_cache_dir() / f'{discovery_branch}_{term_part}_{base_hash}.json'

    def _normalize_subject_items(self, items: Any, *, requested_branch: str) -> list[dict[str, Any]]:
        if not isinstance(items, list):
            raise RuntimeError('AP get-course trả dữ liệu môn không đúng định dạng list.')
        subjects: list[dict[str, Any]] = []
        for item in items:
            if isinstance(item, dict):
                code = _clean(item.get('psubject_code') or item.get('subject_code') or item.get('id'))
                if code:
                    normalized = dict(item)
                    normalized.setdefault('subject_code', code)
                    normalized.setdefault('discovery_branch', 'poly')
                    normalized.setdefault('requested_branch', _lower(requested_branch) or 'poly')
                    subjects.append(normalized)
        return subjects

    def _extract_subject_items_from_response(self, data: Any) -> list[dict[str, Any]]:
        if isinstance(data, dict) and data.get('status') not in (None, 'success'):
            raise RuntimeError(f'AP get-course failed: {data.get("message") or data.get("status")}')
        root = data.get('data') if isinstance(data, dict) and isinstance(data.get('data'), (dict, list)) else data
        if isinstance(root, dict):
            items = root.get('course') or root.get('courses') or root.get('data') or []
        elif isinstance(root, list):
            items = root
        else:
            items = []
        return items

    def _read_subject_cache(self, *, branch: str, term_name: str) -> list[dict[str, Any]] | None:
        if not self._subject_cache_enabled() or self._subject_cache_refresh():
            return None
        path = self._subject_cache_file(branch=branch, term_name=term_name)
        if not path.exists():
            return None
        ttl = self._subject_cache_ttl_seconds()
        try:
            raw = json.loads(path.read_text(encoding='utf-8'))
            cached_at_ts = float(raw.get('cached_at_ts') or 0)
            if ttl > 0 and cached_at_ts > 0 and (datetime.now(timezone.utc).timestamp() - cached_at_ts) > ttl:
                return None
            items = raw.get('subjects') or raw.get('items') or []
            subjects = self._normalize_subject_items(items, requested_branch=branch)
            for item in subjects:
                item['_catalog_source'] = 'ap.get-course.file-cache'
                item['_catalog_cache_file'] = str(path)
            return subjects or None
        except Exception:
            # Corrupt/stale cache must never break AP sync. Fall back to AP.
            return None

    def _write_subject_cache(self, *, branch: str, term_name: str, subjects: list[dict[str, Any]]) -> None:
        if not self._subject_cache_enabled():
            return
        path = self._subject_cache_file(branch=branch, term_name=term_name)
        payload = {
            'schema_version': 1,
            'source': 'ap.get-course',
            'base_url': self.base_url,
            'discovery_branch': 'poly',
            'requested_branch': _lower(branch) or 'poly',
            'term_name': term_name,
            'cached_at': datetime.now(timezone.utc).isoformat(),
            'cached_at_ts': datetime.now(timezone.utc).timestamp(),
            'count': len(subjects),
            # Store only get-course catalog rows. This file is deliberately not a
            # DB table, so repeated syncs can reuse the discovery list without
            # growing academic_subjects/classes.
            'subjects': subjects,
        }
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp_path = path.with_suffix(path.suffix + '.tmp')
            tmp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding='utf-8')
            tmp_path.replace(path)
        except Exception:
            # Cache write is an optimization only; never fail sync because /tmp or
            # mounted cache storage is not writable.
            return

    def get_subjects(self, *, branch: str, term_name: str, campus: str | None = None) -> list[dict[str, Any]]:
        # ACMS legacy contract: /get-course must always use branch=poly to
        # discover the canonical subject catalog. Some requested branches
        # (notably ptcd) return noisy/incorrect subject lists. The requested
        # branch is still preserved for downstream class/student sync.
        cached = self._read_subject_cache(branch=branch, term_name=term_name)
        if cached:
            return cached

        discovery_branch = 'poly'
        params = {'branch': discovery_branch, 'term_name': term_name}
        with httpx.Client(timeout=self.timeout_seconds, verify=self._verify_config()) as client:
            response = client.get(
                f'{self.base_url}/get-course',
                headers=self._headers(),
                params=params,
            )
            response.raise_for_status()
            data = response.json()
        items = self._extract_subject_items_from_response(data)
        subjects = self._normalize_subject_items(items, requested_branch=branch)
        if not subjects:
            raise RuntimeError(f'AP get-course không trả môn nào cho branch=poly, term={term_name}, requested_branch={branch}.')
        for item in subjects:
            item['_catalog_source'] = 'ap.get-course'
        self._write_subject_cache(branch=branch, term_name=term_name, subjects=subjects)
        return subjects

    def get_division(self, *, campus: str, term_name: str, subject_code: str) -> dict[str, Any]:
        body = {'campus': campus, 'term_name': term_name, 'subject_code': subject_code}
        with httpx.Client(timeout=self.timeout_seconds, verify=self._verify_config()) as client:
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
        # AP /get-data-cms is called once per campus/subject. Every response carries
        # the same term.block payload, so repeatedly touching /semesters rows inside
        # one sync run is unnecessary. This cache is scoped to one service instance
        # and still refreshes immediately when AP returns a different signature.
        self._term_block_payload_cache: dict[str, tuple[AcademicTerm, dict[str, AcademicBlock], list[AcademicBlock]]] = {}

    def create_run(self, *, source: str, mode: str, requested_by: str | None = None, term_name: str | None = None, campus: str | None = None, branch: str | None = None, status: str = 'running', counters_json: dict[str, Any] | None = None) -> AcademicSyncRun:
        now = _now()
        run = AcademicSyncRun(
            id=str(uuid.uuid4()),
            source=source,
            mode=mode,
            status=status or 'running',
            requested_by=requested_by,
            term_name=term_name,
            campus=_lower(campus) or None,
            branch=_lower(branch) or 'poly',
            counters_json=counters_json or {},
            started_at=now,
            created_at=now,
        )
        self.db.add(run)
        self.db.commit()
        self.db.refresh(run)
        return run

    def update_run_progress(self, run: AcademicSyncRun, *, current: int, total: int, label: str, plan: dict[str, Any] | None = None, counters: SyncCounters | None = None, commit: bool = True) -> AcademicSyncRun:
        data = run.counters_json if isinstance(run.counters_json, dict) else {}
        next_data = dict(data)
        if counters is not None:
            next_data.update(counters.as_dict())
        if plan is not None:
            next_data['plan'] = plan
        next_data['progress'] = {
            'current': max(0, int(current or 0)),
            'total': max(1, int(total or 1)),
            'label': label,
            'updated_at': _now().isoformat(),
        }
        run.counters_json = next_data
        self.db.add(run)
        if commit:
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

    def _set_if_changed(self, obj: Any, attr: str, value: Any, *, allow_empty: bool = False) -> bool:
        """Assign only when the incoming value is meaningful and different.

        AP sync is intentionally idempotent: re-running the same term/campus/subject
        must not dirty rows or update updated_at when AP data did not actually
        change. This avoids large no-op UPDATE storms and prevents repeated syncs
        from fighting natural-key constraints.
        """
        if value is None:
            return False
        if isinstance(value, str):
            value = _clean(value)
            if not value and not allow_empty:
                return False
        current = getattr(obj, attr)
        if current != value:
            setattr(obj, attr, value)
            return True
        return False

    def _set_json_if_changed(self, obj: Any, attr: str, value: dict | None) -> bool:
        normalized = value or {}
        if (getattr(obj, attr) or {}) != normalized:
            setattr(obj, attr, normalized)
            return True
        return False

    def _valid_student_items(self, raw_class: dict[str, Any]) -> list[dict[str, Any]]:
        """Return AP student rows that can be mapped into CMS/Open edX users.

        DB-growth guard: AP can return thousands of empty class shells across many
        campuses and subjects. A class without a valid student username is not
        actionable for Student Management, enrollment, or learning analytics, so
        production sync skips it before creating subject/class/teacher rows.
        """
        raw_students = raw_class.get('student') or raw_class.get('students') or []
        if not isinstance(raw_students, list):
            return []
        valid: list[dict[str, Any]] = []
        for item in raw_students:
            if not isinstance(item, dict):
                continue
            username = _lower(item.get('username') or item.get('user_name') or item.get('login'))
            if username:
                # Preserve the original AP row but normalize the username key for the
                # existing _get_or_create_student implementation.
                if not item.get('username'):
                    item = {**item, 'username': username}
                valid.append(item)
        return valid

    def _mark_class_superseded(self, stale: AcademicClass, winner: AcademicClass, *, reason: str) -> bool:
        changed = False
        changed |= self._set_if_changed(stale, 'active', False)
        meta = dict(stale.metadata_json or {})
        meta.update({
            'source': meta.get('source') or 'ap',
            'superseded_by_class_id': winner.id,
            'superseded_reason': reason,
            'superseded_at': _now().isoformat(),
        })
        changed |= self._set_json_if_changed(stale, 'metadata_json', meta)
        if changed:
            stale.updated_at = _now()
            self.db.add(stale)
        return changed

    def _merge_duplicate_class_relations(self, stale: AcademicClass, winner: AcademicClass) -> None:
        """Move safe child rows from a stale duplicate class into the winner row.

        Keep the stale class row inactive for audit/history; do not delete it because
        other tables may still reference it. Child rows with unique constraints are
        merged by deleting only duplicate links that already exist on the winner.
        """
        if stale.id == winner.id:
            return

        # Class-student links: class_id + student_id is unique.
        for link in self.db.query(AcademicClassStudent).filter(AcademicClassStudent.class_id == stale.id).all():
            existing = self.db.query(AcademicClassStudent).filter(
                AcademicClassStudent.class_id == winner.id,
                AcademicClassStudent.student_id == link.student_id,
            ).first()
            if existing:
                self.db.delete(link)
            else:
                link.class_id = winner.id
                self.db.add(link)

        # Teacher assignments: teacher + class + subject + term + block is unique.
        for assignment in self.db.query(AcademicTeacherAssignment).filter(AcademicTeacherAssignment.class_id == stale.id).all():
            existing = self.db.query(AcademicTeacherAssignment).filter(
                AcademicTeacherAssignment.teacher_id == assignment.teacher_id,
                AcademicTeacherAssignment.class_id == winner.id,
                AcademicTeacherAssignment.subject_id == winner.subject_id,
                AcademicTeacherAssignment.term_id == winner.term_id,
                AcademicTeacherAssignment.block_id == winner.block_id,
            ).first()
            if existing:
                self.db.delete(assignment)
            else:
                assignment.class_id = winner.id
                assignment.subject_id = winner.subject_id
                assignment.term_id = winner.term_id
                assignment.block_id = winner.block_id
                assignment.campus = winner.campus or assignment.campus
                assignment.branch = winner.branch or assignment.branch
                self.db.add(assignment)

        # Class-level Open edX override mapping is unique by class_id. Keep an existing
        # winner mapping. If the winner has none, move the stale mapping.
        stale_mapping = self.db.query(AcademicClassCourseMapping).filter(AcademicClassCourseMapping.class_id == stale.id).first()
        if stale_mapping:
            winner_mapping = self.db.query(AcademicClassCourseMapping).filter(AcademicClassCourseMapping.class_id == winner.id).first()
            if winner_mapping:
                stale_mapping.active = False
                stale_mapping.updated_at = _now()
                stale_mapping.note = (stale_mapping.note or '') + f'\nSuperseded by class {winner.id}'
                self.db.add(stale_mapping)
            else:
                stale_mapping.class_id = winner.id
                stale_mapping.updated_at = _now()
                self.db.add(stale_mapping)

        # Learning snapshots: class + student + course is unique.
        for snap in self.db.query(AcademicStudentLearningSnapshot).filter(AcademicStudentLearningSnapshot.class_id == stale.id).all():
            existing = self.db.query(AcademicStudentLearningSnapshot).filter(
                AcademicStudentLearningSnapshot.class_id == winner.id,
                AcademicStudentLearningSnapshot.student_id == snap.student_id,
                AcademicStudentLearningSnapshot.openedx_course_id == snap.openedx_course_id,
            ).first()
            if existing:
                self.db.delete(snap)
            else:
                snap.class_id = winner.id
                snap.updated_at = _now()
                self.db.add(snap)

        self._mark_class_superseded(stale, winner, reason='duplicate_natural_key')

    def _resolve_class_row(
        self,
        *,
        term: AcademicTerm,
        block: AcademicBlock | None,
        subject: AcademicSubject,
        class_code: str,
        ap_class_id: str | None,
        counters: SyncCounters,
    ) -> tuple[AcademicClass, bool]:
        target_block_id = block.id if block else None
        target_cls = self.db.query(AcademicClass).filter(
            AcademicClass.term_id == term.id,
            AcademicClass.block_id == target_block_id,
            AcademicClass.subject_id == subject.id,
            AcademicClass.class_code == class_code,
        ).first()

        ap_cls = None
        if ap_class_id:
            ap_cls = (
                self.db.query(AcademicClass)
                .filter(AcademicClass.ap_class_id == ap_class_id)
                .order_by(AcademicClass.active.desc(), AcademicClass.updated_at.desc().nullslast())
                .first()
            )

        if target_cls:
            if ap_cls and ap_cls.id != target_cls.id:
                self._merge_duplicate_class_relations(ap_cls, target_cls)
            return target_cls, False

        if ap_cls:
            # Defensive check: if a duplicate natural-key row appeared between the
            # first lookup and the AP-id lookup, use that row instead of updating
            # ap_cls into a unique-constraint violation.
            conflict = self.db.query(AcademicClass).filter(
                AcademicClass.term_id == term.id,
                AcademicClass.block_id == target_block_id,
                AcademicClass.subject_id == subject.id,
                AcademicClass.class_code == class_code,
                AcademicClass.id != ap_cls.id,
            ).first()
            if conflict:
                self._merge_duplicate_class_relations(ap_cls, conflict)
                return conflict, False
            return ap_cls, False

        cls = AcademicClass(
            id=str(uuid.uuid4()),
            term_id=term.id,
            block_id=target_block_id,
            subject_id=subject.id,
            class_code=class_code,
            created_at=_now(),
            updated_at=_now(),
        )
        counters.classes += 1
        return cls, True

    def _get_or_create_term(self, term_payload: dict[str, Any], branch: str, counters: SyncCounters) -> AcademicTerm:
        term_name = _clean(term_payload.get('term_name') or term_payload.get('pterm_name') or term_payload.get('name')) or 'Unknown Term'
        ap_term_id = _clean(term_payload.get('id') or term_payload.get('term_id') or term_payload.get('pterm_id')) or None
        branch = _lower(branch) or 'poly'
        canonical_code = _term_code(term_name, branch)
        legacy_code = _legacy_term_code(term_name, branch)

        term = self.db.query(AcademicTerm).filter(
            AcademicTerm.term_code == canonical_code,
            AcademicTerm.branch == branch,
        ).first()

        if not term:
            candidates = self.db.query(AcademicTerm).filter(AcademicTerm.branch == branch).all()
            wanted = _text_key(term_name)
            for candidate in candidates:
                if _text_key(candidate.term_name) == wanted or _text_key(candidate.term_code) == wanted:
                    term = candidate
                    break

        if not term and ap_term_id:
            term = self.db.query(AcademicTerm).filter(
                AcademicTerm.ap_term_id == ap_term_id,
                AcademicTerm.branch == branch,
            ).first()

        if not term:
            term = self.db.query(AcademicTerm).filter(
                AcademicTerm.term_code == legacy_code,
                AcademicTerm.branch == branch,
            ).first()

        is_new = False
        if not term:
            term = AcademicTerm(
                id=str(uuid.uuid4()),
                term_code=canonical_code,
                term_name=term_name,
                branch=branch,
                created_at=_now(),
                updated_at=_now(),
            )
            counters.terms += 1
            is_new = True

        changed = is_new
        changed |= self._set_if_changed(term, 'ap_term_id', ap_term_id)
        if _text_key(term.term_code) in {_text_key(legacy_code), '', 'unknownterm'} and term.term_code != canonical_code:
            existing = self.db.query(AcademicTerm).filter(
                AcademicTerm.term_code == canonical_code,
                AcademicTerm.branch == branch,
                AcademicTerm.id != term.id,
            ).first()
            if not existing:
                changed |= self._set_if_changed(term, 'term_code', canonical_code)
        changed |= self._set_if_changed(term, 'term_name', term_name)
        changed |= self._set_if_changed(term, 'start_date', _parse_date(term_payload.get('startday') or term_payload.get('start_day') or term_payload.get('start_date')))
        changed |= self._set_if_changed(term, 'end_date', _parse_date(term_payload.get('endday') or term_payload.get('end_day') or term_payload.get('end_date')))
        changed |= self._set_if_changed(term, 'active', True)
        meta = dict(term.metadata_json or {})
        meta.update({'source': meta.get('source') or 'ap', 'last_sync_source': 'ap', 'raw_keys': sorted(term_payload.keys())})
        changed |= self._set_json_if_changed(term, 'metadata_json', meta)
        if changed:
            term.updated_at = _now()
            self.db.add(term)
            self.db.flush()
        return term

    def _get_or_create_block(self, term: AcademicTerm, block_payload: dict[str, Any], counters: SyncCounters) -> AcademicBlock:
        name = _clean(block_payload.get('block_name') or block_payload.get('block') or block_payload.get('name')) or 'Block'
        ap_block_id = _clean(block_payload.get('id') or block_payload.get('block_id')) or None
        canonical_code = name
        legacy_code = ap_block_id or name.lower().replace(' ', '-')

        block = None
        if ap_block_id:
            block = self.db.query(AcademicBlock).filter(AcademicBlock.term_id == term.id, AcademicBlock.ap_block_id == ap_block_id).first()
        if not block:
            block = self.db.query(AcademicBlock).filter(AcademicBlock.term_id == term.id, AcademicBlock.block_code == canonical_code).first()
        if not block and legacy_code != canonical_code:
            block = self.db.query(AcademicBlock).filter(AcademicBlock.term_id == term.id, AcademicBlock.block_code == legacy_code).first()
        if not block:
            wanted = _text_key(name)
            for candidate in self.db.query(AcademicBlock).filter(AcademicBlock.term_id == term.id).all():
                if _text_key(candidate.block_name) == wanted or _text_key(candidate.block_code) == wanted:
                    block = candidate
                    break

        is_new = False
        if not block:
            block = AcademicBlock(
                id=str(uuid.uuid4()),
                term_id=term.id,
                block_code=canonical_code,
                block_name=name,
                created_at=_now(),
                updated_at=_now(),
            )
            counters.blocks += 1
            is_new = True

        changed = is_new
        changed |= self._set_if_changed(block, 'ap_block_id', ap_block_id)
        changed |= self._set_if_changed(block, 'block_name', name)
        if block.block_code == legacy_code and block.block_code != canonical_code:
            existing = self.db.query(AcademicBlock).filter(
                AcademicBlock.term_id == term.id,
                AcademicBlock.block_code == canonical_code,
                AcademicBlock.id != block.id,
            ).first()
            if not existing:
                changed |= self._set_if_changed(block, 'block_code', canonical_code)
        changed |= self._set_if_changed(block, 'start_date', _parse_date(block_payload.get('start_day') or block_payload.get('start_date')))
        changed |= self._set_if_changed(block, 'end_date', _parse_date(block_payload.get('end_day') or block_payload.get('end_date')))
        changed |= self._set_if_changed(block, 'sort_order', _block_sort_order(name) or block.sort_order or 0)
        changed |= self._set_if_changed(block, 'active', True)
        meta = dict(block.metadata_json or {})
        meta.update({'source': meta.get('source') or 'ap', 'last_sync_source': 'ap', 'raw_keys': sorted(block_payload.keys())})
        changed |= self._set_json_if_changed(block, 'metadata_json', meta)
        if changed:
            block.updated_at = _now()
            self.db.add(block)
            self.db.flush()
        return block

    def _term_block_signature(self, term_payload: dict[str, Any]) -> str:
        """Stable signature for AP term/block master data.

        The signature intentionally contains only term and block master fields used
        by /semesters. Class/student rosters are excluded so a normal class sync
        cannot force noisy term/block checks for every /get-data-cms response.
        """
        blocks: list[dict[str, Any]] = []
        for raw in term_payload.get('block') or []:
            if not isinstance(raw, dict):
                continue
            blocks.append({
                'id': _clean(raw.get('id') or raw.get('block_id')),
                'block_name': _clean(raw.get('block_name') or raw.get('block') or raw.get('name')),
                'start_day': _clean(raw.get('start_day') or raw.get('start_date')),
                'end_day': _clean(raw.get('end_day') or raw.get('end_date')),
            })
        normalized = {
            'term_id': _clean(term_payload.get('id') or term_payload.get('term_id') or term_payload.get('pterm_id')),
            'term_name': _clean(term_payload.get('term_name') or term_payload.get('pterm_name') or term_payload.get('name')),
            'startday': _clean(term_payload.get('startday') or term_payload.get('start_day') or term_payload.get('start_date')),
            'endday': _clean(term_payload.get('endday') or term_payload.get('end_day') or term_payload.get('end_date')),
            'blocks': sorted(blocks, key=lambda item: (item.get('id') or '', item.get('block_name') or '')),
        }
        return hashlib.sha1(json.dumps(normalized, ensure_ascii=False, sort_keys=True).encode('utf-8')).hexdigest()

    def _recent_term_block_signature(self, term: AcademicTerm, signature: str) -> bool:
        meta = term.metadata_json if isinstance(term.metadata_json, dict) else {}
        if meta.get('ap_term_block_signature') != signature:
            return False
        raw_at = _clean(meta.get('ap_term_block_checked_at'))
        if not raw_at:
            return False
        try:
            checked_at = datetime.fromisoformat(raw_at.replace('Z', '+00:00'))
            if checked_at.tzinfo:
                checked_at = checked_at.astimezone(timezone.utc).replace(tzinfo=None)
        except Exception:
            return False
        ttl = max(0, int(getattr(settings, 'academic_ap_term_block_refresh_ttl_seconds', 3600) or 0))
        if ttl <= 0:
            return False
        return (_now() - checked_at) < timedelta(seconds=ttl)

    def _load_blocks_for_term(self, term: AcademicTerm) -> tuple[dict[str, AcademicBlock], list[AcademicBlock]]:
        blocks = (
            self.db.query(AcademicBlock)
            .filter(AcademicBlock.term_id == term.id)
            .order_by(AcademicBlock.sort_order.asc(), AcademicBlock.block_name.asc(), AcademicBlock.id.asc())
            .all()
        )
        blocks_by_ap = {str(block.ap_block_id): block for block in blocks if block.ap_block_id}
        return blocks_by_ap, blocks

    def _get_or_create_term_and_blocks_cached(
        self,
        term_payload: dict[str, Any],
        branch: str,
        counters: SyncCounters,
    ) -> tuple[AcademicTerm, dict[str, AcademicBlock], list[AcademicBlock]]:
        signature = self._term_block_signature(term_payload)
        term_name = _clean(term_payload.get('term_name') or term_payload.get('pterm_name') or term_payload.get('name')) or 'Unknown Term'
        term_key = _clean(term_payload.get('id') or term_payload.get('term_id') or term_payload.get('pterm_id')) or _text_key(term_name)
        cache_key = f'{_lower(branch) or "poly"}:{term_key}:{signature}'
        cached = self._term_block_payload_cache.get(cache_key)
        if cached:
            return cached

        term = self._get_or_create_term(term_payload, branch, counters)
        meta = dict(term.metadata_json or {})

        # If AP master data did not change recently, do not repeatedly run the
        # block upsert path while get-data-cms loops over many subjects. We still
        # load local blocks for class.block_id resolution and date fallback.
        if self._recent_term_block_signature(term, signature):
            blocks_by_ap, blocks = self._load_blocks_for_term(term)
            cached_value = (term, blocks_by_ap, blocks)
            self._term_block_payload_cache[cache_key] = cached_value
            return cached_value

        for raw_block in term_payload.get('block') or []:
            if not isinstance(raw_block, dict):
                continue
            self._get_or_create_block(term, raw_block, counters)

        meta.update({
            'source': meta.get('source') or 'ap',
            'last_sync_source': 'ap',
            'ap_term_block_signature': signature,
            'ap_term_block_checked_at': _now().isoformat(),
            'ap_term_block_count': len([item for item in (term_payload.get('block') or []) if isinstance(item, dict)]),
        })
        if self._set_json_if_changed(term, 'metadata_json', meta):
            term.updated_at = _now()
            self.db.add(term)
            self.db.flush()

        blocks_by_ap, blocks = self._load_blocks_for_term(term)
        cached_value = (term, blocks_by_ap, blocks)
        self._term_block_payload_cache[cache_key] = cached_value
        return cached_value

    def _infer_block_from_class_dates(self, raw: dict[str, Any], blocks: list[AcademicBlock]) -> AcademicBlock | None:
        class_start = _parse_date(raw.get('start_date') or raw.get('start_day'))
        class_end = _parse_date(raw.get('end_date') or raw.get('end_day'))
        if not class_start and not class_end:
            return None
        usable = [block for block in blocks if block.start_date and block.end_date]
        if not usable:
            return None

        # Best match: class start day falls inside the AP block range.
        if class_start:
            for block in usable:
                if block.start_date <= class_start <= block.end_date:
                    return block

        # Fallback: class end day falls inside the block range.
        if class_end:
            for block in usable:
                if block.start_date <= class_end <= block.end_date:
                    return block

        # Last fallback: any interval overlap. This handles short AP date offsets
        # without assigning a class to an unrelated block.
        if class_start and class_end:
            for block in usable:
                if class_start <= block.end_date and class_end >= block.start_date:
                    return block
        return None

    def _resolve_block_for_class(
        self,
        term: AcademicTerm,
        raw: dict[str, Any],
        blocks_by_ap: dict[str, AcademicBlock],
        blocks: list[AcademicBlock],
        counters: SyncCounters,
    ) -> tuple[AcademicBlock | None, str]:
        raw_block_id = _clean(raw.get('block_id'))
        if raw_block_id and raw_block_id in blocks_by_ap:
            return blocks_by_ap[raw_block_id], 'ap_block_id'

        inferred = self._infer_block_from_class_dates(raw, blocks)
        if inferred:
            return inferred, 'date_range'

        if raw_block_id:
            # AP sent a block id that is not present in term.block. Preserve the
            # class instead of dropping it, but make the placeholder visible in
            # /semesters so admins can correct AP/master-data mismatch.
            block = self._get_or_create_block(term, {'id': raw_block_id, 'block_name': raw.get('block_name') or f'Block {raw_block_id}'}, counters)
            blocks_by_ap[raw_block_id] = block
            blocks.append(block)
            return block, 'ap_block_id_placeholder'
        return None, 'unresolved'

    def _get_or_create_subject(self, item: dict[str, Any], branch: str, counters: SyncCounters) -> AcademicSubject:
        branch = _lower(branch) or 'poly'
        subject_code = _clean(item.get('psubject_code') or item.get('subject_code') or item.get('id'))
        if not subject_code:
            raise ValueError('Thiếu subject_code')
        subject = self.db.query(AcademicSubject).filter(AcademicSubject.subject_code == subject_code, AcademicSubject.branch == branch).first()
        is_new = False
        if not subject:
            subject = AcademicSubject(
                id=str(uuid.uuid4()),
                subject_code=subject_code,
                branch=branch,
                subject_name=subject_code,
                created_at=_now(),
                updated_at=_now(),
            )
            counters.subjects += 1
            is_new = True

        changed = is_new
        changed |= self._set_if_changed(subject, 'ap_subject_id', _clean(item.get('subject_id') or item.get('id')) or None)
        changed |= self._set_if_changed(subject, 'subject_name', _clean(item.get('psubject_name') or item.get('subject_name') or item.get('short_name')) or subject.subject_name or subject_code)
        changed |= self._set_if_changed(subject, 'subject_name_en', _clean(item.get('subject_name_en')) or None)
        changed |= self._set_if_changed(subject, 'skill_code', _clean(item.get('skill_code')) or None)
        changed |= self._set_if_changed(subject, 'active', True)
        changed |= self._set_json_if_changed(subject, 'metadata_json', {'source': 'ap', 'raw_keys': sorted(item.keys())})
        if changed:
            subject.updated_at = _now()
            self.db.add(subject)
            self.db.flush()
        return subject

    def _get_or_create_teacher(self, username: str, campus: str | None, branch: str, counters: SyncCounters) -> AcademicTeacher:
        username = _lower(username)
        if not username:
            raise ValueError('Thiếu teacher username')
        teacher = self.db.query(AcademicTeacher).filter(func.lower(AcademicTeacher.username) == username).first()
        is_new = False
        if not teacher:
            teacher = AcademicTeacher(id=str(uuid.uuid4()), username=username, full_name=username, created_at=_now(), updated_at=_now())
            counters.teachers += 1
            is_new = True
        changed = is_new
        changed |= self._set_if_changed(teacher, 'campus', _lower(campus) or None)
        changed |= self._set_if_changed(teacher, 'branch', _lower(branch) or None)
        changed |= self._set_if_changed(teacher, 'active', True)
        if changed:
            teacher.updated_at = _now()
            self.db.add(teacher)
            self.db.flush()
        return teacher

    def _get_or_create_student(self, item: dict[str, Any], campus: str | None, branch: str, counters: SyncCounters) -> AcademicStudent:
        username = _lower(item.get('username'))
        if not username:
            raise ValueError('Thiếu student username')
        student = self.db.query(AcademicStudent).filter(func.lower(AcademicStudent.username) == username).first()
        is_new = False
        if not student:
            student = AcademicStudent(id=str(uuid.uuid4()), username=username, full_name='', created_at=_now(), updated_at=_now())
            counters.students += 1
            is_new = True
        changed = is_new
        changed |= self._set_if_changed(student, 'student_code', _clean(item.get('student_code') or item.get('user_code')) or None)
        changed |= self._set_if_changed(student, 'email', _lower(item.get('email')) or None)
        changed |= self._set_if_changed(student, 'full_name', _clean(item.get('name') or item.get('full_name')) or student.full_name or username)
        changed |= self._set_if_changed(student, 'phone', _clean(item.get('phone')) or None)
        changed |= self._set_if_changed(student, 'campus', _lower(campus) or None)
        changed |= self._set_if_changed(student, 'branch', _lower(branch) or None)
        changed |= self._set_if_changed(student, 'active', True)
        changed |= self._set_json_if_changed(student, 'metadata_json', {'source': 'ap'})
        if changed:
            student.updated_at = _now()
            self.db.add(student)
            self.db.flush()
        return student

    def import_payload(self, payload: dict[str, Any], *, run: AcademicSyncRun | None = None, campus: str | None = None, branch: str = 'poly') -> SyncCounters:
        counters = SyncCounters()
        branch = _lower(branch) or 'poly'
        campus = _lower(campus) or None
        term_payload = payload.get('term') if isinstance(payload.get('term'), dict) else {}
        raw_class_items = payload.get('class') if isinstance(payload.get('class'), list) else []

        # v25.9.16.4.9 DB-growth guard: skip class shells that have no valid
        # students before creating term/block/subject/class/teacher records. AP
        # returns many campuses/subjects/classes; empty classes are not useful for
        # CMS-user mapping, enrollment, or progress dashboards.
        class_items: list[dict[str, Any]] = []
        student_items_by_ap_key: dict[str, list[dict[str, Any]]] = {}
        skip_empty_classes = bool(getattr(settings, 'academic_ap_skip_empty_classes', True))
        for raw in raw_class_items:
            if not isinstance(raw, dict):
                self._error(run, counters, 'class', 'unknown', 'Class payload không phải object', raw)
                continue
            ap_key = _clean(raw.get('id') or raw.get('group_name') or raw.get('class_code') or raw.get('classname') or str(len(class_items)))
            valid_students = self._valid_student_items(raw)
            if skip_empty_classes and not valid_students:
                counters.skipped_empty_classes += 1
                continue
            class_items.append(raw)
            student_items_by_ap_key[ap_key] = valid_students

        term: AcademicTerm | None = None
        blocks_by_ap: dict[str, AcademicBlock] = {}
        blocks_for_term: list[AcademicBlock] = []
        if term_payload:
            # Keep /semesters aligned with AP term.block even when a particular
            # get-data-cms response has no actionable class/student rows. The
            # signature/TTL cache prevents the many subject calls in one sync from
            # repeatedly touching the same term/block rows.
            term, blocks_by_ap, blocks_for_term = self._get_or_create_term_and_blocks_cached(term_payload, branch, counters)

        if not class_items:
            # No actionable class in this AP payload. Do not create term/block/subject
            # rows because that would bloat the DB with empty shells.
            if run:
                current = run.counters_json if isinstance(run.counters_json, dict) else {}
                run.counters_json = {**current, **counters.as_dict()}
            self.db.commit()
            return counters

        if class_items and not term_payload:
            first = class_items[0]
            term_payload = {'id': first.get('pterm_id'), 'term_name': first.get('pterm_name')}
            term, blocks_by_ap, blocks_for_term = self._get_or_create_term_and_blocks_cached(term_payload, branch, counters)
        if term is None:
            raise ValueError('Không xác định được kỳ học từ AP payload')
        for raw in class_items:
            if not isinstance(raw, dict):
                self._error(run, counters, 'class', 'unknown', 'Class payload không phải object', raw)
                continue
            try:
                # Savepoint per AP class keeps the session usable if one malformed
                # class/student row fails. This prevents the common SQLAlchemy
                # "transaction has been rolled back" cascade after a flush error.
                with self.db.begin_nested():
                    subject = self._get_or_create_subject(raw, branch, counters)
                    raw_block_id = _clean(raw.get('block_id'))
                    block, block_resolution = self._resolve_block_for_class(term, raw, blocks_by_ap, blocks_for_term, counters)
                    class_code = _clean(raw.get('group_name') or raw.get('class_code') or raw.get('classname'))
                    if not class_code:
                        raise ValueError('Thiếu class/group_name')
                    ap_class_id = _clean(raw.get('id')) or None
                    cls, is_new_class = self._resolve_class_row(
                        term=term,
                        block=block,
                        subject=subject,
                        class_code=class_code,
                        ap_class_id=ap_class_id,
                        counters=counters,
                    )

                    changed = is_new_class
                    changed |= self._set_if_changed(cls, 'ap_class_id', ap_class_id)
                    changed |= self._set_if_changed(cls, 'term_id', term.id)
                    changed |= self._set_if_changed(cls, 'block_id', block.id if block else None)
                    changed |= self._set_if_changed(cls, 'subject_id', subject.id)
                    changed |= self._set_if_changed(cls, 'class_code', class_code)
                    changed |= self._set_if_changed(cls, 'class_name', _clean(raw.get('classname') or raw.get('class_name') or class_code) or class_code)
                    changed |= self._set_if_changed(cls, 'campus', campus)
                    changed |= self._set_if_changed(cls, 'branch', branch)
                    changed |= self._set_if_changed(cls, 'start_date', _parse_date(raw.get('start_date')))
                    changed |= self._set_if_changed(cls, 'end_date', _parse_date(raw.get('end_date')))
                    changed |= self._set_if_changed(cls, 'active', True)
                    changed |= self._set_json_if_changed(cls, 'metadata_json', {
                        'source': 'ap',
                        'raw_keys': sorted(raw.keys()),
                        'ap_block_id': raw_block_id or None,
                        'block_resolution': block_resolution,
                    })
                    if changed:
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
                            self.db.add(assignment)
                        else:
                            assignment_changed = False
                            assignment_changed |= self._set_if_changed(assignment, 'campus', campus)
                            assignment_changed |= self._set_if_changed(assignment, 'branch', branch)
                            assignment_changed |= self._set_if_changed(assignment, 'source', 'ap')
                            if assignment_changed:
                                assignment.synced_at = _now()
                                self.db.add(assignment)
                    ap_key = _clean(raw.get('id') or raw.get('group_name') or raw.get('class_code') or raw.get('classname') or '')
                    student_items = student_items_by_ap_key.get(ap_key) or self._valid_student_items(raw)
                    for raw_student in student_items:
                        try:
                            student = self._get_or_create_student(raw_student, campus, branch, counters)
                            link = self.db.query(AcademicClassStudent).filter(AcademicClassStudent.class_id == cls.id, AcademicClassStudent.student_id == student.id).first()
                            if not link:
                                link = AcademicClassStudent(id=str(uuid.uuid4()), class_id=cls.id, student_id=student.id, source='ap', synced_at=_now())
                                counters.class_students += 1
                                self.db.add(link)
                            elif link.source != 'ap':
                                link.source = 'ap'
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
                    'description': 'Cơ sở AP',
                    'meta': {'source': 'academic_campuses', 'id': item.id, 'branch': item.branch, 'sort_order': item.sort_order},
                }
        if include_env:
            for index, code in enumerate(_parse_csv_codes(settings.academic_ap_campuses), start=1):
                if code and code not in values:
                    values[code] = {
                        'value': code,
                        'label': code.upper(),
                        'description': 'Cơ sở AP',
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
                        'description': 'Cơ sở AP',
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
                        f'Không lấy được danh sách môn từ AP cho kỳ {term_name}. '
                        'Hãy kiểm tra API key/kết nối AP hoặc chọn phạm vi Theo môn với mã môn cụ thể. '
                        f'Chi tiết: {exc}'
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
            warnings.append('Chưa có kỳ trong AI Server. Hãy tạo kỳ tại /semesters trước khi đồng bộ AP.')

        subjects: list[dict[str, Any]] = []
        if include_subjects:
            catalog: list[dict[str, Any]] = []
            if term_name and _clean(term_name):
                try:
                    catalog = APAcademicClient().get_subjects(branch=normalized_branch, term_name=_clean(term_name))
                except Exception as exc:
                    warnings.append('Không tải được môn từ AP, đang dùng dữ liệu môn đã lưu nếu có.')
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
        run: AcademicSyncRun | None = None,
    ) -> tuple[AcademicSyncRun, SyncCounters]:
        scope = _lower(sync_scope or 'campus')
        resolved_campuses = self._resolve_campuses(sync_scope=scope, campus=campus, campuses=campuses, branch=branch)
        run_campus = ','.join(resolved_campuses[:10]) + ('...' if len(resolved_campuses) > 10 else '')
        mode = f'api_{scope}_dry_run' if dry_run else f'api_{scope}'
        if run is None:
            run = self.create_run(
                source='ap',
                mode=mode,
                requested_by=requested_by,
                term_name=term_name,
                campus=run_campus,
                branch=branch,
            )
        else:
            run.source = 'ap'
            run.mode = mode
            run.status = 'running'
            run.requested_by = requested_by or run.requested_by
            run.term_name = term_name
            run.campus = run_campus
            run.branch = _lower(branch) or run.branch or 'poly'
            run.started_at = run.started_at or _now()
            run.error_message = ''
            run.finished_at = None
            self.db.add(run)
            self.db.commit()
            self.db.refresh(run)
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
        estimated_total = max(1, len(resolved_campuses))
        self.update_run_progress(run, current=0, total=estimated_total, label='Đã đưa job đồng bộ AP vào hàng đợi xử lý', plan=planned, counters=counters)
        try:
            for campus_index, campus_code in enumerate(resolved_campuses, start=1):
                self.update_run_progress(run, current=max(0, campus_index - 1), total=estimated_total, label=f'Đang lấy danh sách môn từ AP cho cơ sở {campus_code}', plan=planned, counters=counters)
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
                estimated_total = max(estimated_total, sum(int(item.get('count') or 0) for item in planned['subjects_by_campus'].values()) or len(resolved_campuses))
                self.update_run_progress(run, current=min(estimated_total - 1, sum(int(item.get('count') or 0) for item in list(planned['subjects_by_campus'].values())[:campus_index - 1])), total=estimated_total, label=f'Đã xác định {len(codes)} môn cho cơ sở {campus_code}', plan=planned, counters=counters)
                if dry_run:
                    continue
                catalog_key = f'{_lower(branch) or "poly"}:{term_name}:{source}'
                if (
                    catalog
                    and catalog_key not in imported_catalog_keys
                    and bool(getattr(settings, 'academic_ap_import_catalog_subjects', False))
                ):
                    # Discovery catalog import is disabled by default to avoid DB
                    # bloat. Subjects are normally persisted only when /get-data-cms
                    # returns at least one class with students for that subject.
                    self.import_subject_catalog(catalog, branch=branch, counters=counters)
                    imported_catalog_keys.add(catalog_key)
                completed_before_campus = sum(int(item.get('count') or 0) for item in list(planned['subjects_by_campus'].values())[:campus_index - 1])
                for subject_index, code in enumerate(codes, start=1):
                    try:
                        self.update_run_progress(run, current=min(estimated_total - 1, completed_before_campus + subject_index - 1), total=estimated_total, label=f'Đang gọi AP /get-data-cms cho {campus_code} · {code}', plan=planned, counters=counters)
                        payload = client.get_division(campus=campus_code, term_name=term_name, subject_code=code)
                        if not payload:
                            self._error(run, counters, 'ap_subject', f'{campus_code}:{code}', 'AP trả payload rỗng', {'campus': campus_code, 'subject_code': code})
                            continue
                        imported = self.import_payload(payload, run=run, campus=campus_code, branch=branch)
                        for key, value in imported.as_dict().items():
                            setattr(counters, key, getattr(counters, key) + value)
                        self.update_run_progress(run, current=min(estimated_total, completed_before_campus + subject_index), total=estimated_total, label=f'Đã đồng bộ {campus_code} · {code}', plan=planned, counters=counters)
                    except Exception as exc:
                        self._error(run, counters, 'ap_subject', f'{campus_code}:{code}', str(exc), {'campus': campus_code, 'subject_code': code})
            if dry_run:
                counters.subjects = sum(item['count'] for item in planned['subjects_by_campus'].values())
                run.counters_json = {**counters.as_dict(), 'plan': planned, 'progress': {'current': estimated_total, 'total': estimated_total, 'label': 'Đã kiểm tra kế hoạch đồng bộ AP', 'updated_at': _now().isoformat()}}
                return self.finish_run(run, counters), counters
            current = run.counters_json or {}
            run.counters_json = {**current, **counters.as_dict(), 'plan': planned, 'progress': {'current': estimated_total, 'total': estimated_total, 'label': 'Đã đồng bộ AP', 'updated_at': _now().isoformat()}}
            return self.finish_run(run, counters), counters
        except Exception as exc:
            self.db.rollback()
            return self.finish_run(run, counters, error=str(exc)), counters

