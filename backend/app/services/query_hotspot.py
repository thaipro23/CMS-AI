from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from app.core.config import settings


@dataclass
class QueryHotspotItem:
    file: str
    line: int
    code: str
    severity: str
    reason: str


class QueryHotspotService:
    """Static query hotspot scanner for release/load hardening.

    This report is read-only and intentionally static: it scans source files for
    risky unbounded ORM patterns so reviewers can keep the hot endpoints honest.
    It does not import routes, query the database, run EXPLAIN, enqueue jobs, or
    mutate data. It complements performance readiness; it is not a replacement
    for pg_stat_statements/EXPLAIN on UAT.
    """

    SOURCE_DIRS = [
        'backend/app/api/routes',
        'backend/app/services',
        'openedx-connector-plugin/openedx_ai_connector',
        'openedx-unit-reset-plugin/openedx_unit_reset',
    ]
    IGNORE_PARTS = {'tests', 'alembic', '__pycache__', '.pytest_cache'}
    HIGH_RISK_TOKENS = (
        'Question', 'ContentChunk', 'AuditLog', 'GenerationJob', 'GenerationBatch',
        'AcademicClassStudent', 'AcademicClass', 'TrackingEvent', 'LearningBehavior',
        'BankMaterialChunk', 'BankOperationJob', 'CourseQuizInstance',
    )
    SAFE_HINTS = (
        '.limit(', '.offset(', '.group_by(', '.with_entities(', 'func.count',
        '.first()', '.one_or_none()', 'in_(', 'ids)', 'node_ids', 'allowed_class_ids',
    )

    def __init__(self, root: Path | None = None):
        self.root = root or Path(__file__).resolve().parents[3]

    def report(self, *, max_items: int = 100) -> dict[str, Any]:
        items = self.scan(max_items=max_items)
        counts = Counter(item.severity for item in items)
        blockers = [item for item in items if item.severity == 'BLOCKER']
        warnings = [item for item in items if item.severity == 'WARNING']
        status = 'BLOCKED' if blockers else ('READY_WITH_WARNINGS' if warnings else 'READY')
        return {
            'version': settings.app_version,
            'report_type': 'query_hotspot_static_scan',
            'status': status,
            'blocker_count': len(blockers),
            'warning_count': len(warnings),
            'info_count': counts.get('INFO', 0),
            'items': [asdict(item) for item in items],
            'summary': {
                'source_dirs': self.SOURCE_DIRS,
                'scanned_files': self._scanned_file_count(),
                'max_items': max_items,
            },
            'next_actions': self._next_actions(blockers, warnings),
            'safe_policy': 'static_source_scan_no_db_no_mutation',
            'read_only_guarantees': [
                'Không query database',
                'Không chạy EXPLAIN/ANALYZE',
                'Không import route/service runtime',
                'Không enqueue job hoặc mutate dữ liệu',
            ],
        }

    def scan(self, *, max_items: int = 100) -> list[QueryHotspotItem]:
        found: list[QueryHotspotItem] = []
        for base in self.SOURCE_DIRS:
            path = self.root / base
            if not path.exists():
                continue
            for file in sorted(path.rglob('*.py')):
                if any(part in self.IGNORE_PARTS for part in file.parts):
                    continue
                try:
                    lines = file.read_text(encoding='utf-8').splitlines()
                except UnicodeDecodeError:
                    continue
                for index, line in enumerate(lines, start=1):
                    stripped = line.strip()
                    if '.all()' not in stripped:
                        continue
                    context = '\n'.join(lines[max(0, index - 40):index])
                    severity, reason = self._classify(stripped, file, context=context)
                    if severity == 'IGNORE':
                        continue
                    found.append(QueryHotspotItem(
                        file=str(file.relative_to(self.root)),
                        line=index,
                        code=stripped[:220],
                        severity=severity,
                        reason=reason,
                    ))
                    if len(found) >= max_items:
                        return found
        return found

    def _classify(self, line: str, file: Path, *, context: str = '') -> tuple[str, str]:
        if 'query_hotspot.py' in str(file):
            return 'IGNORE', 'self scan'
        if any(hint in line for hint in self.SAFE_HINTS):
            return 'INFO', 'bounded_or_aggregate_pattern'
        bounded_context_patterns = (
            ('AcademicClassStudent', '.class_id =='),
            ('GenerationBatch', '.job_id =='),
            ('PublishBatchItem', '.batch_id =='),
            ('BankReleaseQuestion', '.bank_release_id =='),
            ('QuestionBankVersion', '.chapter_id.in_(chapter_ids)'),
            ('AnalyticsTrackingEvent', 'username.in_(target_usernames)'),
        )
        if any(model in context and scope in context for model, scope in bounded_context_patterns):
            return 'INFO', 'bounded_by_parent_or_roster_scope'
        if 'AcademicClassCourseMapping' in context and '.in_(class_ids)' in context:
            return 'WARNING', 'background_report_bounded_by_selected_class_ids'
        if 'AcademicClass.id' in context and 'or_(*filters)' in context:
            return 'WARNING', 'rbac_access_scope_ids_materialized'
        if 'ContentChunk' in context and '.course_id ==' in context:
            return 'WARNING', 'course_scoped_content_query_review_size'
        if 'Question' in context and '.course_id ==' in context:
            return 'WARNING', 'course_scoped_question_query_review_size'
        if any(token in line for token in self.HIGH_RISK_TOKENS):
            return 'BLOCKER', 'potential_unbounded_large_table_all'
        if 'db.query(' in line or '.query(' in line:
            return 'WARNING', 'review_all_query_for_scope_and_limit'
        return 'INFO', 'manual_review'

    def _scanned_file_count(self) -> int:
        count = 0
        for base in self.SOURCE_DIRS:
            path = self.root / base
            if not path.exists():
                continue
            count += sum(1 for file in path.rglob('*.py') if not any(part in self.IGNORE_PARTS for part in file.parts))
        return count

    @staticmethod
    def _next_actions(blockers: list[QueryHotspotItem], warnings: list[QueryHotspotItem]) -> list[str]:
        if blockers:
            return [
                'Fix BLOCKER .all() sites first: add pagination/limit, SQL aggregate, or narrow scope filter.',
                'Run scripts/query-hotspot-report.sh after each change and keep blocker_count trending down.',
                'For remaining large-table queries, run EXPLAIN on UAT with real data before pilot expansion.',
            ]
        if warnings:
            return [
                'Review WARNING .all() sites and document why each is bounded or safe.',
                'Add static whitelist/test only after code review confirms small table or strict scope.',
            ]
        return ['No obvious unbounded .all() hotspot found by static scan; continue UAT EXPLAIN/load test.']
