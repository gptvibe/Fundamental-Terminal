from __future__ import annotations

import json
import logging
import time
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

import app.api.handlers._shared as shared_handlers
import app.model_engine.engine as engine_module
from app.model_engine.engine import ModelEngine
from app.model_engine.types import CompanyDataset
from app.main import app
from app.observability import (
    begin_request_observation,
    complete_request_observation,
    end_request_observation,
    observe_worker_job,
    record_cache_event,
    record_redis_call,
    record_singleflight_wait,
    record_sql_query,
    record_upstream_request,
    reset_request_observations,
    reset_worker_observations,
    snapshot_request_observations,
)
from app.services.status_stream import JobReporter, StatusBroker


@pytest.fixture(autouse=True)
def _reset_observability_store() -> None:
    reset_request_observations()
    reset_worker_observations()
    yield
    reset_request_observations()
    reset_worker_observations()


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
    fake_definition = SimpleNamespace(
        name="ratios",
        version="test-v1",
        calculation_version="ratios_formula_v1",
        compute=lambda _dataset: {"model_status": "ok"},
    )

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


def test_request_observation_tracks_component_breakdown() -> None:
    metrics, token = begin_request_observation(
        request_id="req-1",
        method="GET",
        path="/api/companies/AAPL/overview",
        query_string="model=dcf",
        request_kind="read",
    )
    try:
        record_sql_query(12.5)
        record_redis_call(3.25)
        record_cache_event("hot_response", "miss")
        record_cache_event("hot_response", "hit")
        record_singleflight_wait(6.0)
        record_upstream_request(20.0, source="sec.gov")
        time.sleep(0.002)
        complete_request_observation(
            metrics,
            route_path="/api/companies/{ticker}/overview",
            status_code=200,
        )
    finally:
        end_request_observation(token)

    snapshot = snapshot_request_observations()
    assert snapshot["record_count"] == 1
    record = snapshot["records"][0]
    assert record["db_query_count"] == 1
    assert record["db_duration_ms"] == pytest.approx(12.5)
    assert record["redis_call_count"] == 1
    assert record["redis_duration_ms"] == pytest.approx(3.25)
    assert record["singleflight_wait_count"] == 1
    assert record["upstream_request_count"] == 1
    assert record["cache_events"]["hot_response"] == {"hit": 1, "miss": 1}

    route_summary = snapshot["route_summaries"][0]
    assert route_summary["route_path"] == "/api/companies/{ticker}/overview"
    assert route_summary["cache_events"] == {"hit": 1, "miss": 1}


def test_observability_endpoint_combines_requests_workers_and_caches(monkeypatch: pytest.MonkeyPatch) -> None:
    metrics, token = begin_request_observation(
        request_id="req-observability",
        method="GET",
        path="/api/companies/AAPL/models",
        query_string="model=dcf",
        request_kind="read",
    )
    try:
        record_sql_query(5.0)
        complete_request_observation(
            metrics,
            route_path="/api/companies/{ticker}/models",
            status_code=200,
        )
    finally:
        end_request_observation(token)

    with observe_worker_job(worker_kind="refresh_queue", job_name="refresh_job", trace_id="job-1", ticker="AAPL"):
        pass

    async def _snapshot_hot_cache() -> dict[str, object]:
        return {
            "backend": "local",
            "backend_mode": "local_memory",
            "shared": False,
            "namespace": "ft:hot-cache",
            "backend_details": {},
            "config": {},
            "overall": {"misses": 1},
            "routes": {},
        }

    monkeypatch.setattr(shared_handlers.shared_hot_response_cache, "snapshot_metrics", _snapshot_hot_cache)
    monkeypatch.setattr(shared_handlers.shared_upstream_cache, "snapshot_metrics", lambda: {"local_hits": 1, "misses": 2})

    client = TestClient(app)
    response = client.get("/api/internal/observability")

    assert response.status_code == 200
    payload = response.json()
    assert payload["enabled"] is True
    assert payload["requests"]["record_count"] == 1
    assert payload["workers"]["record_count"] == 1
    assert payload["caches"]["hot_response"]["overall"] == {"misses": 1}
    assert payload["caches"]["shared_upstream"] == {"local_hits": 1, "misses": 2}