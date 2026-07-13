from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.core.config import settings
from app.services.maintainability_contract import MaintainabilityContractService
from app.services.performance_readiness import PerformanceReadinessService
from app.services.pilot_operations import PilotOperationsService
from app.services.query_hotspot import QueryHotspotService
from app.services.security_readiness import SecurityReadinessService


class ProductionPilotFinalService:
    """Read-only final QA/sign-off gate for controlled pilot rollout.

    The previous gates answer progressively narrower questions:
    - readiness/security/performance/query/maintainability: are subsystems safe?
    - release candidate: is this release eligible for pilot?
    - pilot operations: what should operators do during go-live?

    This service is the final QA layer. It composes the existing gates into a
    sign-off checklist and makes missing evidence visible. It intentionally does
    not run load tests, publish to Open edX, trigger rollback, enqueue jobs,
    recalculate analytics, scan raw tracking.log, or mutate data. Runtime load
    and rollback drills are performed by companion scripts and their artifacts
    are referenced in the checklist.
    """

    safe_policy = 'read_only_production_pilot_final_gate_no_mutation'
    read_only_guarantees = [
        'Không đọc raw tracking.log trong request',
        'Không gọi Open edX/AP/OpenAI trong request',
        'Không enqueue job hoặc recalculate',
        'Không publish/rollback Bank Release',
        'Không chạy load test trong API request',
        'Không mutate database',
        'Không kết luận vi phạm cá nhân',
    ]

    def __init__(self, db: Session):
        self.db = db

    def report(
        self,
        *,
        class_id: str | None = None,
        course_id: str | None = None,
        campus: str | None = None,
        branch: str | None = None,
        sample_limit: int = 5,
        allowed_class_ids: set[str] | None = None,
        include_static_scans: bool = True,
    ) -> dict[str, Any]:
        generated_at = datetime.now(timezone.utc).isoformat()
        pilot = PilotOperationsService(self.db).report(
            class_id=class_id,
            course_id=course_id,
            campus=campus,
            branch=branch,
            sample_limit=sample_limit,
            allowed_class_ids=allowed_class_ids,
        )
        security = SecurityReadinessService().report()
        performance = PerformanceReadinessService(self.db).performance_readiness_report()
        maintainability = MaintainabilityContractService().report() if include_static_scans else {}
        hotspots = QueryHotspotService().report(max_items=80) if include_static_scans else {}

        gates = [
            self._gate('pilot_operations', 'Pilot operations', pilot.get('status'), pilot.get('blocker_count'), pilot.get('warning_count'), '/api/health/pilot-operations'),
            self._gate('security_readiness', 'Security readiness', security.get('status'), security.get('blocker_count'), security.get('warning_count'), '/api/health/security-readiness'),
            self._gate('performance_readiness', 'Performance readiness', performance.get('status'), performance.get('blocker_count'), performance.get('warning_count'), '/api/health/performance-readiness'),
        ]
        if include_static_scans:
            gates.extend([
                self._gate('maintainability_contract', 'Maintainability contract', maintainability.get('status'), maintainability.get('blocker_count'), maintainability.get('warning_count'), '/api/health/maintainability-contract'),
                self._gate('query_hotspots', 'Query hotspot scan', hotspots.get('status'), hotspots.get('blocker_count'), hotspots.get('warning_count'), '/api/health/query-hotspots'),
            ])

        evidence_required = self._evidence_required()
        final_checks = self._final_checks(pilot=pilot, gates=gates, evidence_required=evidence_required)
        blockers = [item for item in final_checks if item.get('severity') == 'BLOCKER' and not item.get('ok')]
        warnings = [item for item in final_checks if item.get('severity') == 'WARNING' and not item.get('ok')]
        gate_blockers = [gate for gate in gates if gate.get('status') == 'BLOCKED']
        gate_warnings = [gate for gate in gates if gate.get('status') == 'WARNING']
        blocker_count = len(blockers) + len(gate_blockers)
        warning_count = len(warnings) + len(gate_warnings)

        if blocker_count:
            status = 'HOLD'
            decision = 'NO_GO'
            summary = 'Chưa đủ điều kiện chạy pilot final; còn blocker trong gate hoặc checklist.'
        elif warning_count:
            status = 'GO_WITH_MONITORING'
            decision = 'GO_CONTROLLED_PILOT'
            summary = 'Có thể chạy pilot có kiểm soát nếu đã lưu đủ evidence và có người trực rollback.'
        else:
            status = 'GO'
            decision = 'GO_PILOT'
            summary = 'Đủ điều kiện chạy pilot final theo các gate hiện có.'

        ready_for_pilot = status in {'GO', 'GO_WITH_MONITORING'} and bool(pilot.get('ready_for_pilot'))
        ready_for_broad_production = status == 'GO' and bool(pilot.get('ready_for_broad_production'))

        return {
            'version': settings.app_version,
            'report_type': 'production_pilot_final_gate',
            'generated_at': generated_at,
            'status': status,
            'decision': decision,
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
                'include_static_scans': include_static_scans,
            },
            'gates': gates,
            'final_checks': final_checks,
            'evidence_required': evidence_required,
            'load_test_plan': self._load_test_plan(),
            'rollback_drill': self._rollback_drill(),
            'signoff': self._signoff(status=status, decision=decision, ready_for_broad_production=ready_for_broad_production),
            'next_actions': self._next_actions(status=status, gates=gates, final_checks=final_checks),
            'reports': {
                'pilot_operations': self._compact(pilot),
                'security_readiness': self._compact(security),
                'performance_readiness': self._compact(performance),
                'maintainability_contract': self._compact(maintainability),
                'query_hotspots': self._compact(hotspots),
            },
            'safe_policy': self.safe_policy,
            'read_only_guarantees': self.read_only_guarantees,
            'disclaimer': 'Final pilot gate là checklist read-only. Load test, Open edX publish verify và rollback drill phải chạy bằng scripts để sinh artifact độc lập trước sign-off.',
        }

    @staticmethod
    def _gate(key: str, title: str, status: Any, blockers: Any, warnings: Any, endpoint: str) -> dict[str, Any]:
        raw = str(status or '').upper()
        blocker_count = int(blockers or 0)
        warning_count = int(warnings or 0)
        if raw in {'HOLD', 'NO_GO', 'FAIL', 'BLOCKED'} or blocker_count > 0:
            normalized = 'BLOCKED'
        elif raw in {'GO_WITH_MONITORING', 'PILOT_WITH_MONITORING', 'READY_WITH_WARNINGS', 'WARNING', 'PASS_WITH_WARNINGS'} or warning_count > 0:
            normalized = 'WARNING'
        else:
            normalized = 'OK'
        return {
            'key': key,
            'title': title,
            'status': normalized,
            'source_status': raw,
            'blocker_count': blocker_count,
            'warning_count': warning_count,
            'report_endpoint': endpoint,
        }

    @staticmethod
    def _evidence_required() -> list[str]:
        return [
            'BUILD_GATE_SUMMARY.md từ scripts/uat-build-gate.sh với STRICT=1, RUN_FRONTEND_BUILD=1, RUN_REVIEW_PACK=1',
            'PILOT_OPERATIONS_RUNBOOK.md từ scripts/pilot-operations-runbook.sh',
            'PRODUCTION_PILOT_FINAL_SUMMARY.md từ scripts/production-pilot-final-gate.sh',
            'LOAD_TEST_HOT_ENDPOINTS_SUMMARY.md từ scripts/load-test-hot-endpoints.sh',
            'ROLLBACK_DRILL_SUMMARY.md từ scripts/rollback-drill-verify.sh',
            'OPENEDX_PUBLISH_VERIFY_SUMMARY.md nếu pilot có publish/quiz/final test thật',
            'Deploy log gồm zip/root/version/image tag/thời điểm force recreate',
            '.env.production backup và artifact version trước để rollback',
        ]

    @staticmethod
    def _final_checks(*, pilot: dict[str, Any], gates: list[dict[str, Any]], evidence_required: list[str]) -> list[dict[str, Any]]:
        checks = [
            {
                'category': 'go_no_go',
                'code': 'PILOT_OPERATIONS_NOT_HOLD',
                'severity': 'BLOCKER',
                'ok': str(pilot.get('decision') or '').upper() != 'NO_GO',
                'message': 'Pilot operations decision không được là NO_GO.',
                'action': 'Xử lý blocker trong /api/health/pilot-operations trước khi pilot.',
            },
            {
                'category': 'go_no_go',
                'code': 'READY_FOR_PILOT',
                'severity': 'BLOCKER',
                'ok': bool(pilot.get('ready_for_pilot')),
                'message': 'Pilot operations phải ready_for_pilot=true.',
                'action': 'Giới hạn scope hoặc xử lý blocker/warning cho tới khi ready_for_pilot=true.',
            },
            {
                'category': 'gate',
                'code': 'NO_BLOCKED_GATE',
                'severity': 'BLOCKER',
                'ok': not any(gate.get('status') == 'BLOCKED' for gate in gates),
                'message': 'Không gate nào được BLOCKED.',
                'action': 'Mở endpoint gate tương ứng và xử lý blocker.',
            },
            {
                'category': 'evidence',
                'code': 'EVIDENCE_ARTIFACTS_REQUIRED',
                'severity': 'WARNING',
                'ok': False,
                'message': 'API không thể biết file evidence đã lưu chưa; cần chạy scripts final/load/rollback để tạo artifact.',
                'action': 'Chạy production-pilot-final-gate.sh, load-test-hot-endpoints.sh và rollback-drill-verify.sh trên UAT.',
                'target': evidence_required,
            },
            {
                'category': 'operations',
                'code': 'ROLLBACK_OPERATOR_REQUIRED',
                'severity': 'WARNING',
                'ok': False,
                'message': 'Cần người trực có quyền rollback trong cửa sổ pilot.',
                'action': 'Ghi rõ người trực, thời gian trực và lệnh rollback trong ticket pilot.',
            },
        ]
        return checks

    @staticmethod
    def _load_test_plan() -> list[dict[str, Any]]:
        return [
            {'endpoint': '/api/health/build', 'method': 'GET', 'target_p95_ms': 300, 'purpose': 'runtime identity smoke'},
            {'endpoint': '/api/jobs?page=1&page_size=20', 'method': 'GET', 'target_p95_ms': 500, 'purpose': 'job list pagination'},
            {'endpoint': '/api/audit?page=1&page_size=20', 'method': 'GET', 'target_p95_ms': 800, 'purpose': 'audit bounded scan'},
            {'endpoint': '/api/health/query-hotspots?max_items=80', 'method': 'GET', 'target_p95_ms': 1200, 'purpose': 'static hotspot gate'},
            {'endpoint': '/api/health/maintainability-contract', 'method': 'GET', 'target_p95_ms': 1200, 'purpose': 'maintainability contract gate'},
            {'endpoint': '/api/health/pilot-operations?sample_limit=5', 'method': 'GET', 'target_p95_ms': 1800, 'purpose': 'pilot operations composition'},
        ]

    @staticmethod
    def _rollback_drill() -> dict[str, Any]:
        return {
            'required_inputs': ['CURRENT_ZIP', 'PREVIOUS_ZIP', 'ENV_BACKUP', 'DEPLOY_ROOT'],
            'minimum_steps': [
                'verify current zip contains expected root',
                'verify previous zip exists and contains rollback root',
                'verify .env.production backup exists',
                'write rollback command preview without executing destructive action',
                'verify post-rollback health commands are documented',
            ],
            'script': 'scripts/rollback-drill-verify.sh',
        }

    @staticmethod
    def _signoff(*, status: str, decision: str, ready_for_broad_production: bool) -> dict[str, Any]:
        return {
            'current_status': status,
            'current_decision': decision,
            'can_signoff_pilot': status in {'GO', 'GO_WITH_MONITORING'},
            'can_signoff_broad_production': bool(ready_for_broad_production and status == 'GO'),
            'required_roles': ['SYSTEM_ADMIN', 'CAMPUS_OWNER đúng campus pilot', 'Người vận hành UAT có quyền rollback'],
            'requires_manual_evidence_check': True,
        }

    @staticmethod
    def _compact(report: dict[str, Any]) -> dict[str, Any]:
        return {
            'status': report.get('status'),
            'decision': report.get('decision'),
            'summary_label': report.get('summary_label') or report.get('message'),
            'blocker_count': report.get('blocker_count') or 0,
            'warning_count': report.get('warning_count') or 0,
            'next_actions': (report.get('next_actions') or [])[:5],
        }

    @staticmethod
    def _next_actions(*, status: str, gates: list[dict[str, Any]], final_checks: list[dict[str, Any]]) -> list[str]:
        actions: list[str] = []
        for gate in gates:
            if gate.get('status') == 'BLOCKED':
                actions.append(f"Xử lý blocker ở {gate.get('report_endpoint')} trước khi pilot.")
        for check in final_checks:
            if not check.get('ok') and check.get('action'):
                actions.append(str(check['action']))
        if status != 'HOLD':
            actions.extend([
                'Chạy load-test-hot-endpoints.sh và lưu LOAD_TEST_HOT_ENDPOINTS_SUMMARY.md.',
                'Chạy rollback-drill-verify.sh và lưu ROLLBACK_DRILL_SUMMARY.md.',
                'Chỉ mở rộng scope sau khi pilot không phát sinh blocker mới trong cửa sổ theo dõi.',
            ])
        deduped: list[str] = []
        for item in actions:
            if item and item not in deduped:
                deduped.append(item)
        return deduped[:10]
