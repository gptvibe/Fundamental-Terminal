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


def test_warm_company_model_cache_computes_all_registered_models(monkeypatch):
    fake_session = _FakeSession()
    requested: list[tuple[int, list[str], bool]] = []

    class _FakeEngine:
        def __init__(self, session):
            assert session is fake_session

        def compute_models(self, company_id: int, *, model_names: list[str] | None = None, force: bool = False):
            requested.append((company_id, list(model_names or []), force))
            return [SimpleNamespace(cached=False), SimpleNamespace(cached=True)]

    monkeypatch.setattr(prewarm_sp500, "get_engine", lambda: None)
    monkeypatch.setattr(prewarm_sp500, "SessionLocal", _SessionFactory(fake_session))
    monkeypatch.setattr(
        prewarm_sp500,
        "get_company_snapshot",
        lambda session, ticker: SimpleNamespace(company=SimpleNamespace(id=77, ticker=ticker)),
    )
    monkeypatch.setattr(prewarm_sp500, "ModelEngine", _FakeEngine)
    monkeypatch.setattr(prewarm_sp500, "MODEL_REGISTRY", {"ratios": object(), "dcf": object()})

    warmed, total = prewarm_sp500._warm_company_model_cache("GS")

    assert warmed == 1
    assert total == 2
    assert requested == [(77, ["ratios", "dcf"], False)]
    assert fake_session.committed is True


def test_normalize_requested_tickers_deduplicates_and_normalizes():
    assert prewarm_sp500._normalize_requested_tickers(["aapl", "msft,brk.b", "MSFT", " brk.b "]) == [
        "AAPL",
        "MSFT",
        "BRK-B",
    ]


def test_prewarm_main_dry_run_prefers_explicit_tickers(monkeypatch):
    monkeypatch.setattr(
        prewarm_sp500,
        "load_sp500_tickers",
        lambda path: (_ for _ in ()).throw(AssertionError("constituents file should not be loaded")),
    )
    monkeypatch.setattr(
        prewarm_sp500,
        "seed_sp500_companies",
        lambda tickers: (_ for _ in ()).throw(AssertionError("dry-run should not seed")),
    )

    exit_code = prewarm_sp500.prewarm_main(["--dry-run", "--tickers", "AAPL", "msft,brk.b"])

    assert exit_code == 0


def test_refresh_seeded_companies_warms_models_and_charts(monkeypatch):
    calls: list[tuple[str, str]] = []

    class _FakeService:
        def refresh_company(self, *, identifier: str, force: bool, refresh_insider_data: bool, refresh_institutional_data: bool):
            calls.append(("refresh", identifier))
            assert force is True
            assert refresh_insider_data is True
            assert refresh_institutional_data is True
            return SimpleNamespace(status="refreshed", detail="ok")

        def close(self) -> None:
            calls.append(("close", ""))

    monkeypatch.setattr(prewarm_sp500, "EdgarIngestionService", _FakeService)
    monkeypatch.setattr(
        prewarm_sp500,
        "_warm_company_model_cache",
        lambda ticker: calls.append(("models", ticker)) or (1, 2),
    )
    monkeypatch.setattr(
        prewarm_sp500,
        "_warm_company_charts_dashboard",
        lambda ticker: calls.append(("charts", ticker)) or True,
    )

    exit_code = prewarm_sp500._refresh_seeded_companies(["AAPL"], force=True, core_only=False)

    assert exit_code == 0
    assert calls == [("refresh", "AAPL"), ("models", "AAPL"), ("charts", "AAPL"), ("close", "")]


def test_refresh_seeded_companies_warms_charts_in_core_mode(monkeypatch):
    calls: list[tuple[str, str]] = []

    class _FakeService:
        def refresh_company(self, *, identifier: str, force: bool, refresh_insider_data: bool, refresh_institutional_data: bool):
            calls.append(("refresh", identifier))
            assert refresh_insider_data is False
            assert refresh_institutional_data is False
            return SimpleNamespace(status="skipped", detail="fresh")

        def close(self) -> None:
            calls.append(("close", ""))

    monkeypatch.setattr(prewarm_sp500, "EdgarIngestionService", _FakeService)
    monkeypatch.setattr(
        prewarm_sp500,
        "_warm_company_model_cache",
        lambda ticker: (_ for _ in ()).throw(AssertionError("core mode should not warm models")),
    )
    monkeypatch.setattr(
        prewarm_sp500,
        "_warm_company_charts_dashboard",
        lambda ticker: calls.append(("charts", ticker)) or True,
    )

    exit_code = prewarm_sp500._refresh_seeded_companies(["MSFT"], force=False, core_only=True)

    assert exit_code == 0
    assert calls == [("refresh", "MSFT"), ("charts", "MSFT"), ("close", "")]
