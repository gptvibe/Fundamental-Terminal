from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app
import app.api.handlers._shared as shared_handlers


def test_cache_metrics_route_exposes_hot_cache_backend_mode(monkeypatch) -> None:
    async def _snapshot_metrics() -> dict[str, object]:
        return {
            "backend": "local",
            "backend_mode": "local_memory_fallback",
            "shared": False,
            "namespace": "ft:hot-cache",
            "backend_details": {
                "configured_backend": "redis",
                "cache_scope": "process-local",
                "redis_configured": True,
                "fallback_active": True,
                "startup_reason": "redis_connect_failed",
                "fallback_events_total": 2,
                "last_fallback_reason": "redis_read_failed",
                "last_fallback_error": "RedisError: timeout",
                "last_fallback_at": "2026-04-13T00:00:00+00:00",
                "cross_instance_reuse": "disabled",
                "status": "fallback",
                "summary": "Redis was configured, but the app is currently using process-local hot-cache fallback.",
                "operational_impact": "Cross-instance cache reuse and shared singleflight coordination are weaker because each backend process keeps its own hot cache.",
                "recommended_checks": [
                    "Verify REDIS_URL.",
                    "Check Redis reachability from this app instance.",
                ],
            },
            "config": {
                "ttl_seconds": 20,
                "stale_ttl_seconds": 120,
                "singleflight_lock_seconds": 30,
                "singleflight_wait_seconds": 15.0,
                "singleflight_poll_seconds": 0.05,
            },
            "overall": {},
            "routes": {},
        }

    monkeypatch.setattr(shared_handlers.shared_hot_response_cache, "snapshot_metrics", _snapshot_metrics)

    client = TestClient(app)
    response = client.get("/api/internal/cache-metrics")

    assert response.status_code == 200
    payload = response.json()
    assert payload["hot_cache_backend"] == "local"
    assert payload["hot_cache_backend_mode"] == "local_memory_fallback"
    assert payload["hot_cache_status"] == "fallback"
    assert payload["hot_cache_scope"] == "process-local"
    assert payload["hot_cache_cross_instance_reuse"] == "disabled"
    assert "process-local hot-cache fallback" in payload["hot_cache_operator_summary"]
    assert payload["hot_cache"]["backend_details"]["cross_instance_reuse"] == "disabled"
    assert payload["hot_cache"]["backend_details"]["startup_reason"] == "redis_connect_failed"
