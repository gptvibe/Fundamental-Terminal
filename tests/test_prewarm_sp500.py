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