"""Tests for the lightweight route timing store and related middleware/endpoint."""
from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

import app.services.route_timing as route_timing
from app.middleware.route_timing import register_route_timing_middleware


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _reset_store() -> None:
    """Wipe the timing store before and after every test."""
    route_timing.reset()
    yield
    route_timing.reset()


def _make_app_with_middleware(*routes: tuple[str, int, dict[str, str]]) -> FastAPI:
    """Return a minimal FastAPI app with the timing middleware installed.

    Each entry in *routes* is (path, status_code, extra_headers).
    """
    app = FastAPI()
    register_route_timing_middleware(app)

    for path, status_code, headers in routes:
        _path = path  # capture

        @app.get(_path)
        async def _endpoint():  # type: ignore[misc]
            return JSONResponse(content={"ok": True}, status_code=status_code, headers=headers)

    return app


# ---------------------------------------------------------------------------
# Unit tests – store primitives
# ---------------------------------------------------------------------------


class TestRouteTiming:
    def test_record_and_count(self) -> None:
        assert route_timing.record_count() == 0
        route_timing.record(route="/api/test", method="GET", status_code=200, duration_ms=10.0)
        assert route_timing.record_count() == 1

    def test_get_summary_empty_store(self) -> None:
        assert route_timing.get_summary() == []

    def test_get_summary_returns_one_row_per_route_method(self) -> None:
        route_timing.record(route="/api/a", method="GET", status_code=200, duration_ms=20.0)
        route_timing.record(route="/api/a", method="GET", status_code=200, duration_ms=40.0)
        route_timing.record(route="/api/b", method="POST", status_code=201, duration_ms=5.0)

        summary = route_timing.get_summary()
        assert len(summary) == 2
        routes = {s["route"] for s in summary}
        assert routes == {"/api/a", "/api/b"}

    def test_summary_latency_keys(self) -> None:
        for i in range(10):
            route_timing.record(route="/api/x", method="GET", status_code=200, duration_ms=float(i + 1))
        summary = route_timing.get_summary()
        assert len(summary) == 1
        latency = summary[0]["latency_ms"]
        assert set(latency.keys()) >= {"p50", "p95", "p99", "max"}

    def test_summary_p50_p95_p99_monotone(self) -> None:
        for i in range(100):
            route_timing.record(route="/api/mono", method="GET", status_code=200, duration_ms=float(i + 1))
        latency = route_timing.get_summary()[0]["latency_ms"]
        assert latency["p50"] <= latency["p95"] <= latency["p99"] <= latency["max"]

    def test_summary_count_matches_records(self) -> None:
        for _ in range(7):
            route_timing.record(route="/api/count", method="GET", status_code=200, duration_ms=5.0)
        summary = route_timing.get_summary()
        assert summary[0]["count"] == 7

    def test_status_code_aggregation(self) -> None:
        route_timing.record(route="/api/s", method="GET", status_code=200, duration_ms=1.0)
        route_timing.record(route="/api/s", method="GET", status_code=200, duration_ms=2.0)
        route_timing.record(route="/api/s", method="GET", status_code=404, duration_ms=3.0)
        status_codes = route_timing.get_summary()[0]["status_codes"]
        assert status_codes["200"] == 2
        assert status_codes["404"] == 1

    def test_cache_hit_rate_no_data(self) -> None:
        route_timing.record(route="/api/c", method="GET", status_code=200, duration_ms=1.0)
        summary = route_timing.get_summary()
        assert summary[0]["cache_hit_rate"] is None

    def test_cache_hit_rate_calculation(self) -> None:
        route_timing.record(route="/api/c", method="GET", status_code=200, duration_ms=1.0, cache_hit=True)
        route_timing.record(route="/api/c", method="GET", status_code=200, duration_ms=1.0, cache_hit=True)
        route_timing.record(route="/api/c", method="GET", status_code=200, duration_ms=1.0, cache_hit=False)
        summary = route_timing.get_summary()
        rate = summary[0]["cache_hit_rate"]
        assert rate is not None
        assert abs(rate - 2 / 3) < 0.01

    def test_avg_upstream_calls(self) -> None:
        route_timing.record(route="/api/u", method="GET", status_code=200, duration_ms=1.0, upstream_count=2)
        route_timing.record(route="/api/u", method="GET", status_code=200, duration_ms=1.0, upstream_count=4)
        summary = route_timing.get_summary()
        assert summary[0]["avg_upstream_calls"] == pytest.approx(3.0)

    def test_ring_buffer_caps_at_max_records(self) -> None:
        max_records = route_timing._MAX_RECORDS
        for i in range(max_records + 50):
            route_timing.record(route="/api/r", method="GET", status_code=200, duration_ms=float(i))
        assert route_timing.record_count() == max_records

    def test_reset_clears_store_and_returns_count(self) -> None:
        for _ in range(5):
            route_timing.record(route="/api/r", method="GET", status_code=200, duration_ms=1.0)
        cleared = route_timing.reset()
        assert cleared == 5
        assert route_timing.record_count() == 0

    def test_summary_sorted_by_p95_descending(self) -> None:
        # Fast route
        for _ in range(20):
            route_timing.record(route="/api/fast", method="GET", status_code=200, duration_ms=1.0)
        # Slow route
        for _ in range(20):
            route_timing.record(route="/api/slow", method="GET", status_code=200, duration_ms=500.0)
        summary = route_timing.get_summary()
        assert summary[0]["route"] == "/api/slow"
        assert summary[1]["route"] == "/api/fast"


# ---------------------------------------------------------------------------
# Integration tests – middleware captures timing
# ---------------------------------------------------------------------------


class TestRouteTimingMiddleware:
    def test_middleware_records_successful_request(self) -> None:
        app = _make_app_with_middleware(("/ping", 200, {}))
        with TestClient(app, raise_server_exceptions=True) as client:
            resp = client.get("/ping")
        assert resp.status_code == 200
        assert route_timing.record_count() == 1
        summary = route_timing.get_summary()
        assert len(summary) == 1
        assert summary[0]["status_codes"]["200"] == 1

    def test_middleware_skips_health_path(self) -> None:
        app = FastAPI()
        register_route_timing_middleware(app)

        @app.get("/health")
        async def _health():
            return {"ok": True}

        with TestClient(app) as client:
            client.get("/health")
        assert route_timing.record_count() == 0

    def test_middleware_skips_admin_performance_path(self) -> None:
        app = FastAPI()
        register_route_timing_middleware(app)

        @app.get("/api/admin/performance/summary")
        async def _summary():
            return {}

        with TestClient(app) as client:
            client.get("/api/admin/performance/summary")
        assert route_timing.record_count() == 0

    def test_middleware_detects_cache_hit_header(self) -> None:
        app = _make_app_with_middleware(("/cached", 200, {"X-Cache-Status": "hit"}))
        with TestClient(app) as client:
            client.get("/cached")
        summary = route_timing.get_summary()
        assert summary[0]["cache_hit_rate"] == 1.0

    def test_middleware_detects_cache_miss_header(self) -> None:
        app = _make_app_with_middleware(("/cached", 200, {"X-Cache-Status": "miss"}))
        with TestClient(app) as client:
            client.get("/cached")
        summary = route_timing.get_summary()
        assert summary[0]["cache_hit_rate"] == 0.0

    def test_middleware_records_non_200_status(self) -> None:
        app = _make_app_with_middleware(("/gone", 410, {}))
        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.get("/gone")
        assert resp.status_code == 410
        assert route_timing.record_count() == 1
        assert route_timing.get_summary()[0]["status_codes"].get("410") == 1

    def test_multiple_requests_accumulate(self) -> None:
        app = _make_app_with_middleware(("/multi", 200, {}))
        with TestClient(app) as client:
            for _ in range(5):
                client.get("/multi")
        assert route_timing.record_count() == 5
        assert route_timing.get_summary()[0]["count"] == 5


# ---------------------------------------------------------------------------
# Integration tests – admin endpoint
# ---------------------------------------------------------------------------


class TestAdminPerformanceSummaryEndpoint:
    def _client(self) -> TestClient:
        from app.main import app

        return TestClient(app, raise_server_exceptions=True)

    def test_summary_endpoint_returns_200(self) -> None:
        with self._client() as client:
            resp = client.get("/api/admin/performance/summary")
        assert resp.status_code == 200

    def test_summary_endpoint_payload_shape(self) -> None:
        with self._client() as client:
            resp = client.get("/api/admin/performance/summary")
        body = resp.json()
        assert "routes" in body
        assert "record_count" in body
        assert isinstance(body["routes"], list)

    def test_summary_endpoint_reflects_recorded_data(self) -> None:
        route_timing.record(route="/api/test/shape", method="GET", status_code=200, duration_ms=42.0)
        with self._client() as client:
            resp = client.get("/api/admin/performance/summary")
        body = resp.json()
        routes = {r["route"] for r in body["routes"]}
        assert "/api/test/shape" in routes

    def test_summary_endpoint_latency_includes_p99(self) -> None:
        for i in range(20):
            route_timing.record(route="/api/test/p99", method="GET", status_code=200, duration_ms=float(i + 1))
        with self._client() as client:
            resp = client.get("/api/admin/performance/summary")
        body = resp.json()
        target = next((r for r in body["routes"] if r["route"] == "/api/test/p99"), None)
        assert target is not None
        assert "p99" in target["latency_ms"]

    def test_reset_endpoint_clears_store(self) -> None:
        route_timing.record(route="/api/to/clear", method="GET", status_code=200, duration_ms=1.0)
        with self._client() as client:
            resp = client.post("/api/admin/performance/reset")
        assert resp.status_code == 200
        assert resp.json()["cleared"] >= 1
        assert route_timing.record_count() == 0

    def test_summary_not_instrumented_by_itself(self) -> None:
        """Hitting /api/admin/performance/summary must NOT add to the ring buffer."""
        with self._client() as client:
            client.get("/api/admin/performance/summary")
        assert route_timing.record_count() == 0
