from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from app.core.config import settings


@dataclass(frozen=True)
class UxAcceptanceCheck:
    category: str
    code: str
    severity: str
    ok: bool
    message: str
    action: str = ''
    path: str | None = None


class UxAcceptanceService:
    """Read-only source contract gate for enterprise Training/Ops UX.

    The gate intentionally scans source contracts only. It does not query the
    database, call AP/Open edX, enqueue Celery jobs, or claim that browser UAT
    has happened. Runtime keyboard/screen-reader/responsive checks remain part
    of the human UAT checklist.
    """

    TABLE_ROUTES = (
        'frontend/app/teacher-management/page.tsx',
        'frontend/app/student-management/page.tsx',
        'frontend/app/jobs/page.tsx',
        'frontend/app/audit/page.tsx',
    )

    REQUIRED_MODULES = (
        'frontend/components/table/EnterpriseDataTable.tsx',
        'frontend/components/table/TableStates.tsx',
        'frontend/hooks/useAcademicTableState.ts',
        'frontend/hooks/useOpsTableState.ts',
        'frontend/components/ui/StatusBadge.tsx',
        'backend/app/api/routes/audit.py',
        'frontend/app/ops/readiness/page.tsx',
    )

    def __init__(self, root: Path | None = None):
        self.root = root or Path(__file__).resolve().parents[3]

    def report(self) -> dict[str, Any]:
        checks = self._checks()
        blockers = [item for item in checks if item.severity == 'BLOCKER' and not item.ok]
        warnings = [item for item in checks if item.severity == 'WARNING' and not item.ok]
        status = 'BLOCKED' if blockers else ('READY_WITH_WARNINGS' if warnings else 'READY')
        return {
            'version': settings.app_version,
            'report_type': 'uat_ux_acceptance_v1',
            'status': status,
            'summary_label': self._summary_label(status),
            'message': 'Static UX contract gate; browser UAT evidence is still required before sign-off.',
            'blocker_count': len(blockers),
            'warning_count': len(warnings),
            'check_count': len(checks),
            'passed_count': sum(1 for item in checks if item.ok),
            'checks': [asdict(item) for item in checks],
            'sections': self._sections(checks),
            'next_actions': self._next_actions(blockers, warnings),
            'browser_uat_checklist': [
                'F5 và mở URL chia sẻ phải giữ nguyên từ khóa, trạng thái, trang, page size và mật độ bảng.',
                'Dùng bàn phím truy cập filter, menu cột, pagination, action và vùng cuộn ngang.',
                'Kiểm tra 360px, 768px, 1366px; chỉ container bảng được cuộn ngang.',
                'Kiểm tra loading, empty, API error/retry và permission denied trên bốn màn chính.',
                'Kiểm tra StatusBadge có icon + text; không dùng màu làm tín hiệu duy nhất.',
                'Audit CSV phải phản ánh đúng filter và không vượt RBAC của người dùng.',
            ],
            'safe_policy': 'static_source_scan_no_db_no_external_calls_no_mutation',
            'read_only_guarantees': [
                'Không query database',
                'Không gọi AP/Open edX hoặc model provider',
                'Không enqueue job',
                'Không mutate dữ liệu hoặc schema',
                'Không đọc tracking.log',
            ],
            'disclaimer': 'READY chỉ xác nhận source contract của bản build; không thay thế acceptance test trên UAT thật.',
        }

    def _read(self, relative_path: str) -> str:
        path = self.root / relative_path
        return path.read_text(encoding='utf-8', errors='ignore') if path.exists() else ''

    def _checks(self) -> list[UxAcceptanceCheck]:
        checks: list[UxAcceptanceCheck] = []
        for path in self.REQUIRED_MODULES:
            exists = (self.root / path).exists()
            checks.append(UxAcceptanceCheck('module', f'MODULE_{self._code(path)}', 'BLOCKER', exists, f'{path} {"exists" if exists else "missing"}.', 'Khôi phục module bắt buộc trước UAT.' if not exists else '', path))

        for path in self.TABLE_ROUTES:
            body = self._read(path)
            checks.extend([
                UxAcceptanceCheck('enterprise_table', f'ENTERPRISE_TABLE_{self._code(path)}', 'BLOCKER', 'EnterpriseDataTable' in body, f'{path} uses shared EnterpriseDataTable.', 'Migrate bảng chính sang EnterpriseDataTable.', path),
                UxAcceptanceCheck('url_state', f'URL_STATE_{self._code(path)}', 'BLOCKER', ('useAcademicTableState' in body or 'useOpsTableState' in body), f'{path} keeps filter/page/density in URL.', 'Dùng URL-state hook chung; không giữ filter quan trọng chỉ trong local state.', path),
                UxAcceptanceCheck('table_states', f'TABLE_STATES_{self._code(path)}', 'BLOCKER', all(token in body for token in ('loading=', 'emptyTitle=', 'onPageChange=')), f'{path} wires loading, empty and pagination states.', 'Bổ sung loading/empty/pagination contract.', path),
            ])

        enterprise = self._read('frontend/components/table/EnterpriseDataTable.tsx')
        status_badge = self._read('frontend/components/ui/StatusBadge.tsx')
        audit_route = self._read('backend/app/api/routes/audit.py')
        ops_page = self._read('frontend/app/ops/readiness/page.tsx')
        checks.extend([
            UxAcceptanceCheck('accessibility', 'TABLE_HORIZONTAL_SCROLL_ACCESSIBLE', 'BLOCKER', 'tabIndex={0}' in enterprise and 'có thể cuộn ngang' in enterprise, 'Horizontal table container is keyboard-focusable and labeled.', 'Giữ horizontal scroll trong container có nhãn truy cập.', 'frontend/components/table/EnterpriseDataTable.tsx'),
            UxAcceptanceCheck('accessibility', 'STATUS_ICON_TEXT_CONTRACT', 'BLOCKER', 'status-icon' in status_badge and 'aria-hidden="true"' in status_badge, 'Semantic status uses icon + text + color.', 'Không dùng màu là tín hiệu duy nhất.', 'frontend/components/ui/StatusBadge.tsx'),
            UxAcceptanceCheck('audit', 'AUDIT_SERVER_SEARCH_EXPORT', 'BLOCKER', "@router.get('/export.csv')" in audit_route and 'search: str | None' in audit_route and '_visible_audit_row' in audit_route, 'Audit search/export is server-filtered and RBAC-filtered.', 'Export phải dùng cùng filter và visibility contract với list.', 'backend/app/api/routes/audit.py'),
            UxAcceptanceCheck('ops', 'OPS_UX_GATE_VISIBLE', 'BLOCKER', 'UAT UX acceptance' in ops_page and 'getUxAcceptance' in ops_page, 'Ops readiness surfaces the UX acceptance gate.', 'Hiển thị gate trong /ops/readiness.', 'frontend/app/ops/readiness/page.tsx'),
            UxAcceptanceCheck('scope', 'ASSIGNMENT_WRITE_NOT_REINTRODUCED', 'WARNING', 'Workflow Assignment' not in self._read('frontend/app/student-management/page.tsx'), 'Training index does not reintroduce Assignment score write.', 'Không khôi phục Assignment write trong AI Server.', 'frontend/app/student-management/page.tsx'),
        ])
        return checks

    @staticmethod
    def _code(path: str) -> str:
        return path.replace('/', '_').replace('.', '_').replace('-', '_').upper()

    @staticmethod
    def _summary_label(status: str) -> str:
        if status == 'READY':
            return 'Training/Ops UX source contract đạt; sẵn sàng kiểm thử trình duyệt trên UAT.'
        if status == 'READY_WITH_WARNINGS':
            return 'UX source contract đạt phần bắt buộc, còn cảnh báo cần xác minh.'
        return 'UX source contract còn blocker; chưa nên sign-off UAT.'

    @staticmethod
    def _sections(checks: list[UxAcceptanceCheck]) -> list[dict[str, Any]]:
        sections: list[dict[str, Any]] = []
        for category, title in (
            ('enterprise_table', 'Enterprise tables'), ('url_state', 'URL-preserved state'),
            ('table_states', 'Loading/error/empty/pagination'), ('accessibility', 'Accessibility semantics'),
            ('audit', 'Audit filtering/export'), ('ops', 'Ops readiness integration'), ('scope', 'Workflow boundaries'),
        ):
            items = [item for item in checks if item.category == category]
            if not items:
                continue
            blocker_count = sum(1 for item in items if item.severity == 'BLOCKER' and not item.ok)
            warning_count = sum(1 for item in items if item.severity == 'WARNING' and not item.ok)
            sections.append({
                'key': category,
                'title': title,
                'status': 'BLOCKED' if blocker_count else ('WARNING' if warning_count else 'OK'),
                'check_count': len(items),
                'blocker_count': blocker_count,
                'warning_count': warning_count,
            })
        return sections

    @staticmethod
    def _next_actions(blockers: list[UxAcceptanceCheck], warnings: list[UxAcceptanceCheck]) -> list[str]:
        actions = [item.action for item in [*blockers, *warnings] if item.action]
        if not actions:
            actions = [
                'Chạy scripts/uat-ux-acceptance-report.sh sau khi deploy .64.14.',
                'Thực hiện browser UAT theo checklist và lưu ảnh/video hoặc ticket evidence.',
                'Chỉ sửa tiếp dựa trên lỗi UAT thật; không mở rộng Bank workflow trong bản này.',
            ]
        return actions[:8]
