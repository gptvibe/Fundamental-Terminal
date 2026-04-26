from __future__ import annotations

import asyncio
import inspect
import json
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from email.utils import formatdate
from hashlib import sha256
from typing import Any, Awaitable, Callable

from app.config import settings
from app.observability import emit_structured_log, observe_redis_call, record_cache_event, record_singleflight_wait

logger = logging.getLogger(__name__)

try:
    import orjson
except Exception:  # pragma: no cover - optional dependency during bootstrap
    orjson = None

try:
    import redis
    import redis.asyncio as redis_async
    from redis.exceptions import RedisError
except Exception:  # pragma: no cover - optional dependency
    redis = None
    redis_async = None

    class RedisError(Exception):
        pass


@dataclass(frozen=True, slots=True)
class HotCacheLookup:
    content: bytes
    etag: str
    last_modified: str | None
    is_fresh: bool


@dataclass(slots=True)
class _InflightFill:
    event: asyncio.Event = field(default_factory=asyncio.Event)
    result: dict[str, Any] | None = None
    error: BaseException | None = None


@dataclass(slots=True)
class _LocalCacheEntry:
    content: bytes
    fresh_until: float
    stale_until: float
    stored_at: float
    route: str
    tags: tuple[str, ...]
    etag: str
    last_modified: str | None


class SharedHotResponseCache:
    def __init__(self) -> None:
        self._namespace = settings.hot_response_cache_namespace
        self._redis_configured = bool(str(settings.redis_url).strip())
        self._local_lock = asyncio.Lock()
        self._local_entries: dict[str, _LocalCacheEntry] = {}
        self._local_tag_index: dict[str, set[str]] = {}
        self._local_metrics: dict[str, dict[str, float]] = {"overall": {}}
        self._local_routes: set[str] = set()
        self._inflight_lock = asyncio.Lock()
        self._inflight: dict[str, _InflightFill] = {}
        self._startup_backend_reason: str | None = None
        self._fallback_events_total = 0
        self._last_fallback_reason: str | None = None
        self._last_fallback_error: str | None = None
        self._last_fallback_at: datetime | None = None
        self._logged_runtime_fallback_operations: set[str] = set()
        self._redis = None
        self._redis_async = None
        self._redis, self._redis_async = self._build_redis_clients()

    @property
    def backend(self) -> str:
        return "redis" if self._redis is not None else "local"

    @property
    def backend_mode(self) -> str:
        if self._redis is None:
            return "local_memory_fallback" if self._redis_configured else "local_memory"
        if self._fallback_events_total > 0:
            return "redis_with_local_fallbacks"
        return "redis"

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

    async def get(self, logical_key: str, *, route: str | None = None) -> HotCacheLookup | None:
        resolved_route = route or _route_from_logical_key(logical_key)
        lookup = await self._read_entry(logical_key)
        if lookup is None:
            await self._record_metric(resolved_route, "requests")
            await self._record_metric(resolved_route, "misses")
            record_cache_event("hot_response", "miss")
            return None

        await self._record_metric(resolved_route, "requests")
        if lookup.is_fresh:
            await self._record_metric(resolved_route, "hit_fresh")
            record_cache_event("hot_response", "hit")
        else:
            await self._record_metric(resolved_route, "hit_stale")
            await self._record_metric(resolved_route, "stale_served")
            record_cache_event("hot_response", "stale")
        return lookup

    async def store(
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
        content = _render_json_bytes(payload)
        etag = _etag_for_json_bytes(content)
        last_modified = _extract_last_modified_header(payload)
        if self._redis is not None and self._redis_async is not None:
            try:
                await self._store_remote_async(
                    logical_key,
                    route=resolved_route,
                    content=content,
                    tags=normalized_tags,
                    stored_at=stored_at,
                    fresh_until=fresh_until,
                    stale_until=stale_until,
                    etag=etag,
                    last_modified=last_modified,
                )
                return
            except RedisError as exc:
                self._note_runtime_fallback(operation="store", exc=exc)
            except RuntimeError as exc:
                if not _is_closed_event_loop_runtime_error(exc):
                    raise
                self._note_runtime_fallback(operation="store", exc=exc)

        await self._store_local(
            logical_key,
            route=resolved_route,
            content=content,
            tags=normalized_tags,
            stored_at=stored_at,
            fresh_until=fresh_until,
            stale_until=stale_until,
            etag=etag,
            last_modified=last_modified,
        )

    async def fill_or_get(
        self,
        logical_key: str,
        *,
        route: str | None = None,
        tags: tuple[str, ...] = (),
        fill: Callable[[], Any],
    ) -> dict[str, Any]:
        resolved_route = route or _route_from_logical_key(logical_key)
        cached = await self._read_entry(logical_key)
        if cached is not None:
            return _decode_lookup_payload(cached)

        leader, inflight = await self._acquire_local_inflight(logical_key)
        if not leader:
            await self._record_metric(resolved_route, "coalesced_waits")
            wait_started_at = time.perf_counter()
            try:
                await asyncio.wait_for(inflight.event.wait(), timeout=settings.hot_response_cache_singleflight_wait_seconds)
            except asyncio.TimeoutError:
                pass
            else:
                if inflight.error is not None:
                    raise inflight.error
                if inflight.result is not None:
                    record_singleflight_wait((time.perf_counter() - wait_started_at) * 1000.0)
                    return inflight.result

            record_singleflight_wait((time.perf_counter() - wait_started_at) * 1000.0)

            cached = await self._read_entry(logical_key)
            if cached is not None:
                return _decode_lookup_payload(cached)

        try:
            result = await self._fill_or_wait_remote(
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
            await self._release_local_inflight(logical_key, inflight)

    async def invalidate(
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

        if self._redis is not None and self._redis_async is not None:
            try:
                deleted = await self._invalidate_remote_async(tags)
            except RedisError as exc:
                self._note_runtime_fallback(operation="invalidate", exc=exc)
                deleted = await self._invalidate_local(tags)
            except RuntimeError as exc:
                if not _is_closed_event_loop_runtime_error(exc):
                    raise
                self._note_runtime_fallback(operation="invalidate", exc=exc)
                deleted = await self._invalidate_local(tags)
        else:
            deleted = await self._invalidate_local(tags)

        await self._record_metric(None, "invalidation_count")
        await self._record_metric(None, "invalidated_keys", deleted)
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

    async def snapshot_metrics(self) -> dict[str, Any]:
        metrics = await self._snapshot_metrics()
        overall = _compute_metric_summary(metrics.get("overall", {}))
        routes = {
            route: _compute_metric_summary(route_metrics)
            for route, route_metrics in metrics.items()
            if route != "overall"
        }
        backend_status = self._backend_status()
        return {
            "backend": self.backend,
            "backend_mode": self.backend_mode,
            "shared": self.is_shared,
            "namespace": self._namespace,
            "backend_details": self._backend_details(backend_status),
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

    async def clear(self) -> None:
        async with self._inflight_lock:
            for inflight in self._inflight.values():
                inflight.event.set()
            self._inflight.clear()

        async with self._local_lock:
            self._local_entries.clear()
            self._local_tag_index.clear()
            self._local_metrics = {"overall": {}}
            self._local_routes.clear()

        if self._redis is not None and self._redis_async is not None:
            try:
                await self._clear_remote_async()
            except RedisError as exc:
                self._note_runtime_fallback(operation="clear", exc=exc)
                try:
                    self._clear_remote()
                except RedisError:
                    pass
            except RuntimeError as exc:
                if not _is_closed_event_loop_runtime_error(exc):
                    raise
                self._note_runtime_fallback(operation="clear", exc=exc)
                try:
                    self._clear_remote()
                except RedisError:
                    pass

    def clear_sync(self) -> None:
        self._run_async_compat(self.clear())

    def get_sync(self, logical_key: str, *, route: str | None = None) -> HotCacheLookup | None:
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            pass
        else:
            return self._get_sync_from_running_loop(logical_key, route=route)
        return self._run_async_compat(self.get(logical_key, route=route))

    def store_sync(
        self,
        logical_key: str,
        *,
        route: str | None = None,
        payload: dict[str, Any],
        tags: tuple[str, ...] = (),
    ) -> None:
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            pass
        else:
            self._store_sync_from_running_loop(logical_key, route=route, payload=payload, tags=tags)
            return
        self._run_async_compat(self.store(logical_key, route=route, payload=payload, tags=tags))

    def invalidate_sync(
        self,
        *,
        ticker: str | None = None,
        dataset: str | None = None,
        schema_version: str | None = None,
        as_of: str | None = None,
    ) -> dict[str, Any]:
        # SQLAlchemy after_commit hooks can fire while FastAPI still has an active event loop.
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            pass
        else:
            return self._invalidate_sync_from_running_loop(
                ticker=ticker,
                dataset=dataset,
                schema_version=schema_version,
                as_of=as_of,
            )
        return self._run_async_compat(
            self.invalidate(
                ticker=ticker,
                dataset=dataset,
                schema_version=schema_version,
                as_of=as_of,
            )
        )

    def _run_async_compat(self, awaitable: Awaitable[Any]) -> Any:
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(awaitable)
        raise RuntimeError("Async shared hot cache APIs must be awaited when called from a running event loop")

    def _get_sync_from_running_loop(
        self,
        logical_key: str,
        *,
        route: str | None = None,
    ) -> HotCacheLookup | None:
        resolved_route = route or _route_from_logical_key(logical_key)
        lookup = self._read_entry_sync(logical_key)
        if lookup is None:
            self._record_metric_sync(resolved_route, "requests")
            self._record_metric_sync(resolved_route, "misses")
            return None

        self._record_metric_sync(resolved_route, "requests")
        if lookup.is_fresh:
            self._record_metric_sync(resolved_route, "hit_fresh")
        else:
            self._record_metric_sync(resolved_route, "hit_stale")
            self._record_metric_sync(resolved_route, "stale_served")
        return lookup

    def _store_sync_from_running_loop(
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
        content = _render_json_bytes(payload)
        etag = _etag_for_json_bytes(content)
        last_modified = _extract_last_modified_header(payload)
        if self._redis is not None:
            try:
                self._store_remote(
                    logical_key,
                    route=resolved_route,
                    content=content,
                    tags=normalized_tags,
                    stored_at=stored_at,
                    fresh_until=fresh_until,
                    stale_until=stale_until,
                    etag=etag,
                    last_modified=last_modified,
                )
                return
            except RedisError as exc:
                self._note_runtime_fallback(operation="store", exc=exc)

        self._store_local_sync(
            logical_key,
            route=resolved_route,
            content=content,
            tags=normalized_tags,
            stored_at=stored_at,
            fresh_until=fresh_until,
            stale_until=stale_until,
            etag=etag,
            last_modified=last_modified,
        )

    def _invalidate_sync_from_running_loop(
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
            except RedisError as exc:
                self._note_runtime_fallback(operation="invalidate", exc=exc)
                deleted = self._invalidate_local_sync(tags)
        else:
            deleted = self._invalidate_local_sync(tags)

        self._record_metric_sync(None, "invalidation_count")
        self._record_metric_sync(None, "invalidated_keys", deleted)
        emit_structured_log(
            logger,
            "shared_hot_cache.invalidate",
            backend=self.backend,
            tags=tags,
            invalidated_keys=deleted,
        )
        return {
            "backend": self.backend,
            "tags": tags,
            "invalidated_keys": deleted,
        }

    def _build_redis_clients(self):
        if redis is None or redis_async is None:
            self._startup_backend_reason = "redis_dependency_missing"
            self._emit_backend_log(
                level=logging.WARNING,
                reason=self._startup_backend_reason,
                error="redis client dependency unavailable",
            )
            return None, None
        try:
            sync_client = redis.Redis.from_url(
                settings.redis_url,
                decode_responses=False,
                socket_timeout=0.5,
                socket_connect_timeout=0.5,
            )
            sync_client.ping()
            async_client = redis_async.Redis.from_url(
                settings.redis_url,
                decode_responses=False,
                socket_timeout=0.5,
                socket_connect_timeout=0.5,
            )
            self._startup_backend_reason = "redis_connected"
            self._emit_backend_log(
                level=logging.INFO,
                reason=self._startup_backend_reason,
            )
            return sync_client, async_client
        except Exception as exc:
            self._startup_backend_reason = "redis_connect_failed"
            self._note_runtime_fallback(
                operation="startup_connect",
                exc=exc,
                log_once=False,
            )
            self._emit_backend_log(
                level=logging.WARNING,
                reason=self._startup_backend_reason,
                error=self._last_fallback_error,
            )
            return None, None

    async def _fill_or_wait_remote(
        self,
        logical_key: str,
        *,
        route: str,
        tags: tuple[str, ...],
        fill: Callable[[], Any],
    ) -> dict[str, Any]:
        if self._redis is None or self._redis_async is None:
            return await self._fill_now(logical_key, route=route, tags=tags, fill=fill)

        try:
            lock_token = await self._acquire_remote_lock_async(logical_key)
            if lock_token is not None:
                try:
                    cached = await self._read_entry(logical_key)
                    if cached is not None:
                        return _decode_lookup_payload(cached)
                    return await self._fill_now(logical_key, route=route, tags=tags, fill=fill)
                finally:
                    try:
                        await self._release_remote_lock_async(logical_key, lock_token)
                    except RuntimeError as exc:
                        if not _is_closed_event_loop_runtime_error(exc):
                            raise
                        self._note_runtime_fallback(operation="singleflight_release", exc=exc)

            deadline = time.monotonic() + settings.hot_response_cache_singleflight_wait_seconds
            while time.monotonic() < deadline:
                cached = await self._read_entry(logical_key)
                if cached is not None:
                    return _decode_lookup_payload(cached)
                if not await self._remote_lock_exists_async(logical_key):
                    lock_token = await self._acquire_remote_lock_async(logical_key)
                    if lock_token is not None:
                        try:
                            cached = await self._read_entry(logical_key)
                            if cached is not None:
                                return _decode_lookup_payload(cached)
                            return await self._fill_now(logical_key, route=route, tags=tags, fill=fill)
                        finally:
                            try:
                                await self._release_remote_lock_async(logical_key, lock_token)
                            except RuntimeError as exc:
                                if not _is_closed_event_loop_runtime_error(exc):
                                    raise
                                self._note_runtime_fallback(operation="singleflight_release", exc=exc)
                await asyncio.sleep(settings.hot_response_cache_singleflight_poll_seconds)
        except RedisError as exc:
            self._note_runtime_fallback(operation="singleflight_coordination", exc=exc)
            return await self._fill_now(logical_key, route=route, tags=tags, fill=fill)
        except RuntimeError as exc:
            if not _is_closed_event_loop_runtime_error(exc):
                raise
            self._note_runtime_fallback(operation="singleflight_coordination", exc=exc)
            return await self._fill_now(logical_key, route=route, tags=tags, fill=fill)

        return await self._fill_now(logical_key, route=route, tags=tags, fill=fill)

    async def _fill_now(
        self,
        logical_key: str,
        *,
        route: str,
        tags: tuple[str, ...],
        fill: Callable[[], Any],
    ) -> dict[str, Any]:
        started = time.perf_counter()
        filled = fill()
        if inspect.isawaitable(filled):
            filled = await filled
        should_store = True
        payload = filled
        if isinstance(filled, tuple) and len(filled) == 2 and isinstance(filled[0], dict) and isinstance(filled[1], bool):
            payload, should_store = filled
        if should_store:
            await self.store(logical_key, route=route, payload=payload, tags=tags)
        elapsed_ms = (time.perf_counter() - started) * 1000.0
        await self._record_metric(route, "fills")
        await self._record_metric(route, "fill_time_ms_total", elapsed_ms)
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

    async def _read_entry(self, logical_key: str) -> HotCacheLookup | None:
        if self._redis is not None and self._redis_async is not None:
            try:
                return await self._read_remote_async(logical_key)
            except RedisError as exc:
                self._note_runtime_fallback(operation="read", exc=exc)
            except RuntimeError as exc:
                if not _is_closed_event_loop_runtime_error(exc):
                    raise
                self._note_runtime_fallback(operation="read", exc=exc)
        return await self._read_local(logical_key)

    def _read_remote(self, logical_key: str) -> HotCacheLookup | None:
        assert self._redis is not None
        with observe_redis_call():
            raw_record = self._redis.hgetall(self._record_key(logical_key))
        if raw_record:
            return self._lookup_from_remote_record_sync(logical_key, raw_record)

        with observe_redis_call():
            raw_entry, raw_meta = self._redis.mget(self._entry_key(logical_key), self._meta_key(logical_key))
        if raw_entry is None and raw_meta is None:
            return None
        return self._lookup_from_legacy_remote_sync(logical_key, raw_entry=raw_entry, raw_meta=raw_meta)

    async def _read_remote_async(self, logical_key: str) -> HotCacheLookup | None:
        assert self._redis_async is not None
        with observe_redis_call():
            raw_record = await self._redis_async.hgetall(self._record_key(logical_key))
        if raw_record:
            return await self._lookup_from_remote_record_async(logical_key, raw_record)

        with observe_redis_call():
            raw_entry, raw_meta = await self._redis_async.mget(self._entry_key(logical_key), self._meta_key(logical_key))
        if raw_entry is None and raw_meta is None:
            return None
        return await self._lookup_from_legacy_remote_async(logical_key, raw_entry=raw_entry, raw_meta=raw_meta)

    async def _read_local(self, logical_key: str) -> HotCacheLookup | None:
        now = time.time()
        async with self._local_lock:
            entry = self._local_entries.get(logical_key)
            if entry is None:
                return None
            if now > entry.stale_until:
                self._delete_local_entry_locked(logical_key, entry.tags)
                return None
            return HotCacheLookup(
                content=entry.content,
                etag=entry.etag,
                last_modified=entry.last_modified,
                is_fresh=now <= entry.fresh_until,
            )

    def _read_entry_sync(self, logical_key: str) -> HotCacheLookup | None:
        if self._redis is not None:
            try:
                return self._read_remote(logical_key)
            except RedisError as exc:
                self._note_runtime_fallback(operation="read", exc=exc)
        return self._read_local_sync(logical_key)

    def _read_local_sync(self, logical_key: str) -> HotCacheLookup | None:
        now = time.time()
        entry = self._local_entries.get(logical_key)
        if entry is None:
            return None
        if now > entry.stale_until:
            self._delete_local_entry_locked(logical_key, entry.tags)
            return None
        return HotCacheLookup(
            content=entry.content,
            etag=entry.etag,
            last_modified=entry.last_modified,
            is_fresh=now <= entry.fresh_until,
        )

    def _store_remote(
        self,
        logical_key: str,
        *,
        route: str,
        content: bytes,
        tags: tuple[str, ...],
        stored_at: float,
        fresh_until: float,
        stale_until: float,
        etag: str,
        last_modified: str | None,
    ) -> None:
        assert self._redis is not None
        previous_tags = self._load_remote_tags(logical_key)
        ttl_seconds = max(int(stale_until - stored_at) + 1, 1)
        pipeline = self._redis.pipeline()
        pipeline.sadd(self._route_registry_key(), route)
        pipeline.hset(
            self._record_key(logical_key),
            mapping=_build_remote_record_mapping(
                content=content,
                fresh_until=fresh_until,
                stale_until=stale_until,
                stored_at=stored_at,
                route=route,
                tags=tags,
                etag=etag,
                last_modified=last_modified,
            ),
        )
        pipeline.expire(self._record_key(logical_key), ttl_seconds)
        pipeline.delete(self._entry_key(logical_key), self._meta_key(logical_key))
        if previous_tags:
            for previous_tag in previous_tags:
                pipeline.srem(self._tag_key(previous_tag), logical_key)
        for tag in tags:
            pipeline.sadd(self._tag_key(tag), logical_key)
        with observe_redis_call():
            pipeline.execute()

    async def _store_remote_async(
        self,
        logical_key: str,
        *,
        route: str,
        content: bytes,
        tags: tuple[str, ...],
        stored_at: float,
        fresh_until: float,
        stale_until: float,
        etag: str,
        last_modified: str | None,
    ) -> None:
        assert self._redis_async is not None
        previous_tags = await self._load_remote_tags_async(logical_key)
        ttl_seconds = max(int(stale_until - stored_at) + 1, 1)
        pipeline = self._redis_async.pipeline()
        pipeline.sadd(self._route_registry_key(), route)
        pipeline.hset(
            self._record_key(logical_key),
            mapping=_build_remote_record_mapping(
                content=content,
                fresh_until=fresh_until,
                stale_until=stale_until,
                stored_at=stored_at,
                route=route,
                tags=tags,
                etag=etag,
                last_modified=last_modified,
            ),
        )
        pipeline.expire(self._record_key(logical_key), ttl_seconds)
        pipeline.delete(self._entry_key(logical_key), self._meta_key(logical_key))
        if previous_tags:
            for previous_tag in previous_tags:
                pipeline.srem(self._tag_key(previous_tag), logical_key)
        for tag in tags:
            pipeline.sadd(self._tag_key(tag), logical_key)
        with observe_redis_call():
            await pipeline.execute()

    async def _store_local(
        self,
        logical_key: str,
        *,
        route: str,
        content: bytes,
        tags: tuple[str, ...],
        stored_at: float,
        fresh_until: float,
        stale_until: float,
        etag: str,
        last_modified: str | None,
    ) -> None:
        async with self._local_lock:
            previous = self._local_entries.get(logical_key)
            if previous is not None:
                self._delete_local_entry_locked(logical_key, previous.tags)
            self._local_entries[logical_key] = _LocalCacheEntry(
                content=content,
                fresh_until=fresh_until,
                stale_until=stale_until,
                stored_at=stored_at,
                route=route,
                tags=tags,
                etag=etag,
                last_modified=last_modified,
            )
            for tag in tags:
                self._local_tag_index.setdefault(tag, set()).add(logical_key)

    def _store_local_sync(
        self,
        logical_key: str,
        *,
        route: str,
        content: bytes,
        tags: tuple[str, ...],
        stored_at: float,
        fresh_until: float,
        stale_until: float,
        etag: str,
        last_modified: str | None,
    ) -> None:
        previous = self._local_entries.get(logical_key)
        if previous is not None:
            self._delete_local_entry_locked(logical_key, previous.tags)
        self._local_entries[logical_key] = _LocalCacheEntry(
            content=content,
            fresh_until=fresh_until,
            stale_until=stale_until,
            stored_at=stored_at,
            route=route,
            tags=tags,
            etag=etag,
            last_modified=last_modified,
        )
        for tag in tags:
            self._local_tag_index.setdefault(tag, set()).add(logical_key)

    def _delete_remote_entry(self, logical_key: str, tags: list[str]) -> None:
        assert self._redis is not None
        pipeline = self._redis.pipeline()
        pipeline.delete(self._record_key(logical_key), self._entry_key(logical_key), self._meta_key(logical_key))
        for tag in tags:
            pipeline.srem(self._tag_key(tag), logical_key)
        pipeline.execute()

    async def _delete_remote_entry_async(self, logical_key: str, tags: list[str]) -> None:
        assert self._redis_async is not None
        pipeline = self._redis_async.pipeline()
        pipeline.delete(self._record_key(logical_key), self._entry_key(logical_key), self._meta_key(logical_key))
        for tag in tags:
            pipeline.srem(self._tag_key(tag), logical_key)
        await pipeline.execute()

    def _delete_local_entry_locked(self, logical_key: str, tags: tuple[str, ...] | list[str]) -> None:
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
        with observe_redis_call():
            logical_keys = self._resolve_remote_invalidation_keys(tags)
        if not logical_keys:
            return 0

        deleted = 0
        pipeline = self._redis.pipeline()
        for logical_key in logical_keys:
            route, entry_tags = self._load_remote_entry_metadata(logical_key)
            if route:
                self._record_metric_sync(route, "invalidation_count")
            pipeline.delete(self._record_key(logical_key), self._entry_key(logical_key), self._meta_key(logical_key))
            for tag in entry_tags:
                pipeline.srem(self._tag_key(tag), logical_key)
            deleted += 1
        with observe_redis_call():
            pipeline.execute()
        return deleted

    async def _invalidate_remote_async(self, tags: tuple[str, ...]) -> int:
        assert self._redis_async is not None
        with observe_redis_call():
            logical_keys = await self._resolve_remote_invalidation_keys_async(tags)
        if not logical_keys:
            return 0

        deleted = 0
        invalidated_routes: list[str] = []
        pipeline = self._redis_async.pipeline()
        for logical_key in logical_keys:
            route, entry_tags = await self._load_remote_entry_metadata_async(logical_key)
            if route:
                invalidated_routes.append(route)
            pipeline.delete(self._record_key(logical_key), self._entry_key(logical_key), self._meta_key(logical_key))
            for tag in entry_tags:
                pipeline.srem(self._tag_key(tag), logical_key)
            deleted += 1
        with observe_redis_call():
            await pipeline.execute()
        for route in invalidated_routes:
            await self._record_metric(route, "invalidation_count")
        return deleted

    async def _invalidate_local(self, tags: tuple[str, ...]) -> int:
        deleted = 0
        invalidated_routes: list[str] = []
        async with self._local_lock:
            logical_keys = self._resolve_local_invalidation_keys_locked(tags)
            if not logical_keys:
                return 0
            for logical_key in logical_keys:
                entry = self._local_entries.get(logical_key)
                if entry is None:
                    continue
                invalidated_routes.append(entry.route)
                self._delete_local_entry_locked(logical_key, entry.tags)
                deleted += 1
        for route in invalidated_routes:
            await self._record_metric(route, "invalidation_count")
        return deleted

    def _invalidate_local_sync(self, tags: tuple[str, ...]) -> int:
        deleted = 0
        invalidated_routes: list[str] = []
        logical_keys = self._resolve_local_invalidation_keys_locked(tags)
        if not logical_keys:
            return 0
        for logical_key in logical_keys:
            entry = self._local_entries.get(logical_key)
            if entry is None:
                continue
            invalidated_routes.append(entry.route)
            self._delete_local_entry_locked(logical_key, entry.tags)
            deleted += 1
        for route in invalidated_routes:
            self._record_metric_sync(route, "invalidation_count")
        return deleted

    def _resolve_remote_invalidation_keys(self, tags: tuple[str, ...]) -> set[str]:
        assert self._redis is not None
        if len(tags) == 1:
            return {_decode_redis_text(value) for value in self._redis.smembers(self._tag_key(tags[0]))}

        tag_keys = [self._tag_key(tag) for tag in tags]
        return {_decode_redis_text(value) for value in self._redis.sinter(tag_keys)}

    async def _resolve_remote_invalidation_keys_async(self, tags: tuple[str, ...]) -> set[str]:
        assert self._redis_async is not None
        if len(tags) == 1:
            return {_decode_redis_text(value) for value in await self._redis_async.smembers(self._tag_key(tags[0]))}

        tag_keys = [self._tag_key(tag) for tag in tags]
        return {_decode_redis_text(value) for value in await self._redis_async.sinter(tag_keys)}

    def _resolve_local_invalidation_keys_locked(self, tags: tuple[str, ...]) -> set[str]:
        if not tags:
            return set()
        members = [set(self._local_tag_index.get(tag, set())) for tag in tags]
        if not members:
            return set()
        keys = members[0]
        for member_set in members[1:]:
            keys &= member_set
        return keys

    async def _record_metric(self, route: str | None, field: str, amount: float = 1.0) -> None:
        if amount == 0:
            return
        normalized_route = route or "overall"
        if self._redis is not None and self._redis_async is not None:
            try:
                await self._record_remote_metric_async(normalized_route, field, amount)
                return
            except RedisError as exc:
                self._note_runtime_fallback(operation="metrics_write", exc=exc)
        await self._record_local_metric(normalized_route, field, amount)

    def _record_metric_sync(self, route: str | None, field: str, amount: float = 1.0) -> None:
        if amount == 0:
            return
        normalized_route = route or "overall"
        if self._redis is not None:
            try:
                self._record_remote_metric(normalized_route, field, amount)
                return
            except RedisError as exc:
                self._note_runtime_fallback(operation="metrics_write", exc=exc)
        overall = self._local_metrics.setdefault("overall", {})
        overall[field] = float(overall.get(field, 0.0)) + amount
        if normalized_route != "overall":
            route_metrics = self._local_metrics.setdefault(normalized_route, {})
            route_metrics[field] = float(route_metrics.get(field, 0.0)) + amount

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

    async def _record_remote_metric_async(self, route: str, field: str, amount: float) -> None:
        assert self._redis_async is not None
        pipeline = self._redis_async.pipeline()
        pipeline.sadd(self._route_registry_key(), route)
        for metrics_key in {self._metrics_key("overall"), self._metrics_key(route)}:
            if float(amount).is_integer():
                pipeline.hincrby(metrics_key, field, int(amount))
            else:
                pipeline.hincrbyfloat(metrics_key, field, amount)
        await pipeline.execute()

    async def _record_local_metric(self, route: str, field: str, amount: float) -> None:
        async with self._local_lock:
            self._local_routes.add(route)
            overall = self._local_metrics.setdefault("overall", {})
            overall[field] = float(overall.get(field, 0.0)) + amount
            if route != "overall":
                route_metrics = self._local_metrics.setdefault(route, {})
                route_metrics[field] = float(route_metrics.get(field, 0.0)) + amount

    async def _snapshot_metrics(self) -> dict[str, dict[str, float]]:
        if self._redis is not None and self._redis_async is not None:
            try:
                return await self._snapshot_remote_metrics_async()
            except RedisError as exc:
                self._note_runtime_fallback(operation="metrics_snapshot", exc=exc)
        async with self._local_lock:
            return {
                route: dict(values)
                for route, values in self._local_metrics.items()
            }

    def _backend_status(self) -> dict[str, Any]:
        if self._redis is not None:
            if self._fallback_events_total > 0:
                return {
                    "status": "degraded",
                    "summary": "Redis is configured as the shared hot-cache backend, but one or more operations fell back to process-local memory.",
                    "operational_impact": "Cross-instance cache reuse and shared singleflight coordination may be partial until Redis recovers.",
                    "recommended_checks": [
                        "Check Redis health and latency.",
                        "Inspect recent shared_hot_cache.local_fallback logs for the failing operation.",
                        "Confirm all app instances still reach the same Redis deployment.",
                    ],
                }
            return {
                "status": "healthy",
                "summary": "Redis-backed shared hot cache is active.",
                "operational_impact": "Cross-instance cache reuse and shared singleflight coordination are enabled.",
                "recommended_checks": [],
            }

        if self._redis_configured:
            return {
                "status": "fallback",
                "summary": "Redis was configured, but the app is currently using process-local hot-cache fallback.",
                "operational_impact": "Cross-instance cache reuse and shared singleflight coordination are weaker because each backend process keeps its own hot cache.",
                "recommended_checks": [
                    "Verify REDIS_URL.",
                    "Check Redis reachability from this app instance.",
                    "Confirm every app instance can reach the same Redis deployment.",
                ],
            }

        return {
            "status": "local_only",
            "summary": "Redis is not configured, so the app is using process-local hot cache only.",
            "operational_impact": "Cross-instance cache reuse and shared singleflight coordination are disabled because cache entries stay within one backend process.",
            "recommended_checks": [
                "Set REDIS_URL to a shared Redis deployment if you want cross-instance hot-cache reuse.",
            ],
        }

    def _backend_details(self, backend_status: dict[str, Any] | None = None) -> dict[str, Any]:
        backend_status = backend_status or self._backend_status()
        fallback_active = self._redis is None and self._redis_configured
        return {
            "configured_backend": "redis" if self._redis_configured else "local",
            "cache_scope": "cross-instance" if self.is_shared else "process-local",
            "redis_configured": self._redis_configured,
            "fallback_active": fallback_active,
            "startup_reason": self._startup_backend_reason,
            "fallback_events_total": self._fallback_events_total,
            "last_fallback_reason": self._last_fallback_reason,
            "last_fallback_error": self._last_fallback_error,
            "last_fallback_at": self._last_fallback_at.isoformat() if self._last_fallback_at is not None else None,
            "cross_instance_reuse": "enabled" if self.is_shared else "disabled",
            "status": backend_status["status"],
            "summary": backend_status["summary"],
            "operational_impact": backend_status["operational_impact"],
            "recommended_checks": list(backend_status["recommended_checks"]),
        }

    def _emit_backend_log(
        self,
        *,
        level: int,
        reason: str,
        error: str | None = None,
    ) -> None:
        backend_status = self._backend_status()
        emit_structured_log(
            logger,
            "shared_hot_cache.backend",
            level=level,
            backend=self.backend,
            backend_mode=self.backend_mode,
            cache_scope="cross-instance" if self.is_shared else "process-local",
            redis_configured=self._redis_configured,
            shared=self.is_shared,
            status=backend_status["status"],
            summary=backend_status["summary"],
            operational_impact=backend_status["operational_impact"],
            recommended_checks=backend_status["recommended_checks"],
            startup_reason=reason,
            fallback_reason=self._last_fallback_reason,
            fallback_events_total=self._fallback_events_total,
            error=error,
        )

    def _note_runtime_fallback(
        self,
        *,
        operation: str,
        exc: BaseException,
        log_once: bool = True,
    ) -> None:
        self._fallback_events_total += 1
        self._last_fallback_reason = f"redis_{operation}_failed"
        self._last_fallback_error = f"{type(exc).__name__}: {exc}"
        self._last_fallback_at = datetime.now(timezone.utc)
        backend_status = self._backend_status()
        if log_once and operation in self._logged_runtime_fallback_operations:
            return
        self._logged_runtime_fallback_operations.add(operation)
        emit_structured_log(
            logger,
            "shared_hot_cache.local_fallback",
            level=logging.WARNING,
            backend=self.backend,
            backend_mode=self.backend_mode,
            cache_scope="process-local-on-fallback",
            operation=operation,
            status=backend_status["status"],
            summary=backend_status["summary"],
            operational_impact=backend_status["operational_impact"],
            recommended_checks=backend_status["recommended_checks"],
            fallback_reason=self._last_fallback_reason,
            error=self._last_fallback_error,
            redis_configured=self._redis_configured,
            shared=self.is_shared,
        )

    def _snapshot_remote_metrics(self) -> dict[str, dict[str, float]]:
        assert self._redis is not None
        routes = {_decode_redis_text(value) for value in self._redis.smembers(self._route_registry_key())}
        routes.add("overall")
        metrics: dict[str, dict[str, float]] = {}
        for route in routes:
            raw_values = self._redis.hgetall(self._metrics_key(route))
            parsed: dict[str, float] = {}
            for key, value in raw_values.items():
                try:
                    parsed[_decode_redis_text(key)] = float(_decode_redis_text(value))
                except (TypeError, ValueError):
                    continue
            metrics[route] = parsed
        return metrics

    async def _snapshot_remote_metrics_async(self) -> dict[str, dict[str, float]]:
        assert self._redis_async is not None
        routes = {_decode_redis_text(value) for value in await self._redis_async.smembers(self._route_registry_key())}
        routes.add("overall")
        metrics: dict[str, dict[str, float]] = {}
        for route in routes:
            raw_values = await self._redis_async.hgetall(self._metrics_key(route))
            parsed: dict[str, float] = {}
            for key, value in raw_values.items():
                try:
                    parsed[_decode_redis_text(key)] = float(_decode_redis_text(value))
                except (TypeError, ValueError):
                    continue
            metrics[route] = parsed
        return metrics

    async def _acquire_local_inflight(self, logical_key: str) -> tuple[bool, _InflightFill]:
        async with self._inflight_lock:
            current = self._inflight.get(logical_key)
            if current is not None:
                return False, current
            current = _InflightFill()
            self._inflight[logical_key] = current
            return True, current

    async def _release_local_inflight(self, logical_key: str, inflight: _InflightFill) -> None:
        async with self._inflight_lock:
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

    async def _acquire_remote_lock_async(self, logical_key: str) -> str | None:
        if self._redis_async is None:
            return None
        token = sha256(f"{logical_key}:{time.time_ns()}".encode("utf-8")).hexdigest()
        if await self._redis_async.set(self._lock_key(logical_key), token, nx=True, ex=settings.hot_response_cache_singleflight_lock_seconds):
            return token
        return None

    def _release_remote_lock(self, logical_key: str, token: str) -> None:
        if self._redis is None:
            return
        lock_key = self._lock_key(logical_key)
        current = self._redis.get(lock_key)
        if _optional_text(current) == token:
            self._redis.delete(lock_key)

    async def _release_remote_lock_async(self, logical_key: str, token: str) -> None:
        if self._redis_async is None:
            return
        lock_key = self._lock_key(logical_key)
        current = await self._redis_async.get(lock_key)
        if _optional_text(current) == token:
            await self._redis_async.delete(lock_key)

    def _remote_lock_exists(self, logical_key: str) -> bool:
        return bool(self._redis and self._redis.exists(self._lock_key(logical_key)))

    async def _remote_lock_exists_async(self, logical_key: str) -> bool:
        return bool(self._redis_async and await self._redis_async.exists(self._lock_key(logical_key)))

    def _clear_remote(self) -> None:
        assert self._redis is not None
        cursor = 0
        keys_to_delete: list[Any] = []
        pattern = f"{self._namespace}:*"
        while True:
            cursor, keys = self._redis.scan(cursor=cursor, match=pattern, count=200)
            keys_to_delete.extend(keys)
            if cursor == 0:
                break
        if keys_to_delete:
            self._redis.delete(*keys_to_delete)

    async def _clear_remote_async(self) -> None:
        assert self._redis_async is not None
        cursor = 0
        keys_to_delete: list[Any] = []
        pattern = f"{self._namespace}:*"
        while True:
            with observe_redis_call():
                cursor, keys = await self._redis_async.scan(cursor=cursor, match=pattern, count=200)
            keys_to_delete.extend(keys)
            if cursor == 0:
                break
        if keys_to_delete:
            with observe_redis_call():
                await self._redis_async.delete(*keys_to_delete)

    # New remote records live in one Redis hash per logical key. We still read and
    # clean up legacy entry/meta keys so existing caches stay valid during rollout.
    def _lookup_from_remote_record_sync(self, logical_key: str, raw_record: dict[Any, Any]) -> HotCacheLookup | None:
        record = _parse_remote_record(raw_record)
        if record is None:
            self._delete_remote_entry(logical_key, [])
            return None
        return self._lookup_from_record(logical_key, record, delete_remote=self._delete_remote_entry)

    async def _lookup_from_remote_record_async(self, logical_key: str, raw_record: dict[Any, Any]) -> HotCacheLookup | None:
        record = _parse_remote_record(raw_record)
        if record is None:
            await self._delete_remote_entry_async(logical_key, [])
            return None
        return await self._lookup_from_record_async(logical_key, record)

    def _lookup_from_legacy_remote_sync(
        self,
        logical_key: str,
        *,
        raw_entry: Any,
        raw_meta: Any,
    ) -> HotCacheLookup | None:
        if raw_entry is None or raw_meta is None:
            self._delete_remote_entry(logical_key, [])
            return None
        try:
            record = _build_record_from_legacy(raw_entry, raw_meta)
        except Exception:
            self._delete_remote_entry(logical_key, [])
            return None
        return self._lookup_from_record(logical_key, record, delete_remote=self._delete_remote_entry)

    async def _lookup_from_legacy_remote_async(
        self,
        logical_key: str,
        *,
        raw_entry: Any,
        raw_meta: Any,
    ) -> HotCacheLookup | None:
        if raw_entry is None or raw_meta is None:
            await self._delete_remote_entry_async(logical_key, [])
            return None
        try:
            record = _build_record_from_legacy(raw_entry, raw_meta)
        except Exception:
            await self._delete_remote_entry_async(logical_key, [])
            return None
        return await self._lookup_from_record_async(logical_key, record)

    def _lookup_from_record(
        self,
        logical_key: str,
        record: dict[str, Any],
        *,
        delete_remote: Callable[[str, list[str]], None],
    ) -> HotCacheLookup | None:
        now = time.time()
        stale_until = float(record.get("stale_until", 0.0) or 0.0)
        tags = _normalize_tags(record.get("tags"))
        if now > stale_until:
            delete_remote(logical_key, tags)
            return None

        fresh_until = float(record.get("fresh_until", 0.0) or 0.0)
        etag = str(record.get("etag") or "")
        content = record.get("content")
        if not etag or not isinstance(content, (bytes, bytearray)):
            delete_remote(logical_key, tags)
            return None

        return HotCacheLookup(
            content=bytes(content),
            etag=etag,
            last_modified=_optional_text(record.get("last_modified")),
            is_fresh=now <= fresh_until,
        )

    async def _lookup_from_record_async(self, logical_key: str, record: dict[str, Any]) -> HotCacheLookup | None:
        now = time.time()
        stale_until = float(record.get("stale_until", 0.0) or 0.0)
        tags = _normalize_tags(record.get("tags"))
        if now > stale_until:
            await self._delete_remote_entry_async(logical_key, tags)
            return None

        fresh_until = float(record.get("fresh_until", 0.0) or 0.0)
        etag = str(record.get("etag") or "")
        content = record.get("content")
        if not etag or not isinstance(content, (bytes, bytearray)):
            await self._delete_remote_entry_async(logical_key, tags)
            return None

        return HotCacheLookup(
            content=bytes(content),
            etag=etag,
            last_modified=_optional_text(record.get("last_modified")),
            is_fresh=now <= fresh_until,
        )

    def _load_remote_tags(self, logical_key: str) -> list[str]:
        assert self._redis is not None
        pipeline = self._redis.pipeline()
        pipeline.hget(self._record_key(logical_key), "tags")
        pipeline.get(self._meta_key(logical_key))
        raw_tags, raw_meta = pipeline.execute()
        tags = _parse_tags_field(raw_tags)
        if tags:
            return tags
        return _parse_legacy_tags(raw_meta)

    async def _load_remote_tags_async(self, logical_key: str) -> list[str]:
        assert self._redis_async is not None
        pipeline = self._redis_async.pipeline()
        pipeline.hget(self._record_key(logical_key), "tags")
        pipeline.get(self._meta_key(logical_key))
        raw_tags, raw_meta = await pipeline.execute()
        tags = _parse_tags_field(raw_tags)
        if tags:
            return tags
        return _parse_legacy_tags(raw_meta)

    def _load_remote_entry_metadata(self, logical_key: str) -> tuple[str, list[str]]:
        assert self._redis is not None
        raw_record = self._redis.hgetall(self._record_key(logical_key))
        if raw_record:
            record = _parse_remote_record(raw_record)
            if record is not None:
                return str(record.get("route") or ""), _normalize_tags(record.get("tags"))

        raw_meta = self._redis.get(self._meta_key(logical_key))
        if raw_meta is None:
            return "", []
        try:
            payload = _json_loads(raw_meta)
        except Exception:
            return "", []
        return str(payload.get("route") or ""), _normalize_tags(payload.get("tags"))

    async def _load_remote_entry_metadata_async(self, logical_key: str) -> tuple[str, list[str]]:
        assert self._redis_async is not None
        raw_record = await self._redis_async.hgetall(self._record_key(logical_key))
        if raw_record:
            record = _parse_remote_record(raw_record)
            if record is not None:
                return str(record.get("route") or ""), _normalize_tags(record.get("tags"))

        raw_meta = await self._redis_async.get(self._meta_key(logical_key))
        if raw_meta is None:
            return "", []
        try:
            payload = _json_loads(raw_meta)
        except Exception:
            return "", []
        return str(payload.get("route") or ""), _normalize_tags(payload.get("tags"))

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

    def _record_key(self, logical_key: str) -> str:
        return f"{self._namespace}:record:{_digest(logical_key)}"

    def _meta_key(self, logical_key: str) -> str:
        return f"{self._namespace}:meta:{_digest(logical_key)}"

    def _lock_key(self, logical_key: str) -> str:
        return f"{self._namespace}:lock:{_digest(logical_key)}"

    def _tag_key(self, tag: str) -> str:
        return f"{self._namespace}:tag:{tag}"

    def _metrics_key(self, route: str) -> str:
        return f"{self._namespace}:metrics:{route}"

    def _route_registry_key(self) -> str:
        return f"{self._namespace}:routes"


def _is_closed_event_loop_runtime_error(exc: RuntimeError) -> bool:
    return "Event loop is closed" in str(exc)


def _build_remote_record_mapping(
    *,
    content: bytes,
    fresh_until: float,
    stale_until: float,
    stored_at: float,
    route: str,
    tags: tuple[str, ...],
    etag: str,
    last_modified: str | None,
) -> dict[str, bytes]:
    return {
        "content": content,
        "fresh_until": str(fresh_until).encode("utf-8"),
        "stale_until": str(stale_until).encode("utf-8"),
        "stored_at": str(stored_at).encode("utf-8"),
        "route": route.encode("utf-8"),
        "tags": _json_dumps_bytes(list(tags), sort_keys=True),
        "etag": etag.encode("utf-8"),
        "last_modified": (last_modified or "").encode("utf-8"),
        "format": b"v2-hash",
    }


def _parse_remote_record(raw_record: dict[Any, Any]) -> dict[str, Any] | None:
    if not raw_record:
        return None
    normalized_record = {_decode_redis_text(key): value for key, value in raw_record.items()}
    content = normalized_record.get("content")
    if not isinstance(content, (bytes, bytearray)):
        return None
    return {
        "content": bytes(content),
        "fresh_until": _float_from_redis_value(normalized_record.get("fresh_until")),
        "stale_until": _float_from_redis_value(normalized_record.get("stale_until")),
        "stored_at": _float_from_redis_value(normalized_record.get("stored_at")),
        "route": _decode_redis_text(normalized_record.get("route", b"")),
        "tags": _parse_tags_field(normalized_record.get("tags")),
        "etag": _decode_redis_text(normalized_record.get("etag", b"")),
        "last_modified": _optional_text(normalized_record.get("last_modified")),
    }


def _build_record_from_legacy(raw_entry: Any, raw_meta: Any) -> dict[str, Any]:
    payload = _json_loads(raw_meta)
    return {
        "content": bytes(raw_entry),
        "fresh_until": float(payload.get("fresh_until", 0.0) or 0.0),
        "stale_until": float(payload.get("stale_until", 0.0) or 0.0),
        "stored_at": float(payload.get("stored_at", 0.0) or 0.0),
        "route": str(payload.get("route") or ""),
        "tags": _normalize_tags(payload.get("tags")),
        "etag": str(payload.get("etag") or ""),
        "last_modified": _optional_text(payload.get("last_modified")),
    }


def _parse_tags_field(raw_tags: Any) -> list[str]:
    if raw_tags in (None, b"", ""):
        return []
    try:
        return _normalize_tags(_json_loads(raw_tags))
    except Exception:
        return []


def _parse_legacy_tags(raw_meta: Any) -> list[str]:
    if raw_meta in (None, b"", ""):
        return []
    try:
        return _normalize_tags(_json_loads(raw_meta).get("tags"))
    except Exception:
        return []


def _normalize_tags(value: Any) -> list[str]:
    if not isinstance(value, (list, tuple, set)):
        return []
    return [str(tag) for tag in value if str(tag)]


def _digest(value: str) -> str:
    return sha256(value.encode("utf-8")).hexdigest()


def _render_json_bytes(payload: Any) -> bytes:
    return _json_dumps_bytes(payload)


def _etag_for_json_bytes(content: bytes) -> str:
    return f'W/"{sha256(content).hexdigest()[:16]}"'


def _extract_last_modified_header(payload: dict[str, Any]) -> str | None:
    candidates: list[datetime] = []

    company = payload.get("company")
    if isinstance(company, dict):
        parsed_company = _parse_cache_timestamp(company.get("last_checked"))
        if parsed_company is not None:
            candidates.append(parsed_company)

    results = payload.get("results")
    if isinstance(results, list):
        for item in results:
            if not isinstance(item, dict):
                continue
            parsed_item = _parse_cache_timestamp(item.get("last_checked"))
            if parsed_item is not None:
                candidates.append(parsed_item)

    if not candidates:
        return None
    latest = max(candidates)
    return formatdate(latest.timestamp(), usegmt=True)


def _parse_cache_timestamp(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = f"{text[:-1]}+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _decode_lookup_payload(lookup: HotCacheLookup) -> dict[str, Any]:
    return _json_loads(lookup.content)


def _json_dumps_bytes(payload: Any, *, sort_keys: bool = False) -> bytes:
    if orjson is not None:
        option = 0
        if sort_keys:
            option |= orjson.OPT_SORT_KEYS
        return orjson.dumps(payload, option=option)
    return json.dumps(payload, ensure_ascii=False, allow_nan=False, separators=(",", ":"), sort_keys=sort_keys).encode("utf-8")


def _json_loads(payload: Any) -> dict[str, Any]:
    if orjson is not None:
        return orjson.loads(payload)
    if isinstance(payload, bytes):
        payload = payload.decode("utf-8")
    return json.loads(payload)


def _decode_redis_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8")
    return str(value)


def _float_from_redis_value(value: Any) -> float:
    try:
        return float(_decode_redis_text(value))
    except (TypeError, ValueError):
        return 0.0


def _optional_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


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
