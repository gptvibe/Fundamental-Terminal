from __future__ import annotations

import threading
import time
from dataclasses import dataclass

from app.config import settings

try:
    import redis.asyncio as redis_async
    from redis.exceptions import RedisError
except Exception:  # pragma: no cover - optional at runtime
    redis_async = None

    class RedisError(Exception):
        pass


@dataclass(frozen=True, slots=True)
class RateLimitDecision:
    allowed: bool
    limit: int
    remaining: int
    reset_at_epoch: int
    retry_after_seconds: int


class PublicRouteRateLimiter:
    def __init__(self) -> None:
        self._enabled = settings.api_rate_limit_enabled
        self._limit = settings.api_rate_limit_requests
        self._window_seconds = settings.api_rate_limit_window_seconds
        self._namespace = settings.rate_limit_namespace
        self._local_lock = threading.Lock()
        self._local_counts: dict[str, tuple[int, int]] = {}
        self._redis = self._build_redis_client()

    @property
    def enabled(self) -> bool:
        return self._enabled

    async def evaluate(self, identifier: str, *, scope: str = "public-api") -> RateLimitDecision:
        if not self._enabled:
            now = int(time.time())
            return RateLimitDecision(
                allowed=True,
                limit=self._limit,
                remaining=self._limit,
                reset_at_epoch=now + self._window_seconds,
                retry_after_seconds=0,
            )

        now = int(time.time())
        safe_identifier = identifier.strip() or "unknown"
        window_index = now // self._window_seconds
        window_start = window_index * self._window_seconds
        window_end = window_start + self._window_seconds
        redis_key = f"{self._namespace}:{scope}:{safe_identifier}:{window_start}"

        if self._redis is not None:
            try:
                return await self._evaluate_redis(redis_key=redis_key, now=now, window_end=window_end)
            except RedisError:
                pass
            except RuntimeError as exc:
                if "Event loop is closed" not in str(exc):
                    raise

        return await self._evaluate_local(redis_key=redis_key, now=now, window_end=window_end)

    async def _evaluate_redis(self, *, redis_key: str, now: int, window_end: int) -> RateLimitDecision:
        assert self._redis is not None
        pipe = self._redis.pipeline(transaction=True)
        pipe.incr(redis_key)
        pipe.expire(redis_key, self._window_seconds, nx=True)
        pipe.ttl(redis_key)
        count_raw, _expire_raw, ttl_raw = await pipe.execute()

        count = int(count_raw or 0)
        ttl = int(ttl_raw or 0)
        if ttl <= 0:
            ttl = max(window_end - now, 1)
        reset_at = now + ttl
        remaining = max(self._limit - count, 0)
        allowed = count <= self._limit
        retry_after = 0 if allowed else max(reset_at - now, 1)

        return RateLimitDecision(
            allowed=allowed,
            limit=self._limit,
            remaining=remaining,
            reset_at_epoch=reset_at,
            retry_after_seconds=retry_after,
        )

    async def _evaluate_local(self, *, redis_key: str, now: int, window_end: int) -> RateLimitDecision:
        with self._local_lock:
            count, reset_at = self._local_counts.get(redis_key, (0, window_end))
            if reset_at <= now:
                count = 0
                reset_at = window_end
            count += 1
            self._local_counts[redis_key] = (count, reset_at)

            cutoff = now - (self._window_seconds * 3)
            stale_keys = [key for key, (_value, key_reset) in self._local_counts.items() if key_reset < cutoff]
            for key in stale_keys:
                self._local_counts.pop(key, None)

        remaining = max(self._limit - count, 0)
        allowed = count <= self._limit
        retry_after = 0 if allowed else max(reset_at - now, 1)
        return RateLimitDecision(
            allowed=allowed,
            limit=self._limit,
            remaining=remaining,
            reset_at_epoch=reset_at,
            retry_after_seconds=retry_after,
        )

    def _build_redis_client(self):
        if redis_async is None:
            return None
        redis_url = str(settings.redis_url).strip()
        if not redis_url:
            return None
        try:
            return redis_async.Redis.from_url(
                redis_url,
                decode_responses=False,
                socket_timeout=1.0,
                socket_connect_timeout=1.0,
            )
        except Exception:
            return None


public_route_rate_limiter = PublicRouteRateLimiter()
