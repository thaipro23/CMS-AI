from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from app.core.config import settings


@dataclass
class MaintainabilityFileMetric:
    path: str
    lines: int
    threshold: int
    severity: str
    reason: str


class MaintainabilityContractService:
    """Read-only source contract gate for maintainability and UI/API splits.

    This does not pretend to refactor every large file in one release. It makes
    the current technical debt visible, introduces stable split contract modules,
    and gives reviewers a repeatable gate so future changes cannot keep bloating
    the same monolith files unnoticed.
    """

    LARGE_FILE_LIMITS = {
        'backend/app/services/academic_service.py': 4500,
        'backend/app/services/question_bank_service.py': 4200,
        'backend/app/services/learning_analytics/analytics_core_service.py': 3200,
        'backend/app/api/routes/academic.py': 1800,
        'backend/app/api/routes/question_bank_v2.py': 1600,
        'frontend/lib/api.ts': 3500,
        'frontend/types/index.ts': 2600,
        'frontend/app/analytics/learning/page.tsx': 1200,
        'frontend/app/ops/readiness/page.tsx': 450,
        'frontend/app/globals.css': 8500,
        'frontend/styles/ops-readiness.css': 900,
    }

    CONTRACT_MODULES = [
        'backend/app/schemas/readiness.py',
        'backend/app/services/maintainability_contract.py',
        'backend/app/core/security_headers.py',
        'backend/app/services/security_attack_simulation.py',
        'frontend/types/readiness.ts',
        'frontend/lib/api/readiness.ts',
        'frontend/components/readiness/OperationalGatePanel.tsx',
        'frontend/app/ops/readiness/page.tsx',
        'backend/app/services/academic/helpers.py',
        'backend/app/services/academic/access.py',
        'backend/app/services/academic/roster.py',
        'backend/app/services/academic/sync_enrollment.py',
        'backend/app/services/academic/identity.py',
        'backend/app/services/academic/teacher_report.py',
        'backend/app/services/academic/ap_sync.py',
        'backend/app/services/academic/assignment_external.py',
        'backend/app/services/question_bank/helpers.py',
        'backend/app/services/question_bank/release_publish.py',
        'backend/app/services/question_bank/quiz_creation.py',
        'backend/app/services/question_bank/generation_review.py',
        'backend/app/services/learning_analytics/presentation.py',
        'backend/app/services/learning_analytics/operations.py',
        'backend/app/services/learning_analytics/results.py',
        'frontend/styles/ops-readiness.css',
        'frontend/components/navigation/Breadcrumbs.tsx',
        'frontend/components/table/EnterpriseDataTable.tsx',
        'frontend/components/table/TableStates.tsx',
        'frontend/hooks/useUrlTableState.ts',
        'frontend/styles/enterprise-ui.css',
    ]

    def __init__(self, root: Path | None = None):
        self.root = root or Path(__file__).resolve().parents[3]

    def report(self) -> dict[str, Any]:
        file_metrics = self._file_metrics()
        modules = self._contract_modules()
        warnings = [item for item in file_metrics if item.severity == 'WARNING']
        missing_modules = [item for item in modules if not item['exists']]
        blockers = [item for item in file_metrics if item.severity == 'BLOCKER']
        if missing_modules:
            blockers.extend([
                MaintainabilityFileMetric(
                    path=item['path'],
                    lines=0,
                    threshold=1,
                    severity='BLOCKER',
                    reason='missing_contract_module',
                ) for item in missing_modules
            ])
        status = 'BLOCKED' if blockers else ('READY_WITH_WARNINGS' if warnings else 'READY')
        return {
            'version': settings.app_version,
            'report_type': 'maintainability_contract',
            'status': status,
            'summary_label': self._summary_label(status),
            'blocker_count': len(blockers),
            'warning_count': len(warnings),
            'file_metrics': [asdict(item) for item in file_metrics],
            'contract_modules': modules,
            'checks': self._checks(file_metrics=file_metrics, modules=modules),
            'sections': [
                {
                    'key': 'backend_contract',
                    'title': 'Backend readiness schema contract',
                    'status': 'OK' if all(item['exists'] for item in modules if item['path'].startswith('backend/')) else 'BLOCKED',
                    'check_count': 2,
                    'blocker_count': sum(1 for item in modules if item['path'].startswith('backend/') and not item['exists']),
                    'warning_count': 0,
                },
                {
                    'key': 'frontend_contract',
                    'title': 'Frontend readiness split modules',
                    'status': 'OK' if all(item['exists'] for item in modules if item['path'].startswith('frontend/')) else 'BLOCKED',
                    'check_count': 3,
                    'blocker_count': sum(1 for item in modules if item['path'].startswith('frontend/') and not item['exists']),
                    'warning_count': 0,
                },
                {
                    'key': 'large_files',
                    'title': 'Large file debt visibility',
                    'status': 'WARNING' if warnings else 'OK',
                    'check_count': len(file_metrics),
                    'blocker_count': 0,
                    'warning_count': len(warnings),
                },
            ],
            'summary': {
                'large_file_thresholds': self.LARGE_FILE_LIMITS,
                'service_split_modules': [item for item in self.CONTRACT_MODULES if 'services/' in item or item.startswith('frontend/styles/')],
                'contract_module_count': len(modules),
                'existing_contract_module_count': sum(1 for item in modules if item['exists']),
                'largest_files': [asdict(item) for item in sorted(file_metrics, key=lambda item: item.lines, reverse=True)[:5]],
            },
            'next_actions': self._next_actions(warnings=warnings, missing_modules=missing_modules),
            'safe_policy': 'static_source_contract_scan_no_db_no_mutation',
            'read_only_guarantees': [
                'Không query database',
                'Không import heavy runtime route/service modules',
                'Không enqueue job hoặc mutate dữ liệu',
                'Không thay đổi schema database',
            ],
        }

    def _file_metrics(self) -> list[MaintainabilityFileMetric]:
        metrics: list[MaintainabilityFileMetric] = []
        for rel_path, threshold in self.LARGE_FILE_LIMITS.items():
            path = self.root / rel_path
            if not path.exists():
                metrics.append(MaintainabilityFileMetric(
                    path=rel_path,
                    lines=0,
                    threshold=threshold,
                    severity='BLOCKER',
                    reason='file_missing',
                ))
                continue
            lines = len(path.read_text(encoding='utf-8', errors='ignore').splitlines())
            severity = 'WARNING' if lines > threshold else 'INFO'
            reason = 'large_file_refactor_candidate' if severity == 'WARNING' else 'within_current_contract'
            metrics.append(MaintainabilityFileMetric(
                path=rel_path,
                lines=lines,
                threshold=threshold,
                severity=severity,
                reason=reason,
            ))
        return metrics

    def _contract_modules(self) -> list[dict[str, Any]]:
        return [
            {'path': rel_path, 'exists': (self.root / rel_path).exists()}
            for rel_path in self.CONTRACT_MODULES
        ]

    @staticmethod
    def _summary_label(status: str) -> str:
        if status == 'READY':
            return 'Maintainability contract đạt.'
        if status == 'READY_WITH_WARNINGS':
            return 'Maintainability contract đã có, còn large-file debt cần refactor tiếp.'
        return 'Maintainability contract còn thiếu module bắt buộc.'

    @staticmethod
    def _checks(*, file_metrics: list[MaintainabilityFileMetric], modules: list[dict[str, Any]]) -> list[dict[str, Any]]:
        checks: list[dict[str, Any]] = []
        for item in modules:
            checks.append({
                'category': 'contract_module',
                'code': f"CONTRACT_MODULE_{item['path'].replace('/', '_').replace('.', '_').upper()}",
                'severity': 'INFO' if item['exists'] else 'BLOCKER',
                'ok': item['exists'],
                'message': f"{item['path']} {'exists' if item['exists'] else 'missing'}.",
                'action': '' if item['exists'] else 'Add the missing split contract module before continuing refactor.',
            })
        for item in file_metrics:
            checks.append({
                'category': 'large_file',
                'code': f"LARGE_FILE_{item.path.replace('/', '_').replace('.', '_').upper()}",
                'severity': item.severity,
                'ok': item.severity != 'BLOCKER',
                'message': f'{item.path} has {item.lines} lines; target <= {item.threshold}.',
                'action': 'Split this file in the .63/.64 maintainability pass.' if item.severity == 'WARNING' else '',
            })
        return checks

    @staticmethod
    def _next_actions(*, warnings: list[MaintainabilityFileMetric], missing_modules: list[dict[str, Any]]) -> list[str]:
        if missing_modules:
            return [f"Create missing contract module: {item['path']}" for item in missing_modules]
        actions = [
            'Use backend/app/schemas/readiness.py as the stable Pydantic contract for readiness/gate endpoints.',
            'Move new readiness API calls into frontend/lib/api/readiness.ts instead of growing frontend/lib/api.ts.',
            'Move new readiness UI into frontend/components/readiness instead of growing analytics/learning/page.tsx.',
        ]
        if warnings:
            actions.append('Continue the service split by moving one tested workflow at a time: next candidates are academic sync/enrollment mutation, question-bank release/publish, and analytics SLA/evidence/result. Keep CSS split into page/component CSS files.')
        return actions[:8]
