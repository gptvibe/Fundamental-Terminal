from __future__ import annotations

from types import SimpleNamespace

import httpx
import pytest

import app.services.market_data as market_data_module


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
