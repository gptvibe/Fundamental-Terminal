from __future__ import annotations

from datetime import datetime, timezone

from fastapi import Response
from starlette.requests import Request

import app.main as main_module


class _Payload:
    def __init__(self, data: dict[str, object]):
        self._data = data

    def model_dump(self, mode: str = "json") -> dict[str, object]:
        assert mode == "json"
        return self._data


def _request_with_headers(headers: list[tuple[bytes, bytes]]) -> Request:
    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "path": "/api/companies/AAPL/financials",
        "query_string": b"",
        "headers": headers,
        "client": ("127.0.0.1", 12345),
        "server": ("testserver", 80),
    }
    return Request(scope)


def test_apply_conditional_headers_sets_etag_and_cache_control():
    payload = _Payload({"company": {"ticker": "AAPL"}, "refresh": {"triggered": False}})
    request = _request_with_headers([])
    response = Response()

    not_modified = main_module._apply_conditional_headers(
        request,
        response,
        payload,
        last_modified=datetime.now(timezone.utc),
    )

    assert not_modified is None
    assert response.headers.get("ETag")
    assert response.headers.get("Cache-Control") == "private, max-age=0, stale-while-revalidate=120"
    assert response.headers.get("Last-Modified")


def test_apply_conditional_headers_returns_304_on_etag_match():
    payload = _Payload({"company": {"ticker": "MSFT"}, "refresh": {"triggered": False}})
    probe_request = _request_with_headers([])
    probe_response = Response()
    main_module._apply_conditional_headers(
        probe_request,
        probe_response,
        payload,
        last_modified=datetime.now(timezone.utc),
    )
    etag = probe_response.headers["ETag"]

    request = _request_with_headers([(b"if-none-match", etag.encode("utf-8"))])
    response = Response()
    not_modified = main_module._apply_conditional_headers(
        request,
        response,
        payload,
        last_modified=datetime.now(timezone.utc),
    )

    assert not_modified is not None
    assert not_modified.status_code == 304
