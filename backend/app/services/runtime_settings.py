import json
import os
from pathlib import Path
from typing import Any

from app.core.config import settings

RUNTIME_CONFIG_PATH = Path(os.getenv('RUNTIME_CONFIG_PATH', '/app/.runtime/runtime-settings.json'))

MANAGED_FIELDS: dict[str, type] = {
    'openai_model': str,
    'openai_api_mode': str,
    'model_provider': str,
    'mock_llm': bool,
    'use_mock_openedx': bool,
    'auth_mode': str,
    'allow_demo_role_header': bool,
    'openedx_base_url': str,
    'openedx_cms_base_url': str,
    'openedx_lms_base_url': str,
    'openedx_oauth_base_url': str,
    'openedx_client_id': str,
    'openedx_oauth_token_url': str,
    'openedx_course_blocks_path': str,
    'openedx_publish_endpoint': str,
    'openedx_library_endpoint': str,
    'openedx_library_import_endpoint': str,
    'cost_input_price_per_1m': float,
    'cost_cached_input_price_per_1m': float,
    'cost_output_price_per_1m': float,
    'cost_safety_factor': float,
    'usd_to_vnd': float,
    'generation_tail_batch_wait_enabled': bool,
    'openai_prompt_cache_warmup_enabled': bool,
    'openai_retry_base_seconds': float,
    'openai_retry_max_attempts': int,
    'openai_max_parallel_calls': int,
    'openai_parallel_enabled': bool,
}

# Secrets are environment-only. They may be displayed as masked env-backed values,
# but PATCH /settings/runtime must never persist them to runtime-settings.json.
SECRET_FIELDS = {'openai_api_key', 'openedx_client_secret', 'openedx_access_token', 'jwt_secret'}

ALLOWED_MODEL_PROVIDERS = {'openai', 'local', 'auto'}
ALLOWED_OPENAI_API_MODES = {'responses', 'chat_legacy'}
ALLOWED_AUTH_MODES = {'demo', 'jwt', 'openedx_sso'}


def _coerce_value(name: str, value: Any) -> Any:
    if value is None:
        return None
    expected = MANAGED_FIELDS[name]
    if expected is bool:
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.strip().lower() in {'1', 'true', 'yes', 'on'}
        return bool(value)
    if expected is str:
        return str(value)
    if expected is float:
        return float(value)
    if expected is int:
        return int(value)
    return value


def _read_runtime_file() -> dict[str, Any]:
    if not RUNTIME_CONFIG_PATH.exists():
        return {}
    try:
        data = json.loads(RUNTIME_CONFIG_PATH.read_text(encoding='utf-8'))
    except json.JSONDecodeError:
        return {}
    if not isinstance(data, dict):
        return {}
    return {key: value for key, value in data.items() if key in MANAGED_FIELDS}


def _write_runtime_file(data: dict[str, Any]) -> None:
    RUNTIME_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    RUNTIME_CONFIG_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')


def apply_runtime_settings() -> None:
    """Apply persisted runtime settings over .env values.

    Runtime settings are intentionally limited to non-secret knobs. Secrets such
    as API keys, OAuth client secrets and JWT secrets are environment-only.
    """
    for key, value in _read_runtime_file().items():
        setattr(settings, key, _coerce_value(key, value))


def _mask_secret(value: str | None) -> str:
    if not value:
        return ''
    if len(value) <= 8:
        return '*' * len(value)
    return f'{value[:4]}...{value[-4:]}'


def public_runtime_settings() -> dict[str, Any]:
    apply_runtime_settings()
    return {
        'model': {
            'model_provider': settings.model_provider,
            'openai_model': settings.openai_model,
            'openai_api_mode': settings.openai_api_mode,
            'mock_llm': settings.mock_llm,
            'has_openai_api_key': bool(settings.openai_api_key),
            'openai_api_key_masked': _mask_secret(settings.openai_api_key),
        },
        'openedx': {
            'use_mock_openedx': settings.use_mock_openedx,
            'openedx_base_url': settings.openedx_base_url,
            'openedx_cms_base_url': settings.openedx_cms_base_url or settings.openedx_base_url,
            'openedx_lms_base_url': settings.openedx_lms_base_url,
            'openedx_oauth_base_url': settings.openedx_oauth_base_url or settings.openedx_lms_base_url or settings.openedx_base_url,
            'openedx_client_id': settings.openedx_client_id or '',
            'has_openedx_client_secret': bool(settings.openedx_client_secret),
            'openedx_client_secret_masked': _mask_secret(settings.openedx_client_secret),
            'has_openedx_access_token': bool(settings.openedx_access_token),
            'openedx_access_token_masked': _mask_secret(settings.openedx_access_token),
            'openedx_oauth_token_url': settings.openedx_oauth_token_url,
            'openedx_course_blocks_path': settings.openedx_course_blocks_path,
            'openedx_publish_endpoint': settings.openedx_publish_endpoint,
            'openedx_library_endpoint': settings.openedx_library_endpoint,
            'openedx_library_import_endpoint': settings.openedx_library_import_endpoint,
        },
        'sso': {
            'auth_mode': settings.auth_mode,
            'allow_demo_role_header': settings.allow_demo_role_header,
            'has_jwt_secret': bool(settings.jwt_secret),
            'jwt_secret_masked': _mask_secret(settings.jwt_secret),
        },
        'cost': {
            'cost_input_price_per_1m': settings.cost_input_price_per_1m,
            'cost_cached_input_price_per_1m': settings.cost_cached_input_price_per_1m,
            'cost_output_price_per_1m': settings.cost_output_price_per_1m,
            'cost_safety_factor': settings.cost_safety_factor,
            'usd_to_vnd': settings.usd_to_vnd,
        },
        'worker': {
            'openai_parallel_enabled': settings.openai_parallel_enabled,
            'openai_max_parallel_calls': settings.openai_max_parallel_calls,
            'openai_retry_max_attempts': settings.openai_retry_max_attempts,
            'openai_retry_base_seconds': settings.openai_retry_base_seconds,
            'openai_prompt_cache_warmup_enabled': settings.openai_prompt_cache_warmup_enabled,
            'generation_tail_batch_wait_enabled': settings.generation_tail_batch_wait_enabled,
        },
        'runtime_config_path': str(RUNTIME_CONFIG_PATH),
    }


def update_runtime_settings(payload: dict[str, Any]) -> dict[str, Any]:
    current = _read_runtime_file()
    updates: dict[str, Any] = {}

    supplied_secrets: list[str] = []

    model = payload.get('model') or {}
    openedx = payload.get('openedx') or {}
    sso = payload.get('sso') or {}
    cost = payload.get('cost') or {}
    worker = payload.get('worker') or {}

    for key in ['model_provider', 'openai_model', 'openai_api_mode', 'mock_llm']:
        if key in model:
            updates[key] = model[key]
    if 'openai_api_key' in model and model.get('openai_api_key') not in (None, ''):
        supplied_secrets.append('openai_api_key')
    for key in [
        'use_mock_openedx', 'openedx_base_url', 'openedx_cms_base_url', 'openedx_lms_base_url', 'openedx_oauth_base_url',
        'openedx_client_id', 'openedx_oauth_token_url', 'openedx_course_blocks_path',
        'openedx_publish_endpoint', 'openedx_library_endpoint', 'openedx_library_import_endpoint'
    ]:
        if key in openedx:
            updates[key] = openedx[key]
    for key in ['openedx_client_secret', 'openedx_access_token']:
        if key in openedx and openedx.get(key) not in (None, ''):
            supplied_secrets.append(key)
    for key in ['auth_mode', 'allow_demo_role_header']:
        if key in sso:
            updates[key] = sso[key]
    if 'jwt_secret' in sso and sso.get('jwt_secret') not in (None, ''):
        supplied_secrets.append('jwt_secret')
    for key in ['cost_input_price_per_1m', 'cost_cached_input_price_per_1m', 'cost_output_price_per_1m', 'cost_safety_factor', 'usd_to_vnd']:
        if key in cost:
            updates[key] = cost[key]
    for key in ['openai_parallel_enabled', 'openai_max_parallel_calls', 'openai_retry_max_attempts', 'openai_retry_base_seconds', 'openai_prompt_cache_warmup_enabled', 'generation_tail_batch_wait_enabled']:
        if key in worker:
            updates[key] = worker[key]

    if supplied_secrets:
        raise ValueError('Secrets are environment-only and were not saved to runtime-settings.json: ' + ', '.join(sorted(set(supplied_secrets))))

    for key, raw_value in updates.items():
        if key not in MANAGED_FIELDS:
            continue
        value = _coerce_value(key, raw_value)
        if key == 'model_provider' and value not in ALLOWED_MODEL_PROVIDERS:
            raise ValueError('model_provider must be one of: openai, local, auto')
        if key == 'openai_api_mode' and value not in ALLOWED_OPENAI_API_MODES:
            raise ValueError('openai_api_mode must be one of: responses, chat_legacy')
        if key == 'auth_mode' and value not in ALLOWED_AUTH_MODES:
            raise ValueError('auth_mode must be one of: demo, jwt, openedx_sso')
        if key.startswith('cost_') and float(value) < 0:
            raise ValueError(f'{key} must be >= 0')
        if key == 'usd_to_vnd' and float(value) <= 0:
            raise ValueError('usd_to_vnd must be > 0')
        if key == 'openai_max_parallel_calls' and not (1 <= int(value) <= 8):
            raise ValueError('openai_max_parallel_calls must be between 1 and 8')
        if key == 'openai_retry_max_attempts' and not (1 <= int(value) <= 8):
            raise ValueError('openai_retry_max_attempts must be between 1 and 8')
        current[key] = value
        setattr(settings, key, value)

    _write_runtime_file(current)
    return public_runtime_settings()
