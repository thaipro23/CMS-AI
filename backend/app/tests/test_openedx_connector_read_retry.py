from __future__ import annotations

from unittest.mock import patch

import httpx
import pytest

from app.core.config import settings
from app.services.openedx_student_insight import OpenEdXConnectorClient


def _connector_client() -> OpenEdXConnectorClient:
    client = OpenEdXConnectorClient.__new__(OpenEdXConnectorClient)
    client.public_base_url = "https://cms.fpl.edu.vn"
    client.base_url = "http://lms:8000"
    client.connector_host_header = "cms.fpl.edu.vn"
    client.connector_secret = "test-secret"
    client.shared_secret = "test-secret"
    client.client_id = "ai-server"
    client.timeout_seconds = 60
    client.class_analytics_endpoint = "/api/ai-connector/v1/class-analytics"
    return client


def _response(status_code: int, payload: dict | None = None) -> httpx.Response:
    request = httpx.Request(
        "POST",
        "http://lms:8000/api/ai-connector/v1/class-analytics",
    )
    return httpx.Response(
        status_code,
        request=request,
        json=payload or {"ok": status_code < 400},
    )


class _SequencedHttpxClient:
    responses: list[object] = []
    calls: list[dict] = []

    def __init__(self, *args, **kwargs):
        self.timeout = kwargs.get("timeout")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def post(self, url, *, content, headers):
        self.__class__.calls.append(
            {
                "url": url,
                "content": content,
                "headers": dict(headers),
            }
        )
        item = self.__class__.responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


@pytest.fixture(autouse=True)
def _reset_fake_httpx_client():
    _SequencedHttpxClient.responses = []
    _SequencedHttpxClient.calls = []
    yield
    _SequencedHttpxClient.responses = []
    _SequencedHttpxClient.calls = []


@pytest.mark.parametrize("status_code", [502, 503, 504])
def test_read_only_class_analytics_retries_transient_status(status_code):
    client = _connector_client()
    _SequencedHttpxClient.responses = [
        _response(status_code),
        _response(200, {"ok": True, "results": []}),
    ]

    with (
        patch("app.services.openedx_student_insight.httpx.Client", _SequencedHttpxClient),
        patch("app.services.openedx_student_insight.time_module.sleep") as sleep,
        patch.object(settings, "openedx_connector_read_retry_max_attempts", 2),
        patch.object(settings, "openedx_connector_read_retry_base_seconds", 0.5),
        patch.object(settings, "openedx_connector_read_retry_max_seconds", 1.0),
    ):
        result = client._post_json(
            path=client.class_analytics_endpoint,
            body={"course_id": "course-v1:FPS+COM1091+FA26", "students": []},
            operation="lấy tiến độ/điểm CMS",
            retry_transient_read=True,
        )

    assert result["ok"] is True
    assert len(_SequencedHttpxClient.calls) == 2
    assert sleep.call_count == 1
    sleep.assert_called_once_with(0.5)

    first_nonce = _SequencedHttpxClient.calls[0]["headers"]["X-AI-Connector-Nonce"]
    second_nonce = _SequencedHttpxClient.calls[1]["headers"]["X-AI-Connector-Nonce"]
    assert first_nonce
    assert second_nonce
    assert first_nonce != second_nonce
    assert _SequencedHttpxClient.calls[0]["headers"]["Host"] == "cms.fpl.edu.vn"
    assert _SequencedHttpxClient.calls[1]["url"].startswith("http://lms:8000/")


def test_mutating_connector_post_does_not_retry_transient_status():
    client = _connector_client()
    _SequencedHttpxClient.responses = [
        _response(503),
        _response(200, {"ok": True}),
    ]

    with (
        patch("app.services.openedx_student_insight.httpx.Client", _SequencedHttpxClient),
        patch("app.services.openedx_student_insight.time_module.sleep") as sleep,
    ):
        with pytest.raises(httpx.HTTPStatusError):
            client._post_json(
                path="/api/ai-connector/v1/course-enrollment/enroll",
                body={"course_id": "course-v1:FPS+COM1091+FA26", "students": []},
                operation="enroll Course CMS",
            )

    assert len(_SequencedHttpxClient.calls) == 1
    sleep.assert_not_called()


def test_read_only_class_analytics_retries_transport_error():
    client = _connector_client()
    request = httpx.Request(
        "POST",
        "http://lms:8000/api/ai-connector/v1/class-analytics",
    )
    _SequencedHttpxClient.responses = [
        httpx.ConnectError("service temporarily unavailable", request=request),
        _response(200, {"ok": True, "results": []}),
    ]

    with (
        patch("app.services.openedx_student_insight.httpx.Client", _SequencedHttpxClient),
        patch("app.services.openedx_student_insight.time_module.sleep"),
        patch.object(settings, "openedx_connector_read_retry_max_attempts", 2),
    ):
        result = client._post_json(
            path=client.class_analytics_endpoint,
            body={"course_id": "course-v1:FPS+COM1091+FA26", "students": []},
            operation="lấy tiến độ/điểm CMS",
            retry_transient_read=True,
        )

    assert result["ok"] is True
    assert len(_SequencedHttpxClient.calls) == 2


def test_class_analytics_payload_enables_read_only_retry():
    client = _connector_client()

    with patch.object(
        client,
        "_post_json",
        return_value={"ok": True, "results": []},
    ) as post_json:
        payload = client.class_analytics_payload(
            course_id="course-v1:FPS+COM1091+FA26",
            students=[],
        )

    assert payload["ok"] is True
    assert post_json.call_args.kwargs["retry_transient_read"] is True
