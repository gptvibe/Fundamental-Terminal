from __future__ import annotations

import json
import logging
from types import SimpleNamespace

import pytest

import app.model_engine.engine as engine_module
from app.model_engine.engine import ModelEngine
from app.model_engine.types import CompanyDataset
from app.services.status_stream import JobReporter, StatusBroker


def test_status_stream_sse_payload_and_logs_include_trace_metadata(caplog: pytest.LogCaptureFixture) -> None:
    broker = StatusBroker(max_jobs=5, max_events_per_job=10)

    with caplog.at_level(logging.INFO, logger="app.services.status_stream"):
        job_id = broker.create_job(ticker="AAPL", kind="refresh")
        broker.publish(job_id, stage="normalize", message="Normalizing XBRL", status="running")

    event = broker._jobs[job_id].events[-1]
    sse_payload = broker.format_sse(job_id, event)
    payload = json.loads(sse_payload.split("data: ", 1)[1])

    assert payload["job_id"] == job_id
    assert payload["trace_id"] == job_id
    assert payload["ticker"] == "AAPL"
    assert payload["kind"] == "refresh"
    assert payload["stage"] == "normalize"

    structured_logs = [json.loads(record.message) for record in caplog.records if record.message.startswith("{")]
    assert any(
        item["event"] == "job.event"
        and item["trace_id"] == job_id
        and item["ticker"] == "AAPL"
        and item["job_kind"] == "refresh"
        for item in structured_logs
    )


def test_model_engine_emits_structured_logs(monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture) -> None:
    company = SimpleNamespace(id=1, ticker="AAPL", name="Apple Inc.", sector="Technology", market_sector="Technology", market_industry="Consumer Electronics")
    dataset = CompanyDataset(
        company_id=1,
        ticker="AAPL",
        name="Apple Inc.",
        sector="Technology",
        market_sector="Technology",
        market_industry="Consumer Electronics",
        market_snapshot=None,
        financials=(SimpleNamespace(period_end="2025-12-31"),),
    )
    fake_definition = SimpleNamespace(name="ratios", version="test-v1", compute=lambda _dataset: {"model_status": "ok"})

    class _FakeSession:
        def __init__(self) -> None:
            self.last_added = None

        def get(self, _model, _company_id):
            return company

        def add(self, model_run) -> None:
            self.last_added = model_run

        def flush(self) -> None:
            if self.last_added is not None:
                self.last_added.id = 321

    fake_session = _FakeSession()
    monkeypatch.setattr(engine_module, "_load_canonical_financials", lambda *_args, **_kwargs: [SimpleNamespace()])
    monkeypatch.setattr(engine_module, "_load_latest_market_snapshot", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(engine_module, "_build_company_dataset", lambda *_args, **_kwargs: dataset)
    monkeypatch.setattr(engine_module, "_select_definitions", lambda _model_names: [fake_definition])
    monkeypatch.setattr(engine_module, "_latest_model_runs", lambda *_args, **_kwargs: {})
    monkeypatch.setattr(engine_module, "_build_input_payload", lambda *_args, **_kwargs: {"signature": "abc"})

    with caplog.at_level(logging.INFO, logger="app.model_engine.engine"):
        results = ModelEngine(fake_session).compute_models(1, model_names=["ratios"], reporter=JobReporter("job-123"))

    assert len(results) == 1
    structured_logs = [json.loads(record.message) for record in caplog.records if record.message.startswith("{")]
    observed_events = {item["event"] for item in structured_logs}
    assert {"model.compute.start", "model.compute.persisted", "model.compute.complete"}.issubset(observed_events)
    assert any(item.get("job_id") == "job-123" and item.get("ticker") == "AAPL" for item in structured_logs)