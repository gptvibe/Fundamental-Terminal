from __future__ import annotations

import json
import logging
from types import SimpleNamespace

import httpx
import pytest

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


def test_sec_http_cache_put_and_revalidate_use_temp_replace(monkeypatch, tmp_path) -> None:
    original_replace = sec_cache_module.Path.replace
    replace_calls: list[tuple[sec_cache_module.Path, sec_cache_module.Path]] = []
    cache = sec_cache_module.SecHttpCache(tmp_path)
    url = "https://www.sec.gov/files/company_tickers.json"

    monkeypatch.setattr(
        sec_cache_module.Path,
        "replace",
        lambda self, target: replace_calls.append((self, target)) or original_replace(self, target),
    )
    monkeypatch.setattr(
        sec_cache_module,
        "settings",
        SimpleNamespace(
            sec_ticker_cache_ttl_seconds=60,
        ),
    )

    response = httpx.Response(
        200,
        headers={"content-type": "application/json", "etag": '"v1"'},
        content=b'{"ok": true}',
        request=httpx.Request("GET", url),
    )
    cache.put("GET", url, response)

    entry = cache.get_stale("GET", url)
    assert entry is not None
    assert len(replace_calls) == 1
    assert replace_calls[0][0].suffixes[-2:] == [".json", ".tmp"]
    assert replace_calls[0][1].suffix == ".json"
    assert not replace_calls[0][0].exists()
    assert replace_calls[0][1].exists()

    refreshed = httpx.Response(304, headers={"etag": '"v2"'}, request=httpx.Request("GET", url))
    cache.revalidate("GET", url, entry, refreshed)

    assert len(replace_calls) == 2
    assert replace_calls[1][0].suffixes[-2:] == [".json", ".tmp"]
    assert replace_calls[1][1] == entry.cache_path
    assert not replace_calls[1][0].exists()
    assert replace_calls[1][1].exists()


def test_sec_http_cache_hit_miss_logs_are_debug_only(monkeypatch, tmp_path, caplog: pytest.LogCaptureFixture) -> None:
    monkeypatch.setattr(
        sec_cache_module,
        "settings",
        SimpleNamespace(
            sec_ticker_cache_ttl_seconds=60,
        ),
    )
    cache = sec_cache_module.SecHttpCache(tmp_path)
    url = "https://www.sec.gov/files/company_tickers.json"
    response = httpx.Response(
        200,
        headers={"content-type": "application/json"},
        content=b'{"ok": true}',
        request=httpx.Request("GET", url),
    )

    with caplog.at_level(logging.INFO, logger=sec_cache_module.logger.name):
        assert cache.get("GET", url) is None
        cache.put("GET", url, response)
        assert cache.get("GET", url) is not None

    assert not [record for record in caplog.records if "CACHE " in record.message]

    caplog.clear()

    uncached_supported_url = "https://www.sec.gov/api/xbrl/companyfacts/CIK0000320193.json"

    with caplog.at_level(logging.DEBUG, logger=sec_cache_module.logger.name):
        second_cache = sec_cache_module.SecHttpCache(tmp_path)
        assert second_cache.get("GET", url) is not None
        assert second_cache.get("GET", uncached_supported_url) is None

    messages = [record.message for record in caplog.records if "CACHE " in record.message]
    assert any(message == f"CACHE HIT {url}" for message in messages)
    assert any(message == f"CACHE MISS {uncached_supported_url}" for message in messages)
