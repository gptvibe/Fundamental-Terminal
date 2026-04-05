from __future__ import annotations

from app.api.handlers._dispatch import route_handler


healthcheck = route_handler("healthcheck")
cache_metrics = route_handler("cache_metrics")
invalidate_cache_metrics = route_handler("invalidate_cache_metrics")
performance_audit_snapshot = route_handler("performance_audit_snapshot")
reset_performance_audit = route_handler("reset_performance_audit")
stream_job_events = route_handler("stream_job_events")
refresh_company = route_handler("refresh_company")


__all__ = [
    "cache_metrics",
    "healthcheck",
    "invalidate_cache_metrics",
    "performance_audit_snapshot",
    "refresh_company",
    "reset_performance_audit",
    "stream_job_events",
]