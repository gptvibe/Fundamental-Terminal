from __future__ import annotations

import json
from types import SimpleNamespace

import httpx

import app.services.sec_cache as sec_cache_module
import app.services.sec_edgar as sec_edgar


def test_edgar_client_revalidates_company_tickers_with_if_modified_since(monkeypatch, tmp_path) -> None:
    ticker_lookup_url = "https://www.sec.gov/files/company_tickers.json"
    last_modified = "Fri, 17 Apr 2026 20:48:02 GMT"
    payload_bytes = json.dumps(
        {
            "0": {
                "ticker": "AAPL",
                "title": "Apple Inc.",
                "cik_str": 320193,
            }
        }
    ).encode("utf-8")
    observed_headers: list[dict[str, str]] = []

    monkeypatch.setattr(
        sec_cache_module,
        "settings",
        SimpleNamespace(
            sec_ticker_cache_ttl_seconds=60,
        ),
    )
    monkeypatch.setattr(
        sec_edgar,
        "settings",
        SimpleNamespace(
            sec_user_agent="test-agent",
            sec_timeout_seconds=10.0,
            sec_min_request_interval_seconds=0.01,
            sec_max_retries=1,
            sec_retry_backoff_seconds=0.01,
            sec_max_retry_backoff_seconds=0.01,
            sec_max_retry_after_seconds=0.01,
            sec_ticker_lookup_url=ticker_lookup_url,
        ),
    )

    cache = sec_cache_module.SecHttpCache(tmp_path)
    monkeypatch.setattr(sec_edgar, "sec_http_cache", cache)
    monkeypatch.setattr(sec_edgar.shared_upstream_cache, "_redis", None)
    sec_edgar.shared_upstream_cache.clear_local()

    client = sec_edgar.EdgarClient()
    try:
        monkeypatch.setattr(client, "_throttle", lambda: None)

        def _request(method: str, url: str, **kwargs):
            headers = dict(kwargs.get("headers") or {})
            observed_headers.append(headers)
            request = httpx.Request(method, url, headers=headers)
            if len(observed_headers) == 1:
                return httpx.Response(
                    200,
                    headers={
                        "content-type": "application/json",
                        "last-modified": last_modified,
                    },
                    content=payload_bytes,
                    request=request,
                )
            return httpx.Response(
                304,
                headers={"last-modified": last_modified},
                request=request,
            )

        monkeypatch.setattr(client._http, "request", _request)

        first = client._get_json(ticker_lookup_url)

        cached_entry = cache.get_stale("GET", ticker_lookup_url)
        assert cached_entry is not None
        updated_payload = dict(cached_entry.payload)
        updated_payload["expires_at"] = 0.0
        cached_entry.cache_path.write_text(json.dumps(updated_payload, separators=(",", ":")), encoding="utf-8")

        second = client._get_json(ticker_lookup_url)
    finally:
        client.close()
        sec_edgar.shared_upstream_cache.clear_local()

    assert first == second
    assert len(observed_headers) == 2
    assert observed_headers[1].get("If-Modified-Since") == last_modified