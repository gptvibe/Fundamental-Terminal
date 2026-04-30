from __future__ import annotations

from fastapi.testclient import TestClient

import app.main as main_module
from app.api.handlers import _shared as _shared_handlers
from app.db.session import PoolStatusSnapshot
from app.main import app


def test_pool_status_endpoint_returns_async_pool_metrics(monkeypatch) -> None:
    _snapshot = lambda: PoolStatusSnapshot(
        label="api_async",
        pool_class="ObservedAsyncAdaptedQueuePool",
        pool_size=20,
        max_overflow=40,
        checked_out=17,
        overflow=2,
        current_capacity=22,
        total_capacity=60,
        utilization_ratio=17 / 60,
        queue_wait_time_ms=12.5,
        average_queue_wait_time_ms=8.3,
        max_queue_wait_time_ms=19.2,
        queue_wait_samples=14,
        pool_timeout_seconds=30,
    )
    monkeypatch.setattr(main_module, "get_async_pool_status", _snapshot)
    monkeypatch.setattr(_shared_handlers, "get_async_pool_status", _snapshot)

    client = TestClient(app)
    response = client.get("/api/health/pool-status")

    assert response.status_code == 200
    assert response.json() == {
        "label": "api_async",
        "pool_class": "ObservedAsyncAdaptedQueuePool",
        "pool_size": 20,
        "max_overflow": 40,
        "checked_out": 17,
        "overflow": 2,
        "current_capacity": 22,
        "total_capacity": 60,
        "utilization_ratio": 17 / 60,
        "queue_wait_time_ms": 12.5,
        "average_queue_wait_time_ms": 8.3,
        "max_queue_wait_time_ms": 19.2,
        "queue_wait_samples": 14,
        "pool_timeout_seconds": 30,
    }