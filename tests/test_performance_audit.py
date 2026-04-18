from __future__ import annotations

import json
from types import SimpleNamespace

import pytest
from starlette.requests import Request

import app.performance_audit as performance_audit


def _request_with_query_string(query_string: str, *, path: str = "/api/companies/AAPL/models") -> Request:
    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "path": path,
        "query_string": query_string.encode("utf-8"),
        "headers": [],
        "client": ("127.0.0.1", 12345),
        "server": ("testserver", 80),
    }
    request = Request(scope)
    request.scope["route"] = SimpleNamespace(path="/api/companies/{ticker}/models")
    return request


@pytest.fixture(autouse=True)
def _reset_performance_audit_store() -> None:
    performance_audit.reset()
    yield
    performance_audit.reset()


def test_sanitize_query_string_redacts_sensitive_values_and_keeps_harmless_controls() -> None:
    request = _request_with_query_string(
        "query=Jane+Doe&token=secret-token&model=dcf&refresh=false&expand=input_periods"
    )

    sanitized = performance_audit._sanitize_query_string(request)

    assert sanitized == "expand=input_periods&model=dcf&query=REDACTED&refresh=false&token=REDACTED"
    assert "Jane+Doe" not in sanitized
    assert "secret-token" not in sanitized


def test_begin_request_uses_sanitized_query_but_preserves_refresh_classification() -> None:
    request = _request_with_query_string("refresh=true&email=user%40example.com")

    metrics, token = performance_audit.begin_request(request)
    try:
        assert metrics.query_string == "email=REDACTED&refresh=true"
        assert metrics.request_kind == "refresh"
    finally:
        performance_audit.end_request(token)


def test_complete_request_logs_sanitized_query_and_preserves_status_timing_metrics(caplog: pytest.LogCaptureFixture) -> None:
    request = _request_with_query_string("model=dcf&query=user-input&max_points=12")

    with caplog.at_level("INFO", logger="app.performance_audit"):
        metrics, token = performance_audit.begin_request(request)
        try:
            performance_audit.complete_request(request, metrics, status_code=200)
        finally:
            performance_audit.end_request(token)

    structured_logs = [json.loads(record.message) for record in caplog.records if record.message.startswith("{")]
    assert structured_logs

    payload = structured_logs[-1]
    assert payload["event"] == "performance_audit.request"
    assert payload["query_string"] == "max_points=12&model=dcf&query=REDACTED"
    assert payload["status_code"] == 200
    assert payload["route_path"] == "/api/companies/{ticker}/models"
    assert payload["duration_ms"] >= 0

    snapshot = performance_audit.snapshot()
    assert snapshot["record_count"] == 1
    record = snapshot["records"][0]
    assert record["query_string"] == "max_points=12&model=dcf&query=REDACTED"
    assert record["status_code"] == 200
    assert record["duration_ms"] >= 0
