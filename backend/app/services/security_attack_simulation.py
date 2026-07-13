from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
import os
from typing import Any

from app.core.config import settings


@dataclass
class AttackCase:
    id: int
    category: str
    attack: str
    control: str
    status: str
    severity: str
    evidence: str
    fix: str


class SecurityAttackSimulationService:
    """Read-only static simulation of common attacks against this project.

    This is not an active exploit runner. It safely inspects source-level controls
    for 20 common web/API attack classes and reports what is protected, what
    still needs UAT verification, and which code paths implement the fix.
    """

    report_type = 'security_attack_simulation_v1'
    safe_policy = 'read_only_static_attack_simulation_no_exploit_execution'
    read_only_guarantees = [
        'Không gửi exploit request vào live server',
        'Không brute-force token/password',
        'Không scan mạng nội bộ',
        'Không gọi Open edX/AP/OpenAI',
        'Không enqueue job hoặc mutate database',
    ]

    def __init__(self, root: Path | None = None) -> None:
        self.root = root or Path(os.getenv('SOURCE_CONTRACT_ROOT') or Path(__file__).resolve().parents[3])
        self.cache: dict[str, str] = {}

    def report(self) -> dict[str, Any]:
        cases = self._cases()
        blockers = [item for item in cases if item.severity == 'BLOCKER' and item.status != 'PROTECTED']
        warnings = [item for item in cases if item.severity == 'WARNING' and item.status != 'PROTECTED']
        status = 'BLOCKED' if blockers else ('READY_WITH_WARNINGS' if warnings else 'READY')
        return {
            'version': settings.app_version,
            'report_type': self.report_type,
            'generated_at': datetime.now(timezone.utc).isoformat(),
            'status': status,
            'summary_label': self._summary_label(status),
            'blocker_count': len(blockers),
            'warning_count': len(warnings),
            'attack_count': len(cases),
            'protected_count': len([item for item in cases if item.status == 'PROTECTED']),
            'needs_review_count': len([item for item in cases if item.status == 'NEEDS_UAT_REVIEW']),
            'attacks': [asdict(item) for item in cases],
            'sections': self._sections(cases),
            'next_actions': self._next_actions(blockers, warnings),
            'safe_policy': self.safe_policy,
            'read_only_guarantees': self.read_only_guarantees,
            'disclaimer': 'Đây là mô phỏng tĩnh an toàn cho 20 nhóm tấn công phổ biến. UAT vẫn cần chạy dynamic smoke test qua reverse proxy thật, TLS thật và token thật.',
        }

    def _read(self, rel: str) -> str:
        if rel not in self.cache:
            path = self.root / rel
            try:
                self.cache[rel] = path.read_text(encoding='utf-8')
            except Exception:
                self.cache[rel] = ''
        return self.cache[rel]

    def _has(self, rel: str, *needles: str) -> bool:
        text = self._read(rel)
        return all(needle in text for needle in needles)

    def _case(self, id: int, category: str, attack: str, control: str, ok: bool, evidence: str, fix: str, *, severity: str = 'BLOCKER', review: bool = False) -> AttackCase:
        status = 'PROTECTED' if ok else ('NEEDS_UAT_REVIEW' if review else 'MISSING_CONTROL')
        return AttackCase(id=id, category=category, attack=attack, control=control, status=status, severity=severity, evidence=evidence, fix=fix)

    def _cases(self) -> list[AttackCase]:
        main = 'backend/app/main.py'
        security = 'backend/app/core/security.py'
        origin = 'backend/app/core/origin_guard.py'
        config = 'backend/app/core/config.py'
        connector = 'backend/app/modules/openedx_connector/real.py'
        connector_auth = 'openedx-connector-plugin/openedx_ai_connector/auth.py'
        unit_reset = 'openedx-unit-reset-plugin/openedx_unit_reset/views.py'
        qb_route = 'backend/app/api/routes/question_bank_v2.py'
        qb_helpers = 'backend/app/services/question_bank/helpers.py'
        assignment = 'backend/app/services/academic/assignment_external.py'
        errors = 'backend/app/core/errors.py'

        return [
            self._case(1, 'auth', 'Demo header role spoofing', 'Production rejects X-User-* demo role authentication.', self._has(security, 'Demo header authentication is disabled in production', 'allow_demo_role_header'), security, 'Keep AUTH_MODE=openedx_sso|jwt and ALLOW_DEMO_ROLE_HEADER=false in production.'),
            self._case(2, 'auth', 'JWT admin privilege spoofing', 'Admin JWT requires superuser/super_admin proof.', self._has(security, 'AI admin token requires Open edX superuser/super_admin proof'), security, 'Do not mint admin role without is_superuser/is_super_admin/ai_system_admin trusted claim.'),
            self._case(3, 'auth', 'Wrong/expired token replay', 'JWT decode enforces issuer, audience, exp, sub, and token_type.', self._has(security, 'issuer=settings.jwt_issuer', 'audience=settings.jwt_audience', "token_type') != 'ai_session"), security, 'Keep issuer/audience/token_type checks mandatory.'),
            self._case(4, 'csrf', 'Cookie-authenticated CSRF without Origin', 'Mutating cookie-authenticated API requests require Origin/Referer.', self._has(origin, 'ORIGIN_REQUIRED', 'cookie-authenticated mutating API requests'), origin, 'Run UAT browser smoke test for POST/PATCH/PUT/DELETE without Origin.'),
            self._case(5, 'csrf', 'Malicious cross-site Origin', 'Mutating API requests from disallowed Origin are rejected.', self._has(origin, 'ORIGIN_FORBIDDEN', '_is_allowed_origin'), origin, 'Keep explicit CORS whitelist and reverse proxy preserving Origin.'),
            self._case(6, 'cors', 'Wildcard CORS with credentials', 'CORS uses explicit allowlist from settings.', self._has(main, 'allow_credentials=True', 'cors_origin_list()'), main, 'Do not set CORS_ALLOWED_ORIGINS=* in production; security-readiness blocks it.'),
            self._case(7, 'browser', 'Clickjacking / frame injection', 'Backend responses add X-Frame-Options and CSP frame-ancestors.', self._has('backend/app/core/security_headers.py', 'X-Frame-Options', "frame-ancestors 'none'"), 'backend/app/core/security_headers.py', 'Keep reverse proxy from stripping security headers.'),
            self._case(8, 'browser', 'MIME sniffing / content-type confusion', 'Backend responses add X-Content-Type-Options=nosniff.', self._has('backend/app/core/security_headers.py', 'X-Content-Type-Options', 'nosniff'), 'backend/app/core/security_headers.py', 'Verify exported CSV/XML still has explicit media_type.'),
            self._case(9, 'browser', 'Sensitive Referer leakage', 'Backend responses set Referrer-Policy=no-referrer.', self._has('backend/app/core/security_headers.py', 'Referrer-Policy', 'no-referrer'), 'backend/app/core/security_headers.py', 'Frontend/reverse proxy should keep no-referrer for AI app routes.'),
            self._case(10, 'transport', 'TLS downgrade / cookie theft over HTTP', 'Production adds HSTS when Secure cookie is enabled.', self._has('backend/app/core/security_headers.py', 'Strict-Transport-Security', 'auth_cookie_secure'), 'backend/app/core/security_headers.py', 'Verify TLS termination and HSTS on public domains.'),
            self._case(11, 'observability', 'Unauthenticated metrics scraping', 'Metrics endpoint requires strong token or is disabled in production.', self._has('backend/app/main.py', 'metrics_token', 'Invalid metrics token'), main, 'Set METRICS_TOKEN >=32 chars or METRICS_ENABLED=false.'),
            self._case(12, 'connector', 'SSRF through asset/transcript download URL', 'Connector blocks non-whitelisted hosts and private IP resolution.', self._has(connector, '_assert_safe_download_url', '_host_resolves_to_private_address'), connector, 'Keep OPENEDX_ALLOWED_DOWNLOAD_HOSTS tight; run UAT with private-IP URL blocked.'),
            self._case(13, 'connector', 'Connector HMAC replay', 'AI Server sends nonce and connector plugin stores nonce/signature within skew window.', self._has(connector, 'X-AI-Connector-Nonce') and self._has(connector_auth, '_check_and_store_hmac_nonce'), f'{connector}; {connector_auth}', 'Ensure CMS cache backend is available; nonce store fails closed.'),
            self._case(14, 'connector', 'Unit-reset HMAC replay', 'Unit reset HMAC now supports nonce and cache-backed replay protection.', self._has(unit_reset, 'HTTP_X_AI_CONNECTOR_NONCE', 'ai_unit_reset_hmac_nonce'), unit_reset, 'Deploy unit-reset plugin together with AI Server so nonce signatures match.'),
            self._case(15, 'upload', 'Path traversal in uploaded filenames', 'Pending material filenames use safe_upload_filename.', self._has(qb_route, 'safe_upload_filename') and self._has(qb_helpers, 'def safe_upload_filename'), f'{qb_route}; {qb_helpers}', 'Reject or sanitize hidden/control-character filenames in future material upload cleanup.'),
            self._case(16, 'upload', 'Oversized upload / decompression bomb', 'Upload/extraction limits are configured and upload read is capped.', self._has(qb_route, '_read_bank_upload_limited') and self._has(config, 'max_zip_uncompressed_bytes', 'max_upload_bytes'), f'{qb_route}; {config}', 'Run UAT with file > MAX_UPLOAD_BYTES and huge XLSX/PDF limits.'),
            self._case(17, 'upload', 'Unsupported executable upload', 'Bank material extension allowlist rejects unsupported formats.', self._has(qb_route, '_raise_unsupported_bank_material', 'supported ='), qb_route, 'Keep MIME/extension allowlist strict; do not allow archives/executables.'),
            self._case(18, 'assignment', 'Unauthorized Assignment score mutation', 'Assignment score write path is externalized and returns 410.', self._has(assignment, 'ASSIGNMENT_SCORE_EXTERNALIZED') or self._has('backend/app/api/routes/academic.py', 'ASSIGNMENT_SCORE_EXTERNALIZED'), assignment, 'Keep assignment scoring in external source of truth.'),
            self._case(19, 'errors', 'Debug traceback / secret leakage in API errors', 'Custom error handlers return structured payloads and production debug should be false.', self._has(errors, 'error_payload') and self._has(config, 'DEBUG_DISABLED') or self._has(config, 'debug: bool'), f'{errors}; {config}', 'Set DEBUG=false and review logs for secret redaction.', severity='WARNING', review=True),
            self._case(20, 'rbac', 'Student Ops / Quiz Bank privilege confusion', 'Business RBAC split keeps Student Ops and Quiz Bank separated.', self._has('backend/app/services/business_rbac.py', 'CAMPUS_OWNER', 'QUESTION_REVIEWER') and self._has('backend/app/services/academic/ap_sync.py', 'AcademicAPSyncWorkflowService'), 'backend/app/services/business_rbac.py', 'Run role matrix UAT with super_admin, campus owner, teacher, subject owner, reviewer.', severity='WARNING', review=True),
        ]

    @staticmethod
    def _sections(cases: list[AttackCase]) -> list[dict[str, Any]]:
        sections: list[dict[str, Any]] = []
        for category in sorted({case.category for case in cases}):
            items = [case for case in cases if case.category == category]
            issues = [case for case in items if case.status != 'PROTECTED']
            sections.append({
                'key': category,
                'title': category.replace('_', ' ').title(),
                'status': 'READY' if not issues else 'READY_WITH_WARNINGS',
                'check_count': len(items),
                'blocker_count': len([case for case in issues if case.severity == 'BLOCKER']),
                'warning_count': len([case for case in issues if case.severity == 'WARNING']),
            })
        return sections

    @staticmethod
    def _summary_label(status: str) -> str:
        if status == 'READY':
            return '20 nhóm tấn công phổ biến đã có control trong artifact.'
        if status == 'READY_WITH_WARNINGS':
            return 'Có control chính, còn vài điểm cần UAT dynamic/reverse-proxy verification.'
        return 'Còn blocker security cần xử lý trước pilot/production.'

    @staticmethod
    def _next_actions(blockers: list[AttackCase], warnings: list[AttackCase]) -> list[str]:
        if blockers:
            return [f"Fix {item.attack}: {item.fix}" for item in blockers[:5]]
        actions = [
            'Deploy UAT và chạy security-attack-simulation-report.sh sau reverse proxy/TLS thật.',
            'Chạy smoke test dynamic: CSRF no Origin, malicious Origin, SSRF private IP, upload oversized file, role matrix.',
            'Verify response headers không bị Nginx/Caddy strip.',
        ]
        actions.extend([f"UAT review {item.attack}: {item.fix}" for item in warnings[:3]])
        return actions[:6]
