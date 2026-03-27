from __future__ import annotations

from types import SimpleNamespace

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
