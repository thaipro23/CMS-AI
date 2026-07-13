from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.core.config import settings
from app.services.learning_analytics.analytics_core_service import LearningAnalyticsCoreService
from app.services.performance_readiness import PerformanceReadinessService
from app.services.security_readiness import SecurityReadinessService


class ReleaseCandidateService:
    """Read-only release candidate gate for UAT/pilot sign-off.

    This service composes existing readiness evidence into one go/no-go report.
    It never scans raw tracking.log, calls external systems, enqueues jobs,
    recalculates analytics, or mutates data. The report is intentionally strict:
    any blocker in security, performance, production readiness, evidence pack, or
    pilot acceptance blocks broad rollout; pilot is allowed only when blockers are
    cleared and the evidence pack is at least PASS_WITH_WARNINGS.
    """

    safe_policy = 'read_only_release_candidate_gate_no_mutation'
    read_only_guarantees = [
        'Không đọc raw tracking.log trong request',
        'Không gọi Open edX/AP/OpenAI trong request',
        'Không enqueue job hoặc recalculate',
        'Không publish/rollback Bank Release',
        'Không mutate database',
        'Không kết luận vi phạm cá nhân',
    ]

    def __init__(self, db: Session):
        self.db = db
        self.analytics = LearningAnalyticsCoreService(db)

    def report(
        self,
        *,
        class_id: str | None = None,
        course_id: str | None = None,
        campus: str | None = None,
        branch: str | None = None,
        sample_limit: int = 5,
        allowed_class_ids: set[str] | None = None,
    ) -> dict[str, Any]:
        generated_at = datetime.now(timezone.utc).isoformat()
        production = self.analytics.production_readiness_report(allowed_class_ids=allowed_class_ids)
        evidence = self.analytics.analytics_uat_evidence_pack(
            class_id=class_id,
            course_id=course_id,
            campus=campus,
            branch=branch,
            sample_limit=sample_limit,
            allowed_class_ids=allowed_class_ids,
        )
        performance = PerformanceReadinessService(self.db).performance_readiness_report()
        security = SecurityReadinessService().report()

        gates = [
            self._gate(
                key='production_readiness',
                title='Production readiness',
                status=self._status_from_blockers(production.get('blocker_count'), production.get('warning_count')),
                blocker_count=production.get('blocker_count'),
                warning_count=production.get('warning_count'),
                message=production.get('summary_label') or production.get('message'),
                report_endpoint='/api/health/readiness',
            ),
            self._gate(
                key='security_readiness',
                title='Security production gate',
                status=security.get('status'),
                blocker_count=security.get('blocker_count'),
                warning_count=security.get('warning_count'),
                message=security.get('summary_label'),
                report_endpoint='/api/health/security-readiness',
            ),
            self._gate(
                key='performance_readiness',
                title='Performance/load gate',
                status=performance.get('status'),
                blocker_count=performance.get('blocker_count'),
                warning_count=performance.get('warning_count'),
                message=performance.get('summary_label'),
                report_endpoint='/api/health/performance-readiness',
            ),
            self._gate(
                key='uat_evidence_pack',
                title='UAT evidence pack',
                status=self._normalize_evidence_status(evidence.get('evidence_status')),
                blocker_count=(evidence.get('summary') or {}).get('blocker_count'),
                warning_count=(evidence.get('summary') or {}).get('warning_count'),
                message=self._evidence_message(evidence),
                report_endpoint='/api/analytics/ops/evidence-pack',
            ),
            self._gate(
                key='pilot_acceptance',
                title='Pilot acceptance',
                status=self._normalize_pilot_status(((evidence.get('reports') or {}).get('pilot_acceptance') or {}).get('pilot_status')),
                blocker_count=len((((evidence.get('reports') or {}).get('pilot_acceptance') or {}).get('blocker_codes') or [])),
                warning_count=len((((evidence.get('reports') or {}).get('pilot_acceptance') or {}).get('warning_codes') or [])),
                message=((evidence.get('reports') or {}).get('pilot_acceptance') or {}).get('message'),
                report_endpoint='/api/analytics/ops/pilot-acceptance',
            ),
        ]
        blockers = self._collect_issues(
            production=production,
            security=security,
            performance=performance,
            evidence=evidence,
            severity='BLOCKER',
        )
        warnings = self._collect_issues(
            production=production,
            security=security,
            performance=performance,
            evidence=evidence,
            severity='WARNING',
        )
        gate_blockers = [gate for gate in gates if gate['status'] == 'BLOCKED']
        gate_warnings = [gate for gate in gates if gate['status'] == 'WARNING']
        blocker_count = len(blockers) + len(gate_blockers)
        warning_count = len(warnings) + len(gate_warnings)

        if blocker_count:
            rc_status = 'FAIL'
            go_no_go = 'HOLD'
            summary = 'Chưa đủ điều kiện pilot; cần xử lý blocker trước khi mở rộng UAT.'
        elif warning_count:
            rc_status = 'PASS_WITH_WARNINGS'
            go_no_go = 'GO_PILOT_WITH_MONITORING'
            summary = 'Có thể pilot có kiểm soát; cần theo dõi và xử lý cảnh báo trước production rộng.'
        else:
            rc_status = 'PASS'
            go_no_go = 'GO_PILOT'
            summary = 'Đủ điều kiện pilot theo các gate kỹ thuật hiện có.'

        ready_for_pilot = blocker_count == 0 and bool((evidence.get('summary') or {}).get('ready_for_pilot', True))
        ready_for_broad_production = (
            rc_status == 'PASS'
            and bool((evidence.get('summary') or {}).get('ready_for_broad_production'))
            and security.get('status') == 'READY'
            and performance.get('status') == 'READY'
            and bool(production.get('ready_for_production'))
        )
        if ready_for_broad_production:
            go_no_go = 'GO_BROAD_PRODUCTION'
            summary = 'Đủ điều kiện mở rộng production theo các gate kỹ thuật hiện có.'

        return {
            'version': settings.app_version,
            'report_type': 'pilot_release_candidate_gate',
            'release_candidate': 'v25.9.16.7.2.64.12',
            'generated_at': generated_at,
            'status': rc_status,
            'go_no_go': go_no_go,
            'summary_label': summary,
            'ready_for_pilot': ready_for_pilot,
            'ready_for_broad_production': ready_for_broad_production,
            'blocker_count': blocker_count,
            'warning_count': warning_count,
            'filters': {
                'class_id': class_id,
                'course_id': course_id,
                'campus': campus,
                'branch': branch,
                'sample_limit': sample_limit,
            },
            'gates': gates,
            'blockers': blockers[:20],
            'warnings': warnings[:20],
            'next_actions': self._next_actions(gates, production, security, performance, evidence),
            'reports': {
                'production_readiness': self._compact_report(production),
                'security_readiness': self._compact_report(security),
                'performance_readiness': self._compact_report(performance),
                'uat_evidence_pack': self._compact_evidence(evidence),
            },
            'safe_policy': self.safe_policy,
            'read_only_guarantees': self.read_only_guarantees,
            'disclaimer': 'Release Candidate gate là checklist vận hành UAT/pilot; vẫn cần backup, rollback plan, reviewer sign-off và theo dõi runtime khi chạy thật.',
        }

    @staticmethod
    def _status_from_blockers(blockers: Any, warnings: Any) -> str:
        if int(blockers or 0) > 0:
            return 'BLOCKED'
        if int(warnings or 0) > 0:
            return 'WARNING'
        return 'OK'

    @staticmethod
    def _normalize_evidence_status(status: Any) -> str:
        value = str(status or '').upper()
        if value == 'FAIL':
            return 'BLOCKED'
        if value == 'PASS_WITH_WARNINGS':
            return 'WARNING'
        return 'OK' if value == 'PASS' else 'WARNING'

    @staticmethod
    def _normalize_pilot_status(status: Any) -> str:
        value = str(status or '').upper()
        if value == 'FAIL':
            return 'BLOCKED'
        if value == 'PASS_WITH_WARNINGS':
            return 'WARNING'
        return 'OK' if value == 'PASS' else 'WARNING'

    @staticmethod
    def _gate(*, key: str, title: str, status: Any, blocker_count: Any, warning_count: Any, message: Any, report_endpoint: str) -> dict[str, Any]:
        normalized = str(status or '').upper()
        if normalized in {'READY', 'PASS', 'OK'}:
            final_status = 'OK'
        elif normalized in {'BLOCKED', 'FAIL', 'ERROR'}:
            final_status = 'BLOCKED'
        elif int(blocker_count or 0) > 0:
            final_status = 'BLOCKED'
        else:
            final_status = 'WARNING'
        return {
            'key': key,
            'title': title,
            'status': final_status,
            'blocker_count': int(blocker_count or 0),
            'warning_count': int(warning_count or 0),
            'message': str(message or ''),
            'report_endpoint': report_endpoint,
        }

    @staticmethod
    def _evidence_message(evidence: dict[str, Any]) -> str:
        status = str(evidence.get('evidence_status') or '').upper()
        if status == 'PASS':
            return 'Evidence pack đạt.'
        if status == 'PASS_WITH_WARNINGS':
            return 'Evidence pack có cảnh báo cần theo dõi.'
        if status == 'FAIL':
            return 'Evidence pack còn blocker.'
        return 'Evidence pack chưa xác định đầy đủ.'

    @staticmethod
    def _compact_report(report: dict[str, Any]) -> dict[str, Any]:
        return {
            'status': report.get('status') or report.get('readiness') or report.get('sla_status') or report.get('evidence_status'),
            'summary_label': report.get('summary_label') or report.get('message'),
            'blocker_count': report.get('blocker_count') or (report.get('summary') or {}).get('blocker_count') or 0,
            'warning_count': report.get('warning_count') or (report.get('summary') or {}).get('warning_count') or 0,
            'next_actions': (report.get('next_actions') or [])[:5],
        }

    @staticmethod
    def _compact_evidence(evidence: dict[str, Any]) -> dict[str, Any]:
        summary = evidence.get('summary') or {}
        return {
            'status': evidence.get('evidence_status'),
            'ready_for_pilot': summary.get('ready_for_pilot'),
            'ready_for_broad_production': summary.get('ready_for_broad_production'),
            'sla_status': summary.get('sla_status'),
            'pilot_status': summary.get('pilot_status'),
            'blocker_count': summary.get('blocker_count') or 0,
            'warning_count': summary.get('warning_count') or 0,
            'next_actions': (evidence.get('next_actions') or [])[:5],
        }

    @staticmethod
    def _issue_from(item: dict[str, Any], source: str, fallback_severity: str) -> dict[str, Any]:
        return {
            'source': source,
            'severity': str(item.get('severity') or fallback_severity).upper(),
            'code': item.get('code') or item.get('key') or source,
            'message': item.get('message') or item.get('summary_label') or item.get('label') or '',
            'action': item.get('action') or item.get('recommended_action') or '',
        }

    def _collect_issues(self, *, production: dict[str, Any], security: dict[str, Any], performance: dict[str, Any], evidence: dict[str, Any], severity: str) -> list[dict[str, Any]]:
        wanted = severity.upper()
        issues: list[dict[str, Any]] = []
        for source, report in (
            ('production_readiness', production),
            ('security_readiness', security),
            ('performance_readiness', performance),
        ):
            for item in report.get('checks') or report.get('issues') or []:
                item_severity = str(item.get('severity') or '').upper()
                if item_severity == wanted and not bool(item.get('ok', False)):
                    issues.append(self._issue_from(item, source, wanted))
        for source_key in ('blockers', 'warnings'):
            if (source_key == 'blockers' and wanted != 'BLOCKER') or (source_key == 'warnings' and wanted != 'WARNING'):
                continue
            for item in evidence.get(source_key) or []:
                issues.append(self._issue_from(item, f"uat_evidence_pack.{item.get('source') or source_key}", wanted))
        deduped: list[dict[str, Any]] = []
        seen: set[tuple[str, str]] = set()
        for item in issues:
            key = (str(item.get('source')), str(item.get('code')))
            if key not in seen:
                seen.add(key)
                deduped.append(item)
        return deduped

    @staticmethod
    def _next_actions(gates: list[dict[str, Any]], production: dict[str, Any], security: dict[str, Any], performance: dict[str, Any], evidence: dict[str, Any]) -> list[str]:
        actions: list[str] = []
        for gate in gates:
            if gate.get('status') == 'BLOCKED':
                endpoint = gate.get('report_endpoint')
                actions.append(f"Mở {endpoint} để xử lý blocker của {gate.get('title')}.")
        for report in (production, security, performance, evidence):
            for action in report.get('next_actions') or []:
                text = str(action or '').strip()
                if text and text not in actions:
                    actions.append(text)
        if not actions:
            actions.extend([
                'Chạy scripts/uat-build-gate.sh với STRICT=1 trên UAT có frontend node_modules và psycopg.',
                'Chạy scripts/pilot-release-candidate-report.sh và lưu artifact vào ticket UAT.',
                'Chuẩn bị rollback bằng cách giữ nguyên zip/version trước đó và backup .env.production.',
            ])
        return actions[:10]
