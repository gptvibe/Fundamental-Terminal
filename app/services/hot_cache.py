from __future__ import annotations

import json
import logging
import threading
import time
from dataclasses import dataclass, field
from hashlib import sha256
from typing import Any, Callable

from app.config import settings
from app.observability import emit_structured_log

logger = logging.getLogger(__name__)

try:
    import redis
    from redis.exceptions import RedisError
except Exception:  # pragma: no cover - optional dependency
    redis = None

    class RedisError(Exception):
        pass


@dataclass(frozen=True, slots=True)
class HotCacheLookup:
    payload: dict[str, Any]
    is_fresh: bool


@dataclass(slots=True)
class _InflightFill:
    event: threading.Event = field(default_factory=threading.Event)
    result: dict[str, Any] | None = None
    error: BaseException | None = None


@dataclass(slots=True)
class _LocalCacheEntry:
    payload: dict[str, Any]
    fresh_until: float
    stale_until: float
    stored_at: float
    route: str
    tags: tuple[str, ...]


class SharedHotResponseCache:
    def __init__(self) -> None:
        self._namespace = settings.hot_response_cache_namespace
        self._local_lock = threading.Lock()
        self._local_entries: dict[str, _LocalCacheEntry] = {}
        self._local_tag_index: dict[str, set[str]] = {}
        self._local_metrics: dict[str, dict[str, float]] = {"overall": {}}
        self._local_routes: set[str] = set()
        self._inflight_lock = threading.Lock()
        self._inflight: dict[str, _InflightFill] = {}
        self._redis = self._build_redis_client()

    @property
    def backend(self) -> str:
        return "redis" if self._redis is not None else "local"

    @property
    def is_shared(self) -> bool:
        return self._redis is not None

    def build_ticker_tag(self, ticker: str) -> str:
        return f"ticker:{ticker.strip().upper()}"

    def build_dataset_tag(self, dataset: str) -> str:
        return f"dataset:{dataset.strip().lower()}"

    def build_schema_tag(self, schema_version: str) -> str:
        return f"schema:{schema_version.strip()}"

    def build_as_of_tag(self, as_of: str | None) -> str:
        normalized = (as_of or "").strip() or "latest"
        return f"asof:{normalized}"

    def get(self, logical_key: str, *, route: str | None = None) -> HotCacheLookup | None:
        resolved_route = route or _route_from_logical_key(logical_key)
        lookup = self._read_entry(logical_key)
        if lookup is None:
            self._record_metric(resolved_route, "requests")
            self._record_metric(resolved_route, "misses")
            return None

        self._record_metric(resolved_route, "requests")
        if lookup.is_fresh:
            self._record_metric(resolved_route, "hit_fresh")
        else:
            self._record_metric(resolved_route, "hit_stale")
            self._record_metric(resolved_route, "stale_served")
        return lookup

    def store(
        self,
        logical_key: str,
        *,
        route: str | None = None,
        payload: dict[str, Any],
        tags: tuple[str, ...] = (),
    ) -> None:
        resolved_route = route or _route_from_logical_key(logical_key)
        normalized_tags = tuple(sorted({tag for tag in tags if tag}))
        stored_at = time.time()
        fresh_until = stored_at + settings.hot_response_cache_ttl_seconds
        stale_until = fresh_until + settings.hot_response_cache_stale_ttl_seconds
        if self._redis is not None:
            try:
                self._store_remote(
                    logical_key,
                    route=resolved_route,
                    payload=payload,
                    tags=normalized_tags,
                    stored_at=stored_at,
                    fresh_until=fresh_until,
                    stale_until=stale_until,
                )
                return
            except RedisError:
                logger.warning("Shared hot cache store failed; falling back to local cache", exc_info=True)

        self._store_local(
            logical_key,
            route=resolved_route,
            payload=payload,
            tags=normalized_tags,
            stored_at=stored_at,
            fresh_until=fresh_until,
            stale_until=stale_until,
        )

    def fill_or_get(
        self,
        logical_key: str,
        *,
        route: str | None = None,
        tags: tuple[str, ...] = (),
        fill: Callable[[], Any],
    ) -> dict[str, Any]:
        resolved_route = route or _route_from_logical_key(logical_key)
        cached = self._read_entry(logical_key)
        if cached is not None:
            return cached.payload

        leader, inflight = self._acquire_local_inflight(logical_key)
        if not leader:
            self._record_metric(resolved_route, "coalesced_waits")
            waited = inflight.event.wait(timeout=settings.hot_response_cache_singleflight_wait_seconds)
            if waited and inflight.error is not None:
                raise inflight.error
            if waited and inflight.result is not None:
                return inflight.result

            cached = self._read_entry(logical_key)
            if cached is not None:
                return cached.payload

        try:
            result = self._fill_or_wait_remote(
                logical_key,
                route=resolved_route,
                tags=tuple(sorted({tag for tag in tags if tag})),
                fill=fill,
            )
            inflight.result = result
            return result
        except BaseException as exc:
            inflight.error = exc
            raise
        finally:
            inflight.event.set()
            self._release_local_inflight(logical_key, inflight)

    def invalidate(
        self,
        *,
        ticker: str | None = None,
        dataset: str | None = None,
        schema_version: str | None = None,
        as_of: str | None = None,
    ) -> dict[str, Any]:
        tags = self._build_invalidation_tags(
            ticker=ticker,
            dataset=dataset,
            schema_version=schema_version,
            as_of=as_of,
        )
        if not tags:
            raise ValueError("At least one invalidation dimension is required")

        if self._redis is not None:
            try:
                deleted = self._invalidate_remote(tags)
            except RedisError:
                logger.warning("Shared hot cache invalidation failed; falling back to local cache", exc_info=True)
                deleted = self._invalidate_local(tags)
        else:
            deleted = self._invalidate_local(tags)

        self._record_metric(None, "invalidation_count")
        self._record_metric(None, "invalidated_keys", deleted)
        emit_structured_log(
            logger,
            "shared_hot_cache.invalidate",
            backend=self.backend,
            tags=tags,
            invalidated_keys=deleted,
        )
        return {
            "backend": self.backend,
            "shared": self.is_shared,
            "filters": {
                "ticker": ticker,
                "dataset": dataset,
                "schema_version": schema_version,
                "as_of": as_of,
            },
            "tags": tags,
            "invalidated_keys": deleted,
        }

    def snapshot_metrics(self) -> dict[str, Any]:
        metrics = self._snapshot_metrics()
        overall = _compute_metric_summary(metrics.get("overall", {}))
        routes = {
            route: _compute_metric_summary(route_metrics)
            for route, route_metrics in metrics.items()
            if route != "overall"
        }
        return {
            "backend": self.backend,
            "shared": self.is_shared,
            "namespace": self._namespace,
            "config": {
                "ttl_seconds": settings.hot_response_cache_ttl_seconds,
                "stale_ttl_seconds": settings.hot_response_cache_stale_ttl_seconds,
                "singleflight_lock_seconds": settings.hot_response_cache_singleflight_lock_seconds,
                "singleflight_wait_seconds": settings.hot_response_cache_singleflight_wait_seconds,
                "singleflight_poll_seconds": settings.hot_response_cache_singleflight_poll_seconds,
            },
            "overall": overall,
            "routes": routes,
        }

    def clear(self) -> None:
        with self._inflight_lock:
            for inflight in self._inflight.values():
                inflight.event.set()
            self._inflight.clear()

        with self._local_lock:
            self._local_entries.clear()
            self._local_tag_index.clear()
            self._local_metrics = {"overall": {}}
            self._local_routes.clear()

        if self._redis is not None:
            try:
                self._clear_remote()
            except RedisError:
                logger.warning("Unable to clear remote shared hot cache state", exc_info=True)

    def _build_redis_client(self):
        if redis is None:
            return None
        try:
            client = redis.Redis.from_url(
                settings.redis_url,
                decode_responses=True,
                socket_timeout=0.5,
                socket_connect_timeout=0.5,
            )
            client.ping()
            return client
        except Exception:
            logger.warning("Redis unavailable for shared hot cache; using local fallback", exc_info=True)
            return None

    def _fill_or_wait_remote(
        self,
        logical_key: str,
        *,
        route: str,
        tags: tuple[str, ...],
        fill: Callable[[], Any],
    ) -> dict[str, Any]:
        if self._redis is None:
            return self._fill_now(logical_key, route=route, tags=tags, fill=fill)

        lock_token = self._acquire_remote_lock(logical_key)
        if lock_token is not None:
            try:
                cached = self._read_entry(logical_key)
                if cached is not None:
                    return cached.payload
                return self._fill_now(logical_key, route=route, tags=tags, fill=fill)
            finally:
                self._release_remote_lock(logical_key, lock_token)

        deadline = time.monotonic() + settings.hot_response_cache_singleflight_wait_seconds
        while time.monotonic() < deadline:
            cached = self._read_entry(logical_key)
            if cached is not None:
                return cached.payload
            if not self._remote_lock_exists(logical_key):
                lock_token = self._acquire_remote_lock(logical_key)
                if lock_token is not None:
                    try:
                        cached = self._read_entry(logical_key)
                        if cached is not None:
                            return cached.payload
                        return self._fill_now(logical_key, route=route, tags=tags, fill=fill)
                    finally:
                        self._release_remote_lock(logical_key, lock_token)
            time.sleep(settings.hot_response_cache_singleflight_poll_seconds)

        return self._fill_now(logical_key, route=route, tags=tags, fill=fill)

    def _fill_now(
        self,
        logical_key: str,
        *,
        route: str,
        tags: tuple[str, ...],
        fill: Callable[[], Any],
    ) -> dict[str, Any]:
        started = time.perf_counter()
        filled = fill()
        should_store = True
        payload = filled
        if isinstance(filled, tuple) and len(filled) == 2 and isinstance(filled[0], dict) and isinstance(filled[1], bool):
            payload, should_store = filled
        if should_store:
            self.store(logical_key, route=route, payload=payload, tags=tags)
        elapsed_ms = (time.perf_counter() - started) * 1000.0
        self._record_metric(route, "fills")
        self._record_metric(route, "fill_time_ms_total", elapsed_ms)
        emit_structured_log(
            logger,
            "shared_hot_cache.fill",
            backend=self.backend,
            route=route,
            logical_key=logical_key,
            fill_time_ms=round(elapsed_ms, 3),
            tag_count=len(tags),
        )
        return payload

    def _read_entry(self, logical_key: str) -> HotCacheLookup | None:
        if self._redis is not None:
            try:
                return self._read_remote(logical_key)
            except RedisError:
                logger.warning("Shared hot cache read failed; falling back to local cache", exc_info=True)
        return self._read_local(logical_key)

    def _read_remote(self, logical_key: str) -> HotCacheLookup | None:
        assert self._redis is not None
        entry_key = self._entry_key(logical_key)
        raw_entry = self._redis.get(entry_key)
        if raw_entry is None:
            return None

        payload = json.loads(raw_entry)
        now = time.time()
        stale_until = float(payload.get("stale_until", 0.0) or 0.0)
        if now > stale_until:
            self._delete_remote_entry(logical_key, payload.get("tags") or [])
            return None

        fresh_until = float(payload.get("fresh_until", 0.0) or 0.0)
        cached_payload = payload.get("payload")
        if not isinstance(cached_payload, dict):
            self._delete_remote_entry(logical_key, payload.get("tags") or [])
            return None

        return HotCacheLookup(payload=cached_payload, is_fresh=now <= fresh_until)

    def _read_local(self, logical_key: str) -> HotCacheLookup | None:
        now = time.time()
        with self._local_lock:
            entry = self._local_entries.get(logical_key)
            if entry is None:
                return None
            if now > entry.stale_until:
                self._delete_local_entry(logical_key, entry.tags)
                return None
            return HotCacheLookup(payload=entry.payload, is_fresh=now <= entry.fresh_until)

    def _store_remote(
        self,
        logical_key: str,
        *,
        route: str,
        payload: dict[str, Any],
        tags: tuple[str, ...],
        stored_at: float,
        fresh_until: float,
        stale_until: float,
    ) -> None:
        assert self._redis is not None
        entry_key = self._entry_key(logical_key)
        previous = self._redis.get(entry_key)
        previous_tags = []
        if previous:
            try:
                previous_payload = json.loads(previous)
                previous_tags = list(previous_payload.get("tags") or [])
            except Exception:
                previous_tags = []

        record = json.dumps(
            {
                "payload": payload,
                "fresh_until": fresh_until,
                "stale_until": stale_until,
                "stored_at": stored_at,
                "route": route,
                "tags": list(tags),
            },
            separators=(",", ":"),
            sort_keys=True,
        )
        ttl_seconds = max(int(stale_until - stored_at) + 1, 1)
        pipeline = self._redis.pipeline()
        pipeline.sadd(self._route_registry_key(), route)
        pipeline.setex(entry_key, ttl_seconds, record)
        if previous_tags:
            for previous_tag in previous_tags:
                pipeline.srem(self._tag_key(previous_tag), logical_key)
        for tag in tags:
            pipeline.sadd(self._tag_key(tag), logical_key)
        pipeline.execute()

    def _store_local(
        self,
        logical_key: str,
        *,
        route: str,
        payload: dict[str, Any],
        tags: tuple[str, ...],
        stored_at: float,
        fresh_until: float,
        stale_until: float,
    ) -> None:
        with self._local_lock:
            previous = self._local_entries.get(logical_key)
            if previous is not None:
                self._delete_local_entry(logical_key, previous.tags)
            self._local_entries[logical_key] = _LocalCacheEntry(
                payload=payload,
                fresh_until=fresh_until,
                stale_until=stale_until,
                stored_at=stored_at,
                route=route,
                tags=tags,
            )
            for tag in tags:
                self._local_tag_index.setdefault(tag, set()).add(logical_key)

    def _delete_remote_entry(self, logical_key: str, tags: list[str]) -> None:
        assert self._redis is not None
        pipeline = self._redis.pipeline()
        pipeline.delete(self._entry_key(logical_key))
        for tag in tags:
            pipeline.srem(self._tag_key(tag), logical_key)
        pipeline.execute()

    def _delete_local_entry(self, logical_key: str, tags: tuple[str, ...] | list[str]) -> None:
        self._local_entries.pop(logical_key, None)
        for tag in tags:
            members = self._local_tag_index.get(tag)
            if not members:
                continue
            members.discard(logical_key)
            if not members:
                self._local_tag_index.pop(tag, None)

    def _invalidate_remote(self, tags: tuple[str, ...]) -> int:
        assert self._redis is not None
        logical_keys = self._resolve_remote_invalidation_keys(tags)
        if not logical_keys:
            return 0

        deleted = 0
        pipeline = self._redis.pipeline()
        for logical_key in logical_keys:
            raw_entry = self._redis.get(self._entry_key(logical_key))
            entry_tags: list[str] = []
            if raw_entry:
                try:
                    parsed = json.loads(raw_entry)
                    entry_tags = list(parsed.get("tags") or [])
                    route = str(parsed.get("route") or "")
                    if route:
                        self._record_metric(route, "invalidation_count")
                except Exception:
                    entry_tags = []
            pipeline.delete(self._entry_key(logical_key))
            for tag in entry_tags:
                pipeline.srem(self._tag_key(tag), logical_key)
            deleted += 1
        pipeline.execute()
        return deleted

    def _invalidate_local(self, tags: tuple[str, ...]) -> int:
        logical_keys = self._resolve_local_invalidation_keys(tags)
        if not logical_keys:
            return 0

        deleted = 0
        invalidated_routes: list[str] = []
        with self._local_lock:
            for logical_key in logical_keys:
                entry = self._local_entries.get(logical_key)
                if entry is None:
                    continue
                invalidated_routes.append(entry.route)
                self._delete_local_entry(logical_key, entry.tags)
                deleted += 1
        for route in invalidated_routes:
            self._record_metric(route, "invalidation_count")
        return deleted

    def _resolve_remote_invalidation_keys(self, tags: tuple[str, ...]) -> set[str]:
        assert self._redis is not None
        if len(tags) == 1:
            return {str(value) for value in self._redis.smembers(self._tag_key(tags[0]))}

        tag_keys = [self._tag_key(tag) for tag in tags]
        return {str(value) for value in self._redis.sinter(tag_keys)}

    def _resolve_local_invalidation_keys(self, tags: tuple[str, ...]) -> set[str]:
        if not tags:
            return set()
        with self._local_lock:
            members = [set(self._local_tag_index.get(tag, set())) for tag in tags]
        if not members:
            return set()
        keys = members[0]
        for member_set in members[1:]:
            keys &= member_set
        return keys

    def _record_metric(self, route: str | None, field: str, amount: float = 1.0) -> None:
        if amount == 0:
            return
        normalized_route = route or "overall"
        if self._redis is not None:
            try:
                self._record_remote_metric(normalized_route, field, amount)
                return
            except RedisError:
                logger.warning("Shared hot cache metrics write failed; falling back to local metrics", exc_info=True)
        self._record_local_metric(normalized_route, field, amount)

    def _record_remote_metric(self, route: str, field: str, amount: float) -> None:
        assert self._redis is not None
        pipeline = self._redis.pipeline()
        pipeline.sadd(self._route_registry_key(), route)
        for metrics_key in {self._metrics_key("overall"), self._metrics_key(route)}:
            if float(amount).is_integer():
                pipeline.hincrby(metrics_key, field, int(amount))
            else:
                pipeline.hincrbyfloat(metrics_key, field, amount)
        pipeline.execute()

    def _record_local_metric(self, route: str, field: str, amount: float) -> None:
        with self._local_lock:
            self._local_routes.add(route)
            overall = self._local_metrics.setdefault("overall", {})
            overall[field] = float(overall.get(field, 0.0)) + amount
            if route != "overall":
                route_metrics = self._local_metrics.setdefault(route, {})
                route_metrics[field] = float(route_metrics.get(field, 0.0)) + amount

    def _snapshot_metrics(self) -> dict[str, dict[str, float]]:
        if self._redis is not None:
            try:
                return self._snapshot_remote_metrics()
            except RedisError:
                logger.warning("Shared hot cache metrics snapshot failed; falling back to local metrics", exc_info=True)
        with self._local_lock:
            return {
                route: dict(values)
                for route, values in self._local_metrics.items()
            }

    def _snapshot_remote_metrics(self) -> dict[str, dict[str, float]]:
        assert self._redis is not None
        routes = {str(value) for value in self._redis.smembers(self._route_registry_key())}
        routes.add("overall")
        metrics: dict[str, dict[str, float]] = {}
        for route in routes:
            raw_values = self._redis.hgetall(self._metrics_key(route))
            parsed: dict[str, float] = {}
            for key, value in raw_values.items():
                try:
                    parsed[key] = float(value)
                except (TypeError, ValueError):
                    continue
            metrics[route] = parsed
        return metrics

    def _acquire_local_inflight(self, logical_key: str) -> tuple[bool, _InflightFill]:
        with self._inflight_lock:
            current = self._inflight.get(logical_key)
            if current is not None:
                return False, current
            current = _InflightFill()
            self._inflight[logical_key] = current
            return True, current

    def _release_local_inflight(self, logical_key: str, inflight: _InflightFill) -> None:
        with self._inflight_lock:
            current = self._inflight.get(logical_key)
            if current is inflight:
                self._inflight.pop(logical_key, None)

    def _acquire_remote_lock(self, logical_key: str) -> str | None:
        if self._redis is None:
            return None
        token = sha256(f"{logical_key}:{time.time_ns()}".encode("utf-8")).hexdigest()
        if self._redis.set(self._lock_key(logical_key), token, nx=True, ex=settings.hot_response_cache_singleflight_lock_seconds):
            return token
        return None

    def _release_remote_lock(self, logical_key: str, token: str) -> None:
        if self._redis is None:
            return
        lock_key = self._lock_key(logical_key)
        current = self._redis.get(lock_key)
        if current == token:
            self._redis.delete(lock_key)

    def _remote_lock_exists(self, logical_key: str) -> bool:
        return bool(self._redis and self._redis.exists(self._lock_key(logical_key)))

    def _clear_remote(self) -> None:
        assert self._redis is not None
        cursor = 0
        keys_to_delete: list[str] = []
        pattern = f"{self._namespace}:*"
        while True:
            cursor, keys = self._redis.scan(cursor=cursor, match=pattern, count=200)
            keys_to_delete.extend(str(key) for key in keys)
            if cursor == 0:
                break
        if keys_to_delete:
            self._redis.delete(*keys_to_delete)

    def _build_invalidation_tags(
        self,
        *,
        ticker: str | None,
        dataset: str | None,
        schema_version: str | None,
        as_of: str | None,
    ) -> tuple[str, ...]:
        tags: list[str] = []
        if ticker:
            tags.append(self.build_ticker_tag(ticker))
        if dataset:
            tags.append(self.build_dataset_tag(dataset))
        if schema_version:
            tags.append(self.build_schema_tag(schema_version))
        if as_of is not None:
            tags.append(self.build_as_of_tag(as_of))
        return tuple(sorted(tags))

    def _entry_key(self, logical_key: str) -> str:
        return f"{self._namespace}:entry:{_digest(logical_key)}"

    def _lock_key(self, logical_key: str) -> str:
        return f"{self._namespace}:lock:{_digest(logical_key)}"

    def _tag_key(self, tag: str) -> str:
        return f"{self._namespace}:tag:{tag}"

    def _metrics_key(self, route: str) -> str:
        return f"{self._namespace}:metrics:{route}"

    def _route_registry_key(self) -> str:
        return f"{self._namespace}:routes"


def _digest(value: str) -> str:
    return sha256(value.encode("utf-8")).hexdigest()


def _route_from_logical_key(logical_key: str) -> str:
    prefix, _, _rest = logical_key.partition(":")
    return prefix or "hot"


def _compute_metric_summary(metrics: dict[str, float]) -> dict[str, float | int]:
    requests = int(metrics.get("requests", 0.0))
    hit_fresh = int(metrics.get("hit_fresh", 0.0))
    hit_stale = int(metrics.get("hit_stale", 0.0))
    hits = hit_fresh + hit_stale
    misses = int(metrics.get("misses", 0.0))
    fills = int(metrics.get("fills", 0.0))
    fill_time_ms_total = float(metrics.get("fill_time_ms_total", 0.0))
    invalidation_count = int(metrics.get("invalidation_count", 0.0))
    invalidated_keys = int(metrics.get("invalidated_keys", 0.0))
    stale_served = int(metrics.get("stale_served", 0.0))
    coalesced_waits = int(metrics.get("coalesced_waits", 0.0))
    hit_rate = (hits / requests) if requests else 0.0
    avg_fill_time_ms = (fill_time_ms_total / fills) if fills else 0.0
    return {
        "requests": requests,
        "hit_fresh": hit_fresh,
        "hit_stale": hit_stale,
        "hits": hits,
        "misses": misses,
        "hit_rate": round(hit_rate, 6),
        "fills": fills,
        "fill_time_ms_total": round(fill_time_ms_total, 3),
        "avg_fill_time_ms": round(avg_fill_time_ms, 3),
        "stale_served_count": stale_served,
        "invalidation_count": invalidation_count,
        "invalidated_keys": invalidated_keys,
        "coalesced_waits": coalesced_waits,
    }


shared_hot_response_cache = SharedHotResponseCache()