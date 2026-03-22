from __future__ import annotations

from datetime import date, datetime, timezone

import pytest

from app.services.risk_free_rate import RiskFreeRateClient, RiskFreeRateSnapshot


class _FakeResponse:
    def __init__(self, text: str, status_code: int = 200):
        self.text = text
        self.status_code = status_code
        self.headers: dict[str, str] = {}

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError("http error")

    def close(self) -> None:
        return None


class _FakeHttp:
    def __init__(self, responses):
        self._responses = list(responses)

    def get(self, _url: str):
        return self._responses.pop(0)

    def close(self) -> None:
        return None


def test_risk_free_rate_reads_latest_treasury_csv_row(tmp_path):
    client = RiskFreeRateClient(cache_file=tmp_path / "risk_free_rate.json")
    client._http = _FakeHttp(
        [
            _FakeResponse(
                "Date,1 Mo,2 Mo,10 Yr\n03/20/2026,4.30,4.28,4.12\n03/21/2026,4.31,4.29,4.15\n"
            )
        ]
    )

    snapshot = client.get_latest_10y_rate()
    assert snapshot.observation_date == date(2026, 3, 21)
    assert snapshot.rate_used == 0.0415
    assert snapshot.tenor == "10y"


def test_risk_free_rate_reuses_cached_value_when_fetch_fails(tmp_path):
    cache_file = tmp_path / "risk_free_rate.json"
    client = RiskFreeRateClient(cache_file=cache_file)
    cached = RiskFreeRateSnapshot(
        source_name="U.S. Treasury Daily Par Yield Curve",
        tenor="10y",
        observation_date=date(2026, 3, 19),
        rate_used=0.04,
        fetched_at=datetime.now(timezone.utc),
    )
    client._write_cache(cached)

    client._http = _FakeHttp([_FakeResponse("", status_code=503), _FakeResponse("", status_code=503), _FakeResponse("", status_code=503)])
    snapshot = client.get_latest_10y_rate()
    assert snapshot.observation_date == cached.observation_date
    assert snapshot.rate_used == cached.rate_used


def test_risk_free_rate_falls_back_to_fiscaldata_proxy_when_csv_unavailable(tmp_path):
    client = RiskFreeRateClient(cache_file=tmp_path / "risk_free_rate.json")
    client._http = _FakeHttp(
        [
            _FakeResponse("", status_code=404),
            _FakeResponse(
                '{"data":[{"record_date":"2026-03-21","security_desc":"Treasury Bonds","avg_interest_rate_amt":"3.377"}]}'
            ),
        ]
    )

    snapshot = client.get_latest_10y_rate()
    assert snapshot.observation_date == date(2026, 3, 21)
    assert snapshot.rate_used == pytest.approx(0.03377)
    assert snapshot.tenor == "10y_proxy"
