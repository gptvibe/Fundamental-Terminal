from __future__ import annotations

from types import SimpleNamespace

import app.prewarm_sp500 as prewarm_sp500


class _FakeSession:
    def __init__(self) -> None:
        self.committed = False

    def commit(self) -> None:
        self.committed = True


class _SessionFactory:
    def __init__(self, session: _FakeSession) -> None:
        self.session = session

    def __call__(self):
        return self

    def __enter__(self) -> _FakeSession:
        return self.session

    def __exit__(self, exc_type, exc, tb) -> None:
        return None


def test_warm_company_charts_dashboard_commits_when_payload_is_persisted(monkeypatch):
    fake_session = _FakeSession()
    requested_company_ids: list[int] = []

    monkeypatch.setattr(prewarm_sp500, "get_engine", lambda: None)
    monkeypatch.setattr(prewarm_sp500, "SessionLocal", _SessionFactory(fake_session))
    monkeypatch.setattr(
        prewarm_sp500,
        "get_company_snapshot",
        lambda session, ticker: SimpleNamespace(company=SimpleNamespace(id=14, ticker=ticker)),
    )
    monkeypatch.setattr(
        prewarm_sp500,
        "recompute_and_persist_company_charts_dashboard",
        lambda session, company_id: requested_company_ids.append(company_id) or SimpleNamespace(payload_version="charts-v1"),
    )

    warmed = prewarm_sp500._warm_company_charts_dashboard("NVDA")

    assert warmed is True
    assert requested_company_ids == [14]
    assert fake_session.committed is True


def test_warm_company_charts_dashboard_raises_for_unknown_ticker(monkeypatch):
    fake_session = _FakeSession()

    monkeypatch.setattr(prewarm_sp500, "get_engine", lambda: None)
    monkeypatch.setattr(prewarm_sp500, "SessionLocal", _SessionFactory(fake_session))
    monkeypatch.setattr(prewarm_sp500, "get_company_snapshot", lambda session, ticker: None)

    try:
        prewarm_sp500._warm_company_charts_dashboard("UNKNOWN")
    except ValueError as exc:
        assert "UNKNOWN" in str(exc)
    else:
        raise AssertionError("Expected ValueError for an unknown ticker")

    assert fake_session.committed is False
