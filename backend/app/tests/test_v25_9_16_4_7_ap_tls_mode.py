import ssl

import pytest

pytest.importorskip("psycopg")

from app.services import ap_academic_sync


def _client_with_mode(monkeypatch, mode: str):
    monkeypatch.setattr(ap_academic_sync.settings, "academic_ap_sync_enabled", True)
    monkeypatch.setattr(ap_academic_sync.settings, "academic_ap_api_base_url", "https://api_v2.poly.edu.vn")
    monkeypatch.setattr(ap_academic_sync.settings, "academic_ap_api_key", "x" * 16)
    monkeypatch.setattr(ap_academic_sync.settings, "academic_ap_request_timeout_seconds", 10)
    monkeypatch.setattr(ap_academic_sync.settings, "academic_ap_tls_mode", mode)
    return ap_academic_sync.APAcademicClient()


def test_ap_tls_chain_only_verifies_ca_but_skips_hostname(monkeypatch):
    client = _client_with_mode(monkeypatch, "chain_only")

    verify = client._verify_config()

    assert isinstance(verify, ssl.SSLContext)
    assert verify.verify_mode == ssl.CERT_REQUIRED
    assert verify.check_hostname is False


def test_ap_tls_off_disables_verification(monkeypatch):
    client = _client_with_mode(monkeypatch, "off")

    assert client._verify_config() is False


def test_ap_tls_strict_uses_httpx_default(monkeypatch):
    client = _client_with_mode(monkeypatch, "strict")

    assert client._verify_config() is True
