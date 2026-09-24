from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func

from app.core.json_safe import json_safe_value
from app.models.academic import AcademicCampus, AcademicTeacherReportSnapshot


REPORT_SNAPSHOT_SCHEMA_VERSION = 'teacher-report-snapshot.v1'
REPORT_SNAPSHOT_POLICY_VERSION = 'teacher-report-campus.v1'


class ReportSnapshotError(RuntimeError):
    pass


def _normalized(value: Any) -> str:
    return str(value or '').strip().lower()


def _iso_utc(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat()


def _canonical_bytes(payload: dict[str, Any]) -> bytes:
    return json.dumps(
        json_safe_value(payload),
        ensure_ascii=False,
        sort_keys=True,
        separators=(',', ':'),
    ).encode('utf-8')


def validate_report_branch(report: dict[str, Any], *, branch: str) -> dict[str, int]:
    expected_branch = _normalized(branch)
    if not expected_branch:
        raise ReportSnapshotError('Report branch scope is invalid.')
    if not isinstance(report, dict):
        raise ReportSnapshotError('Report branch payload must be an object.')

    teacher_ids: set[str] = set()
    class_ids: set[str] = set()
    for teacher in report.get('items') or []:
        teacher = teacher or {}
        teacher_id = str(teacher.get('teacher_id') or '').strip()
        if not teacher_id:
            raise ReportSnapshotError('Report branch row is missing stable teacher_id.')
        teacher_ids.add(teacher_id)
        class_branches: set[str] = set()
        for class_item in teacher.get('classes') or []:
            class_item = class_item or {}
            class_id = str(class_item.get('class_id') or '').strip()
            if not class_id:
                raise ReportSnapshotError('Report branch row is missing stable class_id.')
            class_branch = _normalized(class_item.get('branch'))
            if class_branch != expected_branch:
                raise ReportSnapshotError('Report class branch is outside its scheduled branch scope.')
            class_branches.add(class_branch)
            class_ids.add(class_id)
        if len(class_branches) > 1:
            raise ReportSnapshotError('Report teacher classes span multiple branches.')
        teacher_branch = _normalized(teacher.get('branch'))
        effective_teacher_branch = teacher_branch or next(iter(class_branches), '')
        if effective_teacher_branch != expected_branch:
            raise ReportSnapshotError('Report teacher branch is outside its scheduled branch scope.')

    return {
        'teacher_count': len(teacher_ids),
        'class_count': len(class_ids),
    }


def validate_campus_report(
    report: dict[str, Any],
    *,
    campus: str,
    branch: str,
) -> dict[str, int]:
    expected_campus = _normalized(campus)
    if not expected_campus or expected_campus == 'ho':
        raise ReportSnapshotError('Campus snapshot scope is invalid.')
    if not isinstance(report, dict):
        raise ReportSnapshotError('Campus snapshot report must be an object.')
    branch_counts = validate_report_branch(report, branch=branch)

    teacher_ids: set[str] = set()
    class_ids: set[str] = set()
    student_ids: set[str] = set()
    for teacher in report.get('items') or []:
        teacher_id = str((teacher or {}).get('teacher_id') or '').strip()
        if not teacher_id:
            raise ReportSnapshotError('Campus snapshot row is missing stable teacher_id.')
        teacher_ids.add(teacher_id)
        for class_item in (teacher or {}).get('classes') or []:
            class_id = str((class_item or {}).get('class_id') or '').strip()
            if not class_id:
                raise ReportSnapshotError('Campus snapshot row is missing stable class_id.')
            if _normalized((class_item or {}).get('campus')) != expected_campus:
                raise ReportSnapshotError('Campus snapshot class is outside its one-campus scope.')
            class_ids.add(class_id)

    for student in report.get('student_watch_rows') or []:
        teacher_id = str((student or {}).get('teacher_id') or '').strip()
        class_id = str((student or {}).get('class_id') or '').strip()
        student_id = str((student or {}).get('student_id') or '').strip()
        if not teacher_id:
            raise ReportSnapshotError('Campus snapshot student row is missing stable teacher_id.')
        if not class_id:
            raise ReportSnapshotError('Campus snapshot student row is missing stable class_id.')
        if not student_id:
            raise ReportSnapshotError('Campus snapshot student row is missing stable student_id.')
        if teacher_id not in teacher_ids or class_id not in class_ids:
            raise ReportSnapshotError('Campus snapshot student row does not belong to its teacher/class scope.')
        student_ids.add(student_id)

    summary = report.get('summary') if isinstance(report.get('summary'), dict) else {}
    return {
        'teacher_count': branch_counts['teacher_count'],
        'class_count': branch_counts['class_count'],
        'student_count': len(student_ids) or int(summary.get('student_count') or 0),
    }


def create_campus_snapshot(
    db,
    *,
    storage,
    parent_id: str,
    term_id: str,
    branch: str,
    campus: str,
    scope_hash: str,
    source_child_ids: list[str],
    source_synced_at: datetime,
    report: dict[str, Any],
    source_class_ids: list[str] | None = None,
    term_label: str | None = None,
    run_date_vn: str | None = None,
) -> AcademicTeacherReportSnapshot:
    normalized_branch = _normalized(branch) or 'poly'
    normalized_campus = _normalized(campus)
    counts = validate_campus_report(
        report,
        campus=normalized_campus,
        branch=normalized_branch,
    )
    child_ids = sorted({str(item).strip() for item in source_child_ids if str(item).strip()})
    if not child_ids:
        raise ReportSnapshotError('Campus snapshot source_child_ids is empty.')
    report_class_ids = {
        str(class_item.get('class_id') or '').strip()
        for teacher in (report.get('items') or [])
        for class_item in (teacher.get('classes') or [])
        if str(class_item.get('class_id') or '').strip()
    }
    class_ids = sorted({
        str(item).strip()
        for item in (source_class_ids if source_class_ids is not None else report_class_ids)
        if str(item).strip()
    })
    if not report_class_ids.issubset(set(class_ids)):
        raise ReportSnapshotError('Campus snapshot report contains a class outside its frozen class scope.')

    envelope = {
        'schema_version': REPORT_SNAPSHOT_SCHEMA_VERSION,
        'policy_version': REPORT_SNAPSHOT_POLICY_VERSION,
        'parent_job_id': str(parent_id),
        'term_id': str(term_id),
        'term_label': str(term_label or term_id),
        'branch': normalized_branch,
        'scope_type': 'campus',
        'campus': normalized_campus,
        'scope_hash': str(scope_hash or ''),
        'run_date_vn': str(run_date_vn or source_synced_at.date().isoformat()),
        'source_child_ids': child_ids,
        'source_class_ids': class_ids,
        'source_synced_at': _iso_utc(source_synced_at),
        'counts': counts,
        'report': json_safe_value(report),
    }
    raw = _canonical_bytes(envelope)
    digest = hashlib.sha256(raw).hexdigest()

    existing = db.query(AcademicTeacherReportSnapshot).filter(
        AcademicTeacherReportSnapshot.parent_job_id == str(parent_id),
        AcademicTeacherReportSnapshot.scope_type == 'campus',
        AcademicTeacherReportSnapshot.campus == normalized_campus,
    ).one_or_none()
    if existing is not None:
        if existing.sha256 != digest:
            raise ReportSnapshotError('Immutable campus snapshot already exists with a different checksum.')
        return existing

    object_key = (
        f'teacher-report-snapshots/{parent_id}/campus/'
        f'{normalized_campus}/payload-{digest}.json'
    )
    storage_reference = storage.put_bytes(object_key, raw, content_type='application/json')
    row = AcademicTeacherReportSnapshot(
        parent_job_id=str(parent_id),
        term_id=str(term_id),
        branch=normalized_branch,
        scope_type='campus',
        campus=normalized_campus,
        policy_version=REPORT_SNAPSHOT_POLICY_VERSION,
        storage_key=storage_reference,
        sha256=digest,
        size_bytes=len(raw),
        counts_json=json_safe_value(counts),
        metadata_json=json_safe_value({
            'schema_version': REPORT_SNAPSHOT_SCHEMA_VERSION,
            'scope_hash': str(scope_hash or ''),
            'term_label': str(term_label or term_id),
            'run_date_vn': str(run_date_vn or source_synced_at.date().isoformat()),
            'source_child_ids': child_ids,
            'source_class_ids': class_ids,
            'source_synced_at': _iso_utc(source_synced_at),
            'object_key': object_key,
        }),
    )
    db.add(row)
    db.flush()
    return row


def _aggregate_campus_reports(campus_reports: list[dict[str, Any]]) -> dict[str, Any]:
    teacher_rows: dict[str, dict[str, Any]] = {}
    teacher_class_ids: dict[str, set[str]] = {}
    teacher_subject_ids: dict[str, set[str]] = {}
    teacher_metrics: dict[str, dict[str, Any]] = {}
    student_rows: dict[tuple[str, str, str], dict[str, Any]] = {}
    all_subject_ids: set[str] = set()
    all_student_ids: set[str] = set()

    derived_teacher_keys = {
        'teacher_id', 'campus', 'classes', 'class_count', 'subject_count',
        'subject_codes', 'unique_student_count', 'learning_avg_progress_percent',
        'learning_avg_grade_percent', 'learning_avg_grade_10',
        'udemy_progress_average_percent', 'last_synced_at',
        'udemy_progress_last_imported_at', 'status_counts', 'learning_alerts',
    }
    for report in campus_reports:
        for source in report.get('items') or []:
            teacher_id = str(source.get('teacher_id') or '').strip()
            target = teacher_rows.get(teacher_id)
            if target is None:
                target = dict(source)
                target['campus'] = 'ho'
                target['classes'] = []
                target['status_counts'] = {}
                target['learning_alerts'] = []
                teacher_rows[teacher_id] = target
                teacher_class_ids[teacher_id] = set()
                teacher_subject_ids[teacher_id] = set()
                teacher_metrics[teacher_id] = {
                    'progress_sum': 0.0,
                    'progress_weight': 0,
                    'grade_sum': 0.0,
                    'grade_weight': 0,
                    'udemy_sum': 0.0,
                    'udemy_weight': 0,
                    'last_synced_at': None,
                    'udemy_progress_last_imported_at': None,
                }
                for key, value in list(target.items()):
                    if key not in derived_teacher_keys and isinstance(value, (int, float)) and not isinstance(value, bool):
                        target[key] = 0

            for key, value in source.items():
                if key in derived_teacher_keys or isinstance(value, bool):
                    continue
                if isinstance(value, (int, float)):
                    target[key] = (target.get(key) or 0) + value
            for key, value in (source.get('status_counts') or {}).items():
                target['status_counts'][key] = int(target['status_counts'].get(key) or 0) + int(value or 0)
            metrics = teacher_metrics[teacher_id]
            learning_weight = int(source.get('learning_synced_count') or 0)
            if learning_weight and source.get('learning_avg_progress_percent') is not None:
                metrics['progress_sum'] += float(source['learning_avg_progress_percent']) * learning_weight
                metrics['progress_weight'] += learning_weight
            if learning_weight and source.get('learning_avg_grade_percent') is not None:
                metrics['grade_sum'] += float(source['learning_avg_grade_percent']) * learning_weight
                metrics['grade_weight'] += learning_weight
            udemy_weight = int(source.get('udemy_progress_student_count') or 0)
            if udemy_weight and source.get('udemy_progress_average_percent') is not None:
                metrics['udemy_sum'] += float(source['udemy_progress_average_percent']) * udemy_weight
                metrics['udemy_weight'] += udemy_weight
            for date_key in ('last_synced_at', 'udemy_progress_last_imported_at'):
                value = source.get(date_key)
                if value is not None and (
                    metrics[date_key] is None or str(value) > str(metrics[date_key])
                ):
                    metrics[date_key] = value
            target['learning_alerts'] = sorted({
                *target.get('learning_alerts', []),
                *(source.get('learning_alerts') or []),
            })
            for class_item in source.get('classes') or []:
                class_id = str(class_item.get('class_id') or '').strip()
                if class_id in teacher_class_ids[teacher_id]:
                    continue
                teacher_class_ids[teacher_id].add(class_id)
                subject_id = str(class_item.get('subject_id') or '').strip()
                if subject_id:
                    teacher_subject_ids[teacher_id].add(subject_id)
                    all_subject_ids.add(subject_id)
                target['classes'].append(dict(class_item))

        for row in report.get('student_watch_rows') or []:
            teacher_id = str(row.get('teacher_id') or '').strip()
            class_id = str(row.get('class_id') or '').strip()
            student_id = str(row.get('student_id') or '').strip()
            key = (teacher_id, class_id, student_id)
            student_rows.setdefault(key, dict(row))
            all_student_ids.add(student_id)

    for teacher_id, target in teacher_rows.items():
        target['classes'] = sorted(
            target['classes'],
            key=lambda item: (str(item.get('campus') or ''), str(item.get('class_code') or '')),
        )
        target['class_count'] = len(teacher_class_ids[teacher_id])
        target['subject_count'] = len(teacher_subject_ids[teacher_id])
        target['subject_codes'] = sorted({
            str(item.get('subject_code'))
            for item in target['classes']
            if str(item.get('subject_code') or '').strip()
        })
        target_student_ids = {
            student_id
            for row_teacher_id, _class_id, student_id in student_rows
            if row_teacher_id == teacher_id
        }
        target['unique_student_count'] = len(target_student_ids)
        metrics = teacher_metrics[teacher_id]
        target['learning_avg_progress_percent'] = (
            round(metrics['progress_sum'] / metrics['progress_weight'], 2)
            if metrics['progress_weight'] else None
        )
        target['learning_avg_grade_percent'] = (
            round(metrics['grade_sum'] / metrics['grade_weight'], 2)
            if metrics['grade_weight'] else None
        )
        target['learning_avg_grade_10'] = (
            round(target['learning_avg_grade_percent'] / 10, 2)
            if target['learning_avg_grade_percent'] is not None else None
        )
        target['udemy_progress_average_percent'] = (
            round(metrics['udemy_sum'] / metrics['udemy_weight'], 2)
            if metrics['udemy_weight'] else None
        )
        target['last_synced_at'] = metrics['last_synced_at']
        target['udemy_progress_last_imported_at'] = metrics['udemy_progress_last_imported_at']

    summary: dict[str, Any] = {}
    derived_summary_keys = {
        'teacher_count', 'subject_count', 'unique_student_count',
        'udemy_progress_average_percent',
    }
    for report in campus_reports:
        for key, value in (report.get('summary') or {}).items():
            if key in derived_summary_keys or isinstance(value, bool):
                continue
            if isinstance(value, (int, float)):
                summary[key] = (summary.get(key) or 0) + value
    summary.update({
        'teacher_count': len(teacher_rows),
        'subject_count': len(all_subject_ids),
        'unique_student_count': len(all_student_ids),
    })
    udemy_weight = sum(int((report.get('summary') or {}).get('udemy_progress_student_count') or 0) for report in campus_reports)
    summary['udemy_progress_average_percent'] = (
        round(
            sum(
                float((report.get('summary') or {}).get('udemy_progress_average_percent') or 0)
                * int((report.get('summary') or {}).get('udemy_progress_student_count') or 0)
                for report in campus_reports
            ) / udemy_weight,
            2,
        )
        if udemy_weight else None
    )
    items = sorted(teacher_rows.values(), key=lambda item: (str(item.get('teacher_name') or ''), str(item.get('teacher_id') or '')))
    return {
        'items': items,
        'student_watch_rows': [student_rows[key] for key in sorted(student_rows)],
        'summary': summary,
        'summary_scope': 'frozen_ho_snapshot',
        'total': len(items),
        'page': 1,
        'page_size': len(items) or 1,
        'total_pages': 1 if items else 0,
        'has_next': False,
        'cache': {'status': 'immutable_snapshot', 'scope_key': None},
    }


def create_ho_snapshot(
    db,
    *,
    storage,
    parent_id: str,
    term_id: str,
    branch: str,
    scope_hash: str,
    expected_campuses: list[str],
    campus_snapshots: list[AcademicTeacherReportSnapshot],
    source_synced_at: datetime,
) -> AcademicTeacherReportSnapshot:
    normalized_branch = _normalized(branch) or 'poly'
    campuses = sorted({_normalized(item) for item in expected_campuses if _normalized(item)})
    owned_campuses = {
        _normalized(row.campus_code)
        for row in db.query(AcademicCampus).filter(
            AcademicCampus.active.is_(True),
            func.lower(AcademicCampus.branch) == normalized_branch,
            func.lower(AcademicCampus.campus_code).in_(campuses),
        ).all()
    }
    if owned_campuses != set(campuses):
        raise ReportSnapshotError('HO source campus ownership does not match the requested branch.')
    row_campuses = [_normalized(row.campus) for row in campus_snapshots]
    if len(row_campuses) != len(set(row_campuses)):
        raise ReportSnapshotError('HO source contains a duplicate campus snapshot.')
    if set(row_campuses) != set(campuses):
        raise ReportSnapshotError('HO source campus set does not match frozen parent campus set.')

    ordered_rows = sorted(campus_snapshots, key=lambda row: _normalized(row.campus))
    envelopes: list[dict[str, Any]] = []
    for row in ordered_rows:
        if not row.sha256:
            raise ReportSnapshotError('HO source campus snapshot checksum is missing.')
        metadata = row.metadata_json if isinstance(row.metadata_json, dict) else {}
        if str(metadata.get('scope_hash') or '') != str(scope_hash or ''):
            raise ReportSnapshotError('HO source campus snapshot scope_hash mismatch.')
        envelope = load_snapshot_envelope(
            db,
            storage=storage,
            snapshot_id=str(row.id),
            expected_parent_id=str(parent_id),
            expected_term_id=str(term_id),
            expected_branch=normalized_branch,
            expected_campus=str(row.campus),
        )
        if str(envelope.get('scope_hash') or '') != str(scope_hash or ''):
            raise ReportSnapshotError('HO source campus snapshot payload scope_hash mismatch.')
        envelopes.append(envelope)

    report = _aggregate_campus_reports([envelope['report'] for envelope in envelopes])
    validate_report_branch(report, branch=normalized_branch)
    term_labels = {str(envelope.get('term_label') or '') for envelope in envelopes}
    run_dates = {str(envelope.get('run_date_vn') or '') for envelope in envelopes}
    if len(term_labels) != 1 or not next(iter(term_labels), ''):
        raise ReportSnapshotError('HO source campus snapshot term_label mismatch.')
    if len(run_dates) != 1 or not next(iter(run_dates), ''):
        raise ReportSnapshotError('HO source campus snapshot run_date_vn mismatch.')
    term_label = next(iter(term_labels))
    run_date_vn = next(iter(run_dates))
    source_child_ids = sorted({
        str(child_id)
        for envelope in envelopes
        for child_id in (envelope.get('source_child_ids') or [])
        if str(child_id).strip()
    })
    source_snapshot_ids = [str(row.id) for row in ordered_rows]
    source_checksums = {str(row.id): str(row.sha256) for row in ordered_rows}
    counts = {
        'teacher_count': int((report.get('summary') or {}).get('teacher_count') or 0),
        'class_count': int((report.get('summary') or {}).get('class_count') or 0),
        'student_count': int((report.get('summary') or {}).get('unique_student_count') or 0),
    }
    envelope = {
        'schema_version': REPORT_SNAPSHOT_SCHEMA_VERSION,
        'policy_version': REPORT_SNAPSHOT_POLICY_VERSION,
        'parent_job_id': str(parent_id),
        'term_id': str(term_id),
        'term_label': term_label,
        'branch': normalized_branch,
        'scope_type': 'ho',
        'campus': None,
        'campuses': campuses,
        'scope_hash': str(scope_hash or ''),
        'run_date_vn': run_date_vn,
        'source_child_ids': source_child_ids,
        'source_campus_snapshot_ids': source_snapshot_ids,
        'source_campus_checksums': source_checksums,
        'source_synced_at': _iso_utc(source_synced_at),
        'counts': counts,
        'report': report,
    }
    raw = _canonical_bytes(envelope)
    digest = hashlib.sha256(raw).hexdigest()
    existing = db.query(AcademicTeacherReportSnapshot).filter(
        AcademicTeacherReportSnapshot.parent_job_id == str(parent_id),
        AcademicTeacherReportSnapshot.scope_type == 'ho',
    ).one_or_none()
    if existing is not None:
        if existing.sha256 != digest:
            raise ReportSnapshotError('Immutable HO snapshot already exists with a different checksum.')
        return existing

    object_key = f'teacher-report-snapshots/{parent_id}/ho/payload-{digest}.json'
    storage_reference = storage.put_bytes(object_key, raw, content_type='application/json')
    row = AcademicTeacherReportSnapshot(
        parent_job_id=str(parent_id),
        term_id=str(term_id),
        branch=normalized_branch,
        scope_type='ho',
        campus=None,
        policy_version=REPORT_SNAPSHOT_POLICY_VERSION,
        storage_key=storage_reference,
        sha256=digest,
        size_bytes=len(raw),
        counts_json=json_safe_value(counts),
        metadata_json=json_safe_value({
            'schema_version': REPORT_SNAPSHOT_SCHEMA_VERSION,
            'scope_hash': str(scope_hash or ''),
            'term_label': term_label,
            'run_date_vn': run_date_vn,
            'campuses': campuses,
            'source_child_ids': source_child_ids,
            'source_campus_snapshot_ids': source_snapshot_ids,
            'source_campus_checksums': source_checksums,
            'source_synced_at': _iso_utc(source_synced_at),
            'object_key': object_key,
        }),
    )
    db.add(row)
    db.flush()
    return row


def load_snapshot_envelope(
    db,
    *,
    storage,
    snapshot_id: str,
    expected_parent_id: str,
    expected_term_id: str,
    expected_branch: str,
    expected_campus: str | None,
) -> dict[str, Any]:
    row = db.get(AcademicTeacherReportSnapshot, str(snapshot_id))
    if row is None:
        raise ReportSnapshotError('Immutable report snapshot was not found.')
    expected = {
        'parent_job_id': str(expected_parent_id),
        'term_id': str(expected_term_id),
        'branch': _normalized(expected_branch) or 'poly',
        'campus': _normalized(expected_campus) or None,
    }
    actual = {
        'parent_job_id': str(row.parent_job_id),
        'term_id': str(row.term_id),
        'branch': _normalized(row.branch) or 'poly',
        'campus': _normalized(row.campus) or None,
    }
    for field, expected_value in expected.items():
        if actual[field] != expected_value:
            raise ReportSnapshotError(f'Immutable report snapshot {field} mismatch.')
    if row.scope_type != ('campus' if expected_campus else 'ho'):
        raise ReportSnapshotError('Immutable report snapshot scope_type mismatch.')
    if row.policy_version != REPORT_SNAPSHOT_POLICY_VERSION:
        raise ReportSnapshotError('Immutable report snapshot policy_version mismatch.')

    raw = storage.read_bytes(row.storage_key)
    digest = hashlib.sha256(raw).hexdigest()
    if not row.sha256 or digest != row.sha256 or len(raw) != int(row.size_bytes or 0):
        raise ReportSnapshotError('Immutable report snapshot checksum mismatch.')
    try:
        envelope = json.loads(raw.decode('utf-8'))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ReportSnapshotError('Immutable report snapshot JSON is invalid.') from exc
    if not isinstance(envelope, dict):
        raise ReportSnapshotError('Immutable report snapshot envelope is invalid.')
    if envelope.get('schema_version') != REPORT_SNAPSHOT_SCHEMA_VERSION:
        raise ReportSnapshotError('Immutable report snapshot schema_version mismatch.')
    if envelope.get('policy_version') != REPORT_SNAPSHOT_POLICY_VERSION:
        raise ReportSnapshotError('Immutable report snapshot payload policy_version mismatch.')
    for field, expected_value in expected.items():
        if (_normalized(envelope.get(field)) or None) != (_normalized(expected_value) or None):
            raise ReportSnapshotError(f'Immutable report snapshot payload {field} mismatch.')
    if row.scope_type == 'campus':
        validate_campus_report(
            envelope.get('report') or {},
            campus=str(row.campus),
            branch=str(row.branch),
        )
    return envelope
