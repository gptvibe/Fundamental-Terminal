from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from threading import Event
from types import SimpleNamespace

import app.services.shared_upstream_cache as shared_upstream_cache_module


def test_shared_upstream_cache_coalesces_identical_local_fills(monkeypatch) -> None:
    release_fill = Event()
    fill_count = 0

    monkeypatch.setattr(
        shared_upstream_cache_module,
        "settings",
        SimpleNamespace(
            redis_url="",
            hot_response_cache_namespace="ft:test-hot-cache",
            hot_response_cache_singleflight_lock_seconds=5,
            hot_response_cache_singleflight_wait_seconds=1.0,
            hot_response_cache_singleflight_poll_seconds=0.01,
        ),
    )

    cache = shared_upstream_cache_module.SharedUpstreamCache()
    cache._redis = None

    def _fill_payload() -> tuple[dict[str, object], float]:
        nonlocal fill_count
        fill_count += 1
        assert release_fill.wait(timeout=1.0)
        return ({"value": 42}, 60.0)

    with ThreadPoolExecutor(max_workers=2) as executor:
        first_future = executor.submit(cache.fill_json, "market-profile:AAPL", fill=_fill_payload)
        second_future = executor.submit(cache.fill_json, "market-profile:AAPL", fill=_fill_payload)
        release_fill.set()
        first = first_future.result(timeout=2.0)
        second = second_future.result(timeout=2.0)

    assert fill_count == 1
    assert first == second == {"value": 42}