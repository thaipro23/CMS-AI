#!/usr/bin/env python3
"""Read-only Question Bank schema/data health report.

Safe to run inside the AI backend image. It never mutates data and never prints
connection URLs or secrets. Use Alembic for repairs; do not edit alembic_version
manually.
"""
from __future__ import annotations

import json
from sqlalchemy import inspect, text

from app.db.session import engine


REQUIRED_COLUMNS = {
    'ai_questions': {
        'id', 'bank_version_id', 'status', 'is_retired', 'is_duplicate',
        'openedx_publish_status', 'publish_status', 'pedagogy_json',
    },
    'ai_question_review_logs': {'id', 'question_id', 'old_status', 'new_status'},
    'ai_question_bank_versions': {'id', 'chapter_id', 'status'},
}

PUBLISHED_STATES = (
    'published', 'verified', 'success',
    'published_with_tag_warning', 'published_ok_stale_verify',
)
CANONICAL_STATUSES = {'pending_review', 'approved', 'rejected', 'draft_error', 'published'}
EXPECTED_ALEMBIC_REVISION = '0061_v25_9_16_7_2_64_39'


def scalar(conn, sql: str, params: dict | None = None) -> int:
    return int(conn.execute(text(sql), params or {}).scalar() or 0)


def main() -> int:
    inspector = inspect(engine)
    missing_tables: list[str] = []
    missing_columns: dict[str, list[str]] = {}
    for table_name, required in REQUIRED_COLUMNS.items():
        if not inspector.has_table(table_name):
            missing_tables.append(table_name)
            continue
        actual = {str(c.get('name')) for c in inspector.get_columns(table_name)}
        missing = sorted(required - actual)
        if missing:
            missing_columns[table_name] = missing

    report: dict = {
        'ok': not missing_tables and not missing_columns,
        'schema': {
            'missing_tables': sorted(missing_tables),
            'missing_columns': missing_columns,
            'expected_alembic_revision': EXPECTED_ALEMBIC_REVISION,
            'migration_ready': False,
            'alembic_versions': [],
        },
        'question_bank': {},
    }

    with engine.connect() as conn:
        if inspector.has_table('alembic_version'):
            report['schema']['alembic_versions'] = sorted(str(row[0]) for row in conn.execute(text('SELECT version_num FROM alembic_version')).all())
            report['schema']['migration_ready'] = EXPECTED_ALEMBIC_REVISION in report['schema']['alembic_versions']

        if inspector.has_table('ai_questions'):
            status_rows = conn.execute(text(
                "SELECT COALESCE(NULLIF(TRIM(status), ''), '<NULL_OR_BLANK>') AS status, COUNT(*) "
                "FROM ai_questions WHERE bank_version_id IS NOT NULL GROUP BY 1 ORDER BY 2 DESC"
            )).all()
            distribution = {str(status): int(count) for status, count in status_rows}
            unknown = sum(count for status, count in distribution.items() if status not in CANONICAL_STATUSES)
            report['question_bank']['status_distribution'] = distribution
            report['question_bank']['unknown_or_legacy_status_count'] = int(unknown)
            report['question_bank']['null_is_retired_count'] = scalar(conn, "SELECT COUNT(*) FROM ai_questions WHERE bank_version_id IS NOT NULL AND is_retired IS NULL") if 'is_retired' in {str(c.get('name')) for c in inspector.get_columns('ai_questions')} else None

            qcols = {str(c.get('name')) for c in inspector.get_columns('ai_questions')}
            lifecycle_parts = []
            params = {f'p{i}': value for i, value in enumerate(PUBLISHED_STATES)}
            placeholders = ', '.join(f':p{i}' for i in range(len(PUBLISHED_STATES)))
            if 'openedx_publish_status' in qcols:
                lifecycle_parts.append(f"LOWER(COALESCE(openedx_publish_status, '')) IN ({placeholders})")
            if 'publish_status' in qcols:
                lifecycle_parts.append(f"LOWER(COALESCE(publish_status, '')) IN ({placeholders})")
            if lifecycle_parts:
                report['question_bank']['published_lifecycle_status_drift_count'] = scalar(
                    conn,
                    "SELECT COUNT(*) FROM ai_questions WHERE bank_version_id IS NOT NULL "
                    "AND (" + " OR ".join(lifecycle_parts) + ") "
                    "AND LOWER(COALESCE(status, '')) <> 'published'",
                    params,
                )

        if inspector.has_table('ai_question_review_logs'):
            report['question_bank']['blank_review_log_status_count'] = scalar(
                conn,
                "SELECT COUNT(*) FROM ai_question_review_logs "
                "WHERE old_status IS NULL OR TRIM(old_status) = '' OR new_status IS NULL OR TRIM(new_status) = ''",
            )

        if inspector.has_table('ai_question_search_documents') and inspector.has_table('ai_questions'):
            report['question_bank']['search_status_mismatch_count'] = scalar(
                conn,
                "SELECT COUNT(*) FROM ai_question_search_documents d "
                "JOIN ai_questions q ON q.id = d.question_id "
                "WHERE COALESCE(d.status, '') <> COALESCE(q.status, '')",
            )

    migration_needed = bool(
        missing_tables
        or missing_columns
        or not report['schema'].get('migration_ready')
        or report['question_bank'].get('published_lifecycle_status_drift_count', 0)
        or report['question_bank'].get('blank_review_log_status_count', 0)
    )
    unknown_statuses = int(report['question_bank'].get('unknown_or_legacy_status_count', 0) or 0)
    blocking = migration_needed or unknown_statuses > 0
    report['ok'] = not blocking
    actions: list[str] = []
    if migration_needed:
        actions.append('alembic -c alembic.ini upgrade head')
    if unknown_statuses:
        actions.append('inspect unknown Question.status values; map them explicitly before Release (do not guess or mass-delete)')
    report['recommended_actions'] = actions or ['none']
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if report['ok'] else 2


if __name__ == '__main__':
    raise SystemExit(main())
