from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import Any

from app.core.config import cors_origin_list, is_production, settings


@dataclass
class SecurityReadinessCheck:
    category: str
    code: str
    severity: str
    ok: bool
    message: str
    action: str
    actual: Any | None = None
    target: str | None = None


class SecurityReadinessService:
    """Read-only security gate for UAT/pilot/production review.

    The report intentionally checks configuration and metadata only. It does not
    read secrets, call external systems, enqueue jobs, mutate data, or scan raw
    tracking logs. It is stricter for real production and advisory for UAT.
    """

    report_type = 'security_readiness_v1'
    safe_policy = 'read_only_no_secret_values_no_mutation'
    read_only_guarantees = [
        'Không trả secret/token/password ra response',
        'Không gọi Open edX/AP/OpenAI trong request',
        'Không enqueue job hoặc recalculate',
        'Không đọc raw tracking.log',
        'Không mutate database',
    ]

    def __init__(self) -> None:
        self.production = is_production()
        self.env_name = (settings.app_env or '').strip().lower() or 'dev'

    def report(self) -> dict[str, Any]:
        checks = self._checks()
        blockers = [item for item in checks if item.severity == 'BLOCKER' and not item.ok]
        warnings = [item for item in checks if item.severity == 'WARNING' and not item.ok]
        infos = [item for item in checks if item.severity == 'INFO']
        status = 'BLOCKED' if blockers else ('READY_WITH_WARNINGS' if warnings else 'READY')
        sections = self._sections(checks)
        next_actions = self._next_actions(blockers, warnings)
        return {
            'version': settings.app_version,
            'report_type': self.report_type,
            'generated_at': datetime.now(timezone.utc).isoformat(),
            'app_env': settings.app_env,
            'status': status,
            'summary_label': self._summary_label(status),
            'blocker_count': len(blockers),
            'warning_count': len(warnings),
            'info_count': len(infos),
            'can_pilot': not blockers,
            'can_broad_production': status == 'READY' and self.production,
            'primary_blocker': asdict(blockers[0]) if blockers else None,
            'checks': [asdict(item) for item in checks],
            'sections': sections,
            'next_actions': next_actions,
            'safe_policy': self.safe_policy,
            'read_only_guarantees': self.read_only_guarantees,
            'disclaimer': 'Security readiness chỉ là gate cấu hình/vận hành; vẫn cần review code, infra firewall, backup và log retention trước production thật.',
        }

    def _severity(self, prod_blocker: bool = True) -> str:
        if self.production and prod_blocker:
            return 'BLOCKER'
        return 'WARNING'

    @staticmethod
    def _strong_secret(value: str | None, min_len: int = 32) -> bool:
        if not value:
            return False
        text = str(value)
        if text in {'dev_secret_change_me', 'minioadmin'}:
            return False
        if text.startswith('CHANGE_ME') or 'CHANGE_ME' in text:
            return False
        return len(text) >= min_len

    @staticmethod
    def _set(value: Any) -> bool:
        return value is not None and str(value).strip() != ''

    def _check(self, category: str, code: str, ok: bool, message: str, action: str, *, severity: str | None = None, actual: Any | None = None, target: str | None = None) -> SecurityReadinessCheck:
        return SecurityReadinessCheck(
            category=category,
            code=code,
            severity=severity or ('INFO' if ok else self._severity()),
            ok=bool(ok),
            message=message,
            action=action,
            actual=actual,
            target=target,
        )

    def _checks(self) -> list[SecurityReadinessCheck]:
        origins = cors_origin_list()
        auth_mode = (settings.auth_mode or '').lower().strip()
        storage_provider = (settings.storage_provider or '').lower().strip()
        cookie_samesite = (settings.auth_cookie_samesite or '').lower().strip()
        checks: list[SecurityReadinessCheck] = []

        checks.append(self._check(
            'runtime', 'DEBUG_DISABLED', not bool(settings.debug),
            'DEBUG phải tắt ở môi trường production để không lộ stack/runtime detail.',
            'Set DEBUG=false trong .env.production.', actual=settings.debug, target='false'
        ))
        checks.append(self._check(
            'runtime', 'AUTO_CREATE_TABLES_DISABLED', not bool(settings.auto_create_tables),
            'Production phải chạy Alembic, không tự tạo bảng lúc startup.',
            'Set AUTO_CREATE_TABLES=false và verify alembic current/head.', actual=settings.auto_create_tables, target='false'
        ))
        checks.append(self._check(
            'runtime', 'DATABASE_POSTGRESQL', str(settings.database_url).startswith('postgresql'),
            'DATABASE_URL production phải dùng PostgreSQL, không dùng SQLite/demo DB.',
            'Set DATABASE_URL=postgresql+psycopg://... và không commit secret.', actual=self._redact_url(settings.database_url), target='postgresql+psycopg://...'
        ))
        checks.append(self._check(
            'runtime', 'DATABASE_URL_NO_PLACEHOLDER', 'CHANGE_ME' not in str(settings.database_url),
            'DATABASE_URL không được còn placeholder.',
            'Thay toàn bộ CHANGE_ME trong .env.production bằng secret thật.', actual='contains_CHANGE_ME' if 'CHANGE_ME' in str(settings.database_url) else 'ok'
        ))

        checks.append(self._check(
            'auth', 'AUTH_MODE_PRODUCTION_SAFE', auth_mode in {'jwt', 'openedx_sso'},
            'AUTH_MODE demo chỉ dùng local/UAT kỹ thuật, không dùng production thật.',
            'Set AUTH_MODE=openedx_sso hoặc jwt.', actual=settings.auth_mode, target='openedx_sso|jwt'
        ))
        checks.append(self._check(
            'auth', 'DEMO_ROLE_HEADER_DISABLED', not bool(settings.allow_demo_role_header),
            'ALLOW_DEMO_ROLE_HEADER cho phép giả role bằng header, phải tắt khi production.',
            'Set ALLOW_DEMO_ROLE_HEADER=false.', actual=settings.allow_demo_role_header, target='false'
        ))
        checks.append(self._check(
            'auth', 'JWT_SECRET_STRONG', self._strong_secret(settings.jwt_secret),
            'JWT_SECRET phải là secret mạnh, không dùng mặc định dev.',
            'Generate secret >=32 ký tự và rotate token sau khi đổi.', actual=self._secret_state(settings.jwt_secret), target='>=32 chars non-placeholder'
        ))
        if auth_mode == 'openedx_sso':
            bridge_secret = settings.openedx_session_bridge_secret or settings.openedx_connector_hmac_secret
            checks.append(self._check(
                'auth', 'SSO_BRIDGE_SECRET_STRONG', self._strong_secret(str(bridge_secret) if bridge_secret else None),
                'SSO bridge cần HMAC secret mạnh giữa CMS connector và AI Server.',
                'Set OPENEDX_SESSION_BRIDGE_SECRET hoặc OPENEDX_CONNECTOR_HMAC_SECRET >=32 ký tự.', actual=self._secret_state(str(bridge_secret) if bridge_secret else None)
            ))
        checks.append(self._check(
            'auth', 'COOKIE_SECURE_ENABLED', bool(settings.auth_cookie_secure),
            'Cookie AI session phải bật Secure khi chạy qua HTTPS.',
            'Set AUTH_COOKIE_SECURE=true.', actual=settings.auth_cookie_secure, target='true'
        ))
        allowed_samesite = {'lax', 'strict'} if self.production else {'lax', 'strict', 'none'}
        checks.append(self._check(
            'auth', 'COOKIE_SAMESITE_VALID', cookie_samesite in allowed_samesite,
            'AUTH_COOKIE_SAMESITE production phải là lax hoặc strict.',
            'Set AUTH_COOKIE_SAMESITE=lax hoặc strict.', actual=settings.auth_cookie_samesite
        ))
        checks.append(self._check(
            'auth', 'COOKIE_NONE_REQUIRES_SECURE', not (cookie_samesite == 'none' and not settings.auth_cookie_secure),
            'SameSite=None bắt buộc cookie Secure.',
            'Bật AUTH_COOKIE_SECURE=true hoặc đổi AUTH_COOKIE_SAMESITE=lax.', actual={'same_site': settings.auth_cookie_samesite, 'secure': settings.auth_cookie_secure}
        ))
        checks.append(self._check(
            'auth', 'SESSION_TTL_BOUNDED', 900 <= int(settings.auth_session_token_ttl_seconds or 0) <= 7200,
            'Phiên AI Server phải ngắn hạn để giảm rủi ro khi cookie bị đánh cắp.',
            'Set AUTH_SESSION_TOKEN_TTL_SECONDS trong khoảng 900..7200.', actual=settings.auth_session_token_ttl_seconds, target='900..7200 seconds'
        ))
        checks.append(self._check(
            'auth', 'SSO_TICKET_MAX_AGE_BOUNDED', 30 <= int(settings.openedx_session_bridge_max_age_seconds or 0) <= 60,
            'CMS bridge ticket chỉ nên tồn tại 30–60 giây.',
            'Set OPENEDX_SESSION_BRIDGE_MAX_AGE_SECONDS trong khoảng 30..60.', actual=settings.openedx_session_bridge_max_age_seconds, target='30..60 seconds'
        ))
        checks.append(self._check(
            'auth', 'SSO_EXCHANGE_RATE_LIMITED', int(settings.auth_exchange_rate_limit_per_minute or 0) >= 1 and int(settings.auth_exchange_ticket_rate_limit_per_minute or 0) >= 1,
            'Endpoint exchange phải giới hạn theo IP và fingerprint ticket.',
            'Set AUTH_EXCHANGE_RATE_LIMIT_PER_MINUTE và AUTH_EXCHANGE_TICKET_RATE_LIMIT_PER_MINUTE >=1.', actual={'ip': settings.auth_exchange_rate_limit_per_minute, 'ticket': settings.auth_exchange_ticket_rate_limit_per_minute}
        ))
        checks.append(self._check(
            'auth', 'SSO_REPLAY_STORE_CONFIGURED', bool(str(settings.redis_url or '').strip()) and 'CHANGE_ME' not in str(settings.redis_url),
            'Redis được dùng để claim ticket một lần và thu hồi session JWT theo jti.',
            'Set REDIS_URL tới Redis production có persistence/availability phù hợp.', actual=self._redact_url(settings.redis_url), target='redis://...'
        ))

        explicit_origins = bool(origins) and '*' not in origins
        checks.append(self._check(
            'network', 'CORS_EXPLICIT_WHITELIST', explicit_origins,
            'CORS phải là whitelist cụ thể, không dùng wildcard.',
            'Set CORS_ALLOWED_ORIGINS=https://ai.cms-test.poly.edu.vn,https://api-ai.cms-test.poly.edu.vn,...', actual=origins, target='no wildcard'
        ))
        localhost_origins = [item for item in origins if 'localhost' in item or '127.0.0.1' in item]
        checks.append(self._check(
            'network', 'CORS_NO_LOCALHOST_IN_PRODUCTION', not (self.production and localhost_origins),
            'Production không được cho phép localhost origins.',
            'Xóa localhost/127.0.0.1 khỏi CORS_ALLOWED_ORIGINS trên production thật.', actual=localhost_origins or 'none'
        ))
        insecure_origins = [item for item in origins if item.startswith('http://') and 'localhost' not in item and '127.0.0.1' not in item]
        checks.append(self._check(
            'network', 'CORS_HTTPS_OR_INTERNAL_ONLY', not insecure_origins,
            'CORS public origin nên dùng HTTPS; HTTP chỉ chấp nhận nội bộ/local có kiểm soát.',
            'Đổi public origin sang https:// hoặc bỏ khỏi whitelist.', actual=insecure_origins or 'none', severity='WARNING' if insecure_origins else 'INFO'
        ))

        metrics_ok = (not settings.metrics_enabled) or self._strong_secret(settings.metrics_token)
        checks.append(self._check(
            'observability', 'METRICS_TOKEN_PROTECTED', metrics_ok,
            '/metrics phải tắt hoặc bảo vệ bằng token mạnh.',
            'Set METRICS_ENABLED=false hoặc METRICS_TOKEN >=32 ký tự.', actual={'enabled': settings.metrics_enabled, 'token': self._secret_state(settings.metrics_token)}
        ))
        checks.append(self._check(
            'observability', 'HEALTH_DETAIL_AUTH_REQUIRED', True,
            'Các endpoint readiness/detail đang yêu cầu permission; /health và /health/build chỉ trả metadata an toàn.',
            'Giữ /health/db, /health/readiness, /health/security-readiness sau auth.', severity='INFO', actual='authenticated detail routes'
        ))

        checks.append(self._check(
            'integration', 'MOCK_OPENEDX_DISABLED', not bool(settings.use_mock_openedx),
            'Production không được dùng mock Open edX.',
            'Set USE_MOCK_OPENEDX=false và cấu hình connector thật.', actual=settings.use_mock_openedx, target='false'
        ))
        checks.append(self._check(
            'integration', 'OPENEDX_CONNECTOR_HMAC_SECRET_STRONG', self._strong_secret(settings.openedx_connector_hmac_secret),
            'Open edX connector cần HMAC secret mạnh.',
            'Set OPENEDX_CONNECTOR_HMAC_SECRET cùng giá trị với CMS connector plugin.', actual=self._secret_state(settings.openedx_connector_hmac_secret)
        ))
        checks.append(self._check(
            'integration', 'OPENEDX_OAUTH_SECRET_SET', self._strong_secret(settings.openedx_client_secret, 12) or not self.production,
            'Open edX OAuth client secret phải có khi production dùng connector/publish thật.',
            'Set OPENEDX_CLIENT_ID và OPENEDX_CLIENT_SECRET thật.', actual=self._secret_state(settings.openedx_client_secret), severity=None if self.production else 'WARNING'
        ))
        ap_ok = (not settings.academic_ap_sync_enabled) or self._strong_secret(settings.academic_ap_api_key, 12)
        checks.append(self._check(
            'integration', 'AP_API_KEY_SET_WHEN_SYNC_ENABLED', ap_ok,
            'AP sync bật thì phải có API key/token thật.',
            'Set ACADEMIC_AP_API_KEY hoặc tắt ACADEMIC_AP_SYNC_ENABLED nếu chưa dùng.', actual={'sync_enabled': settings.academic_ap_sync_enabled, 'key': self._secret_state(settings.academic_ap_api_key)}
        ))

        checks.append(self._check(
            'llm', 'MOCK_LLM_DISABLED', not bool(settings.mock_llm),
            'Production không được dùng mock LLM khi sinh câu hỏi thật.',
            'Set MOCK_LLM=false.', actual=settings.mock_llm, target='false'
        ))
        checks.append(self._check(
            'llm', 'OPENAI_API_KEY_SET', self._strong_secret(settings.openai_api_key, 12) or bool(settings.mock_llm and not self.production),
            'OPENAI_API_KEY cần thiết khi MOCK_LLM=false.',
            'Set OPENAI_API_KEY thật qua secret manager/.env.production.', actual=self._secret_state(settings.openai_api_key)
        ))

        minio_default = storage_provider == 'minio' and (settings.minio_access_key == 'minioadmin' or settings.minio_secret_key == 'minioadmin')
        checks.append(self._check(
            'storage', 'NO_DEFAULT_MINIO_CREDENTIALS', not minio_default,
            'Không dùng credential MinIO mặc định trong môi trường chia sẻ/production.',
            'Đổi MINIO_ACCESS_KEY/MINIO_SECRET_KEY hoặc dùng storage_provider được phê duyệt.', actual='default_minio_credentials' if minio_default else storage_provider
        ))
        minio_enabled = storage_provider == 'minio'
        minio_endpoint = str(settings.minio_endpoint or '').strip()
        checks.append(self._check(
            'storage', 'PRODUCTION_EXTERNAL_MINIO_ENABLED', minio_enabled or not self.production,
            'Production AI Server phải ghi artifact lâu dài vào MinIO dùng chung ngoài cụm.',
            'Set STORAGE_PROVIDER=minio trong ai-server-env.', actual=storage_provider, target='minio'
        ))
        checks.append(self._check(
            'storage', 'MINIO_HTTPS_CERT_VERIFIED', (not minio_enabled) or (minio_endpoint.startswith('https://') and bool(settings.minio_cert_check)),
            'Kết nối MinIO production phải dùng HTTPS và xác minh chứng chỉ.',
            'Set MINIO_ENDPOINT=https://s3.fpl.edu.vn và MINIO_CERT_CHECK=true.',
            actual={'https': minio_endpoint.startswith('https://'), 'cert_check': bool(settings.minio_cert_check)},
            target='https + cert_check'
        ))
        minio_secret_ok = (not minio_enabled) or (
            self._strong_secret(settings.minio_secret_key, 12)
            and bool(str(settings.minio_access_key or '').strip())
            and 'CHANGE_ME' not in str(settings.minio_access_key)
        )
        checks.append(self._check(
            'storage', 'MINIO_SERVICE_ACCOUNT_CONFIGURED', minio_secret_ok,
            'AI Server cần service account MinIO riêng, giới hạn trong bucket của AI Server.',
            'Inject MINIO_ACCESS_KEY/MINIO_SECRET_KEY thật qua Kubernetes Secret.',
            actual={'access_key': self._secret_state(settings.minio_access_key), 'secret_key': self._secret_state(settings.minio_secret_key)}
        ))
        checks.append(self._check(
            'storage', 'MINIO_BUCKET_PRECREATED', (not minio_enabled) or not bool(settings.minio_auto_create_bucket),
            'Production không được tự tạo bucket bằng credential runtime.',
            'Tạo trước bucket private ai-server và giữ MINIO_AUTO_CREATE_BUCKET=false.',
            actual={'bucket': settings.minio_bucket, 'auto_create': bool(settings.minio_auto_create_bucket)}, target='auto_create=false'
        ))
        checks.append(self._check(
            'storage', 'UPLOAD_LIMITS_BOUNDED', settings.max_upload_bytes <= 200 * 1024 * 1024 and settings.max_zip_uncompressed_bytes <= 1024 * 1024 * 1024,
            'Giới hạn upload/zip phải bounded để tránh zip bomb hoặc file quá lớn.',
            'Giữ MAX_UPLOAD_BYTES và MAX_ZIP_UNCOMPRESSED_BYTES ở mức được phê duyệt.', actual={'max_upload_bytes': settings.max_upload_bytes, 'max_zip_uncompressed_bytes': settings.max_zip_uncompressed_bytes}, severity='WARNING'
        ))
        allowed_hosts = [item.strip() for item in (settings.openedx_allowed_download_hosts or '').split(',') if item.strip()]
        checks.append(self._check(
            'ssrf', 'DOWNLOAD_HOST_ALLOWLIST_CONFIGURED', bool(allowed_hosts) or not self.production,
            'Download tài liệu/asset từ URL cần allowlist host để giảm SSRF.',
            'Set OPENEDX_ALLOWED_DOWNLOAD_HOSTS chỉ gồm domain Open edX/AP/CDN được phép.', actual=allowed_hosts or 'not_set'
        ))
        checks.append(self._check(
            'data_safety', 'DESTRUCTIVE_IDENTITY_CLEANUP_DISABLED_IN_PRODUCTION', not (self.production and settings.academic_identity_cleanup_allow_destructive),
            'Cleanup identity phá dữ liệu chỉ dành cho UAT, phải tắt ở production thật.',
            'Set ACADEMIC_IDENTITY_CLEANUP_ALLOW_DESTRUCTIVE=false trên production.', actual=settings.academic_identity_cleanup_allow_destructive, target='false'
        ))
        checks.append(self._check(
            'data_safety', 'INLINE_EXTRACTION_DISABLED', not bool(settings.bank_material_extract_inline_enabled),
            'Material extraction nặng phải chạy job nền, không chạy inline ở request.',
            'Set BANK_MATERIAL_EXTRACT_INLINE_ENABLED=false.', actual=settings.bank_material_extract_inline_enabled, target='false', severity='WARNING' if settings.bank_material_extract_inline_enabled else 'INFO'
        ))

        return checks

    @staticmethod
    def _redact_url(url: str) -> str:
        text = str(url or '')
        if '://' not in text or '@' not in text:
            return text.split('?')[0]
        prefix, rest = text.split('://', 1)
        if '@' not in rest:
            return f'{prefix}://{rest}'
        _, host = rest.rsplit('@', 1)
        return f'{prefix}://***:***@{host.split("?", 1)[0]}'

    @staticmethod
    def _secret_state(value: str | None) -> str:
        if not value:
            return 'missing'
        text = str(value)
        if text in {'dev_secret_change_me', 'minioadmin'} or text.startswith('CHANGE_ME') or 'CHANGE_ME' in text:
            return 'placeholder'
        if len(text) < 12:
            return 'too_short'
        if len(text) < 32:
            return 'set_short'
        return 'set_strong'

    @staticmethod
    def _sections(checks: list[SecurityReadinessCheck]) -> list[dict[str, Any]]:
        title_map = {
            'runtime': 'Runtime/DB',
            'auth': 'Xác thực & cookie',
            'network': 'CORS/Network',
            'observability': 'Metrics/Health',
            'integration': 'Open edX/AP connector',
            'llm': 'LLM/API key',
            'storage': 'Storage/Upload',
            'ssrf': 'SSRF/download guard',
            'data_safety': 'Data safety',
        }
        sections: list[dict[str, Any]] = []
        for key in title_map:
            items = [item for item in checks if item.category == key]
            if not items:
                continue
            blockers = [item for item in items if item.severity == 'BLOCKER' and not item.ok]
            warnings = [item for item in items if item.severity == 'WARNING' and not item.ok]
            status = 'BLOCKED' if blockers else ('WARNING' if warnings else 'OK')
            sections.append({
                'key': key,
                'title': title_map[key],
                'status': status,
                'check_count': len(items),
                'blocker_count': len(blockers),
                'warning_count': len(warnings),
            })
        return sections

    @staticmethod
    def _summary_label(status: str) -> str:
        if status == 'READY':
            return 'Security gate đạt cho production'
        if status == 'READY_WITH_WARNINGS':
            return 'Security gate có cảnh báo cần theo dõi'
        return 'Security gate còn blocker cần xử lý'

    @staticmethod
    def _next_actions(blockers: list[SecurityReadinessCheck], warnings: list[SecurityReadinessCheck]) -> list[str]:
        actions: list[str] = []
        for item in blockers + warnings:
            if item.action and item.action not in actions:
                actions.append(item.action)
            if len(actions) >= 8:
                break
        if not actions:
            actions.append('Giữ cấu hình hiện tại, chạy lại security readiness sau mỗi thay đổi env/deploy.')
        return actions
