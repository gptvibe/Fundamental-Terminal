from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from threading import Event
from types import SimpleNamespace

import httpx
import pytest

import app.services.market_data as market_data_module


def _clear_market_caches() -> None:
    market_data_module.shared_upstream_cache._redis = None
    market_data_module._clear_market_profile_cache()
    market_data_module._clear_market_shared_cache()


def test_market_data_client_skips_yahoo_urls_when_strict_mode_enabled(monkeypatch) -> None:
    observed_urls: list[str] = []

    monkeypatch.setattr(
        market_data_module,
        "settings",
        SimpleNamespace(
            strict_official_mode=True,
            sec_user_agent="test-agent",
            sec_timeout_seconds=10,
        ),
    )

    def _unexpected_request(*args, **kwargs):
        observed_urls.append(str(args[1]))
        raise AssertionError("Yahoo request should not be attempted in strict official mode")

    monkeypatch.setattr(market_data_module, "_request_with_retries", _unexpected_request)

    client = market_data_module.MarketDataClient()
    try:
        history = client.get_price_history("AAPL")
        profile = client.get_market_profile("AAPL")
    finally:
        client.close()

    assert history == []
    assert profile.sector is None
    assert profile.industry is None
    assert observed_urls == []


def test_market_data_client_raises_unavailable_for_yahoo_404(monkeypatch) -> None:
    monkeypatch.setattr(
        market_data_module,
        "settings",
        SimpleNamespace(
            strict_official_mode=False,
            sec_user_agent="test-agent",
            sec_timeout_seconds=10,
            market_max_retries=1,
            market_retry_backoff_seconds=0.01,
        ),
    )

    def _missing_symbol(*_args, **_kwargs):
        request = httpx.Request("GET", "https://query1.finance.yahoo.com/v8/finance/chart/OXYWS")
        response = httpx.Response(404, request=request)
        raise httpx.HTTPStatusError("missing", request=request, response=response)

    monkeypatch.setattr(market_data_module, "_request_with_retries", _missing_symbol)

    client = market_data_module.MarketDataClient()
    try:
        with pytest.raises(market_data_module.MarketDataUnavailableError, match="OXYWS"):
            client.get_price_history("OXYWS")
    finally:
        client.close()


def test_market_data_client_caches_market_profile_within_ttl(monkeypatch) -> None:
    calls: list[tuple[str, dict[str, object]]] = []
    payload = {
        "quotes": [
            {
                "symbol": "AAPL",
                "quoteType": "EQUITY",
                "sectorDisp": "Technology",
                "industryDisp": "Consumer Electronics",
            }
        ]
    }

    monkeypatch.setattr(
        market_data_module,
        "settings",
        SimpleNamespace(
            strict_official_mode=False,
            sec_user_agent="test-agent",
            sec_timeout_seconds=10,
            market_max_retries=1,
            market_retry_backoff_seconds=0.01,
            market_profile_cache_ttl_seconds=3600,
        ),
    )
    monkeypatch.setattr(market_data_module.time, "monotonic", lambda: 100.0)
    _clear_market_caches()

    class _Response:
        def json(self) -> dict[str, object]:
            return payload

    def _profile_request(_client, url: str, *, params: dict[str, object]):
        calls.append((url, params))
        return _Response()

    monkeypatch.setattr(market_data_module, "_request_with_retries", _profile_request)

    client = market_data_module.MarketDataClient()
    try:
        first = client.get_market_profile("AAPL")
        second = client.get_market_profile("AAPL")
    finally:
        client.close()
        _clear_market_caches()

    assert first == market_data_module.MarketProfile(sector="Technology", industry="Consumer Electronics")
    assert second == first
    assert len(calls) == 1
    assert calls[0][1]["q"] == "AAPL"


def test_market_data_client_market_profile_cache_expires(monkeypatch) -> None:
    observed_time = {"value": 100.0}
    request_count = 0

    monkeypatch.setattr(
        market_data_module,
        "settings",
        SimpleNamespace(
            strict_official_mode=False,
            sec_user_agent="test-agent",
            sec_timeout_seconds=10,
            market_max_retries=1,
            market_retry_backoff_seconds=0.01,
            market_profile_cache_ttl_seconds=1,
        ),
    )
    monkeypatch.setattr(market_data_module.time, "monotonic", lambda: observed_time["value"])
    _clear_market_caches()

    class _Response:
        def __init__(self, sector: str) -> None:
            self._sector = sector

        def json(self) -> dict[str, object]:
            return {
                "quotes": [
                    {
                        "symbol": "AAPL",
                        "quoteType": "EQUITY",
                        "sectorDisp": self._sector,
                        "industryDisp": "Consumer Electronics",
                    }
                ]
            }

    def _profile_request(*_args, **_kwargs):
        nonlocal request_count
        request_count += 1
        return _Response(sector=f"Technology-{request_count}")

    monkeypatch.setattr(market_data_module, "_request_with_retries", _profile_request)

    client = market_data_module.MarketDataClient()
    try:
        first = client.get_market_profile("AAPL")
        observed_time["value"] = 102.5
        second = client.get_market_profile("AAPL")
    finally:
        client.close()
        _clear_market_caches()

    assert request_count == 2
    assert first.sector == "Technology-1"
    assert second.sector == "Technology-2"


def test_market_data_client_market_profile_cache_ignores_invalid_entries(monkeypatch) -> None:
    request_count = 0

    monkeypatch.setattr(
        market_data_module,
        "settings",
        SimpleNamespace(
            strict_official_mode=False,
            sec_user_agent="test-agent",
            sec_timeout_seconds=10,
            market_max_retries=1,
            market_retry_backoff_seconds=0.01,
            market_profile_cache_ttl_seconds=3600,
        ),
    )
    monkeypatch.setattr(market_data_module.time, "monotonic", lambda: 100.0)
    _clear_market_caches()
    market_data_module._market_profile_cache["AAPL"] = ("bad-expiry", "bad-profile")  # type: ignore[index]

    class _Response:
        def json(self) -> dict[str, object]:
            return {
                "quotes": [
                    {
                        "symbol": "AAPL",
                        "quoteType": "EQUITY",
                        "sectorDisp": "Technology",
                        "industryDisp": "Consumer Electronics",
                    }
                ]
            }

    def _profile_request(*_args, **_kwargs):
        nonlocal request_count
        request_count += 1
        return _Response()

    monkeypatch.setattr(market_data_module, "_request_with_retries", _profile_request)

    client = market_data_module.MarketDataClient()
    try:
        profile = client.get_market_profile("AAPL")
    finally:
        client.close()
        _clear_market_caches()

    assert request_count == 1
    assert profile == market_data_module.MarketProfile(sector="Technology", industry="Consumer Electronics")


def test_market_data_client_market_profile_cache_does_not_override_strict_mode(monkeypatch) -> None:
    _clear_market_caches()
    market_data_module._market_profile_cache["AAPL"] = (
        999999.0,
        market_data_module.MarketProfile(sector="Technology", industry="Consumer Electronics"),
    )

    monkeypatch.setattr(
        market_data_module,
        "settings",
        SimpleNamespace(
            strict_official_mode=True,
            sec_user_agent="test-agent",
            sec_timeout_seconds=10,
            market_profile_cache_ttl_seconds=3600,
        ),
    )

    def _unexpected_request(*_args, **_kwargs):
        raise AssertionError("Yahoo request should not be attempted in strict official mode")

    monkeypatch.setattr(market_data_module, "_request_with_retries", _unexpected_request)

    client = market_data_module.MarketDataClient()
    try:
        profile = client.get_market_profile("AAPL")
    finally:
        client.close()
        _clear_market_caches()

    assert profile == market_data_module.MarketProfile(sector=None, industry=None)


def test_market_data_client_uses_shared_market_profile_cache_after_local_clear(monkeypatch) -> None:
    request_count = 0

    monkeypatch.setattr(
        market_data_module,
        "settings",
        SimpleNamespace(
            strict_official_mode=False,
            sec_user_agent="test-agent",
            sec_timeout_seconds=10,
            market_max_retries=1,
            market_retry_backoff_seconds=0.01,
            market_profile_cache_ttl_seconds=3600,
            hot_response_cache_namespace="ft:test-hot-cache",
            hot_response_cache_singleflight_lock_seconds=5,
            hot_response_cache_singleflight_wait_seconds=1.0,
            hot_response_cache_singleflight_poll_seconds=0.01,
            redis_url="",
        ),
    )
    monkeypatch.setattr(market_data_module.shared_upstream_cache, "_redis", None)
    monkeypatch.setattr(market_data_module.time, "monotonic", lambda: 100.0)
    _clear_market_caches()

    class _Response:
        headers = {"cache-control": "public, max-age=600"}

        def json(self) -> dict[str, object]:
            return {
                "quotes": [
                    {
                        "symbol": "AAPL",
                        "quoteType": "EQUITY",
                        "sectorDisp": "Technology",
                        "industryDisp": "Consumer Electronics",
                    }
                ]
            }

    def _profile_request(*_args, **_kwargs):
        nonlocal request_count
        request_count += 1
        return _Response()

    monkeypatch.setattr(market_data_module, "_request_with_retries", _profile_request)

    first_client = market_data_module.MarketDataClient()
    second_client = market_data_module.MarketDataClient()
    try:
        first = first_client.get_market_profile("AAPL")
        market_data_module._clear_market_profile_cache()
        second = second_client.get_market_profile("AAPL")
    finally:
        first_client.close()
        second_client.close()
        _clear_market_caches()

    assert request_count == 1
    assert first == second == market_data_module.MarketProfile(
        sector="Technology",
        industry="Consumer Electronics",
    )


def test_market_data_client_uses_shared_price_history_cache_with_bucketed_key(monkeypatch) -> None:
    request_count = 0
    observed_time = iter([1000.0, 1005.0])

    monkeypatch.setattr(
        market_data_module,
        "settings",
        SimpleNamespace(
            strict_official_mode=False,
            sec_user_agent="test-agent",
            sec_timeout_seconds=10,
            market_max_retries=1,
            market_retry_backoff_seconds=0.01,
            market_profile_cache_ttl_seconds=3600,
            hot_response_cache_namespace="ft:test-hot-cache",
            hot_response_cache_singleflight_lock_seconds=5,
            hot_response_cache_singleflight_wait_seconds=1.0,
            hot_response_cache_singleflight_poll_seconds=0.01,
            redis_url="",
        ),
    )
    monkeypatch.setattr(market_data_module.shared_upstream_cache, "_redis", None)
    monkeypatch.setattr(market_data_module.time, "time", lambda: next(observed_time))
    _clear_market_caches()

    class _Response:
        headers = {"cache-control": "public, max-age=10"}

        def json(self) -> dict[str, object]:
            return {
                "chart": {
                    "result": [
                        {
                            "timestamp": [1713657600],
                            "indicators": {
                                "quote": [{"close": [101.5], "volume": [123]}],
                            },
                        }
                    ],
                    "error": None,
                }
            }

    def _history_request(*_args, **_kwargs):
        nonlocal request_count
        request_count += 1
        return _Response()

    monkeypatch.setattr(market_data_module, "_request_with_retries", _history_request)

    client = market_data_module.MarketDataClient()
    try:
        first = client.get_price_history("AAPL")
        second = client.get_price_history("AAPL")
    finally:
        client.close()
        _clear_market_caches()

    assert request_count == 1
    assert first == second == [
        market_data_module.PriceBar(
            trade_date=market_data_module.date(2024, 4, 21),
            close=101.5,
            volume=123,
        )
    ]


def test_market_data_client_coalesces_concurrent_market_profile_fetches(monkeypatch) -> None:
    request_count = 0
    release_request = Event()

    monkeypatch.setattr(
        market_data_module,
        "settings",
        SimpleNamespace(
            strict_official_mode=False,
            sec_user_agent="test-agent",
            sec_timeout_seconds=10,
            market_max_retries=1,
            market_retry_backoff_seconds=0.01,
            market_profile_cache_ttl_seconds=3600,
            hot_response_cache_namespace="ft:test-hot-cache",
            hot_response_cache_singleflight_lock_seconds=5,
            hot_response_cache_singleflight_wait_seconds=1.0,
            hot_response_cache_singleflight_poll_seconds=0.01,
            redis_url="",
        ),
    )
    monkeypatch.setattr(market_data_module.shared_upstream_cache, "_redis", None)
    monkeypatch.setattr(market_data_module.time, "monotonic", lambda: 100.0)
    _clear_market_caches()

    class _Response:
        headers = {"cache-control": "public, max-age=600"}

        def json(self) -> dict[str, object]:
            return {
                "quotes": [
                    {
                        "symbol": "AAPL",
                        "quoteType": "EQUITY",
                        "sectorDisp": "Technology",
                        "industryDisp": "Consumer Electronics",
                    }
                ]
            }

    def _profile_request(*_args, **_kwargs):
        nonlocal request_count
        request_count += 1
        assert release_request.wait(timeout=1.0)
        return _Response()

    monkeypatch.setattr(market_data_module, "_request_with_retries", _profile_request)

    first_client = market_data_module.MarketDataClient()
    second_client = market_data_module.MarketDataClient()
    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            first_future = executor.submit(first_client.get_market_profile, "AAPL")
            second_future = executor.submit(second_client.get_market_profile, "AAPL")
            release_request.set()
            first = first_future.result(timeout=2.0)
            second = second_future.result(timeout=2.0)
    finally:
        first_client.close()
        second_client.close()
        _clear_market_caches()

    assert request_count == 1
    assert first == second == market_data_module.MarketProfile(
        sector="Technology",
        industry="Consumer Electronics",
    )
