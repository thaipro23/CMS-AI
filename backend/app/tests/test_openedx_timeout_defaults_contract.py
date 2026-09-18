from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
CONFIG = ROOT / 'backend/app/core/config.py'
ENV = ROOT / '.env.example'
ENV_PROD = ROOT / '.env.production.example'


def test_openedx_http_timeout_defaults_are_60_seconds():
    config = CONFIG.read_text(encoding='utf-8')
    assert 'openedx_connector_timeout_seconds: int = 60' in config
    assert 'academic_ap_request_timeout_seconds: int = 60' in config
    assert 'openedx_request_timeout_seconds: int = 60' in config
    assert 'openedx_write_timeout_seconds: int = 60' in config


def test_env_examples_match_60_second_timeout_budget():
    for path in (ENV, ENV_PROD):
        text = path.read_text(encoding='utf-8')
        assert 'OPENEDX_CONNECTOR_TIMEOUT_SECONDS=60' in text
        assert 'ACADEMIC_AP_REQUEST_TIMEOUT_SECONDS=60' in text
        assert 'OPENEDX_REQUEST_TIMEOUT_SECONDS=60' in text
        assert 'OPENEDX_WRITE_TIMEOUT_SECONDS=60' in text
