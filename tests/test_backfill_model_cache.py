from __future__ import annotations

import importlib
import json
import sys
from types import SimpleNamespace

import pytest

import scripts.backfill_model_cache as backfill_model_cache


class _FakeScalarResult:
    def __init__(self, value=1) -> None:
        self._value = value

    def scalar_one(self) -> int:
        return self._value


class _FakeSession:
    def __init__(self, *, preflight_error: Exception | None = None) -> None:
        self.preflight_error = preflight_error
        self.commit_calls = 0
        self.rollback_calls = 0

    def execute(self, _statement):
        if self.preflight_error is not None:
            raise self.preflight_error
        return _FakeScalarResult()

    def commit(self) -> None:
        self.commit_calls += 1

    def rollback(self) -> None:
        self.rollback_calls += 1


class _SessionFactory:
    def __init__(self, session: _FakeSession) -> None:
        self.session = session

    def __call__(self):
        return self

    def __enter__(self) -> _FakeSession:
        return self.session

    def __exit__(self, exc_type, exc, tb) -> bool:
        return False


class _FakeEngine:
    def __init__(self) -> None:
        self.disposed = False

    def dispose(self) -> None:
        self.disposed = True


def _company(company_id: int, ticker: str) -> SimpleNamespace:
    return SimpleNamespace(id=company_id, ticker=ticker)


def _run(
    monkeypatch: pytest.MonkeyPatch,
    *,
    companies: list[SimpleNamespace] | None = None,
    runs_by_company: dict[int, dict[str, list[SimpleNamespace]]] | None = None,
    compute_result=None,
    preflight_error: Exception | None = None,
):
    fake_session = _FakeSession(preflight_error=preflight_error)
    fake_engine = _FakeEngine()

    monkeypatch.setattr(
        backfill_model_cache,
        "_create_session_factory",
        lambda timeout_seconds: (fake_engine, _SessionFactory(fake_session)),
    )
    monkeypatch.setattr(
        backfill_model_cache,
        "_load_companies",
        lambda *_args, **_kwargs: list(companies or []),
    )
    monkeypatch.setattr(
        backfill_model_cache,
        "_load_model_runs_by_company_and_name",
        lambda *_args, **_kwargs: runs_by_company or {},
    )
    if compute_result is None:
        monkeypatch.setattr(
            backfill_model_cache,
            "_compute_model",
            lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("_compute_model should not be called")),
        )
    else:
        monkeypatch.setattr(backfill_model_cache, "_compute_model", compute_result)

    return fake_session, fake_engine


def test_help_does_not_import_heavy_model_engine(monkeypatch: pytest.MonkeyPatch) -> None:
    sys.modules.pop("app.model_engine.engine", None)
    module = importlib.reload(backfill_model_cache)

    with pytest.raises(SystemExit) as exc_info:
        module.main(["--help"])

    assert exc_info.value.code == 0
    assert "app.model_engine.engine" not in sys.modules


def test_db_preflight_success_path(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    fake_session, fake_engine = _run(monkeypatch)

    exit_code = backfill_model_cache.main(["--preflight-only"])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert captured.out == ""
    assert fake_session.commit_calls == 0
    assert fake_engine.disposed is True


def test_db_preflight_failure_exits_cleanly(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    _run(monkeypatch, preflight_error=TimeoutError("statement timeout"))

    exit_code = backfill_model_cache.main(["--preflight-only", "--db-timeout-seconds", "3"])

    captured = capsys.readouterr()
    assert exit_code == 1
    assert json.loads(captured.out.strip()) == {
        "phase": "db_preflight",
        "reason": "statement timeout",
        "status": "failed",
    }


def test_dry_run_does_not_write(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_session, _fake_engine = _run(
        monkeypatch,
        companies=[_company(1, "AAPL")],
        runs_by_company={1: {"dcf": []}},
    )

    exit_code = backfill_model_cache.main(["--dry-run", "--tickers", "AAPL", "--models", "dcf"])

    assert exit_code == 0
    assert fake_session.commit_calls == 0
    assert fake_session.rollback_calls == 0


def test_limit_limits_rows_processed(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    _run(
        monkeypatch,
        companies=[_company(1, "AAPL"), _company(2, "MSFT")],
        runs_by_company={1: {"dcf": [], "reverse_dcf": []}, 2: {"dcf": [], "reverse_dcf": []}},
    )

    exit_code = backfill_model_cache.main(
        ["--dry-run", "--tickers", "AAPL", "MSFT", "--models", "dcf", "reverse_dcf", "--limit", "2"]
    )

    lines = [json.loads(line) for line in capsys.readouterr().out.splitlines() if line.strip()]
    assert exit_code == 0
    assert len(lines) == 2
    assert [(line["ticker"], line["model"]) for line in lines] == [("AAPL", "dcf"), ("AAPL", "reverse_dcf")]


def test_stale_legacy_rows_are_selected_for_recomputation(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    legacy_row = SimpleNamespace(model_name="dcf", calculation_version=None, result={}, created_at=None, id=1)
    _run(
        monkeypatch,
        companies=[_company(1, "AAPL")],
        runs_by_company={1: {"dcf": [legacy_row]}},
    )

    exit_code = backfill_model_cache.main(["--dry-run", "--tickers", "AAPL", "--models", "dcf"])

    payload = json.loads(capsys.readouterr().out.strip())
    assert exit_code == 0
    assert payload["ticker"] == "AAPL"
    assert payload["status"] == "would_recompute"
    assert payload["reason"] == "missing_calculation_version"


def test_current_version_rows_are_skipped(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    current_row = SimpleNamespace(
        model_name="dcf",
        calculation_version="dcf_ev_bridge_v1",
        result={"calculation_version": "dcf_ev_bridge_v1"},
        created_at=None,
        id=1,
    )
    _run(
        monkeypatch,
        companies=[_company(1, "AAPL")],
        runs_by_company={1: {"dcf": [current_row]}},
    )

    exit_code = backfill_model_cache.main(["--dry-run", "--tickers", "AAPL", "--models", "dcf"])

    payload = json.loads(capsys.readouterr().out.strip())
    assert exit_code == 0
    assert payload["status"] == "skipped"
    assert payload["reason"] == "already_current"


def test_newer_version_rows_are_not_overwritten(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    newer_row = SimpleNamespace(
        model_name="dcf",
        calculation_version="dcf_ev_bridge_v2",
        result={"calculation_version": "dcf_ev_bridge_v2"},
        created_at=None,
        id=1,
    )
    _run(
        monkeypatch,
        companies=[_company(1, "AAPL")],
        runs_by_company={1: {"dcf": [newer_row]}},
    )

    exit_code = backfill_model_cache.main(["--dry-run", "--tickers", "AAPL", "--models", "dcf"])

    payload = json.loads(capsys.readouterr().out.strip())
    assert exit_code == 0
    assert payload["status"] == "skipped"
    assert payload["reason"] == "newer_calculation_version:dcf_ev_bridge_v2"


def test_query_failure_produces_structured_error(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    _run(monkeypatch, companies=[_company(1, "AAPL")])
    monkeypatch.setattr(
        backfill_model_cache,
        "_load_model_runs_by_company_and_name",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("query exploded")),
    )

    exit_code = backfill_model_cache.main(["--dry-run", "--tickers", "AAPL", "--models", "dcf"])

    payload = json.loads(capsys.readouterr().out.strip())
    assert exit_code == 1
    assert payload["phase"] == "model_cache_row_query"
    assert payload["status"] == "failed"
    assert payload["reason"] == "query exploded"


def test_real_run_commits_recomputed_rows(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    fake_session, _fake_engine = _run(
        monkeypatch,
        companies=[_company(1, "AAPL")],
        runs_by_company={1: {"dcf": []}},
        compute_result=lambda *_args, **_kwargs: [SimpleNamespace(cached=False)],
    )

    exit_code = backfill_model_cache.main(["--tickers", "AAPL", "--models", "dcf"])

    payload = json.loads(capsys.readouterr().out.strip())
    assert exit_code == 0
    assert fake_session.commit_calls == 1
    assert payload["status"] == "recomputed"
    assert payload["reason"] == "missing_model_row"


def test_run_calculation_version_handles_mocked_objects_without_attribute() -> None:
    mocked_row = SimpleNamespace(result={"calculation_version": "piotroski_ratio_scale_v1"})

    assert backfill_model_cache._run_calculation_version(mocked_row) == "piotroski_ratio_scale_v1"
