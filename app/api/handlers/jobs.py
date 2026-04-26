from __future__ import annotations

from app.api.handlers._dispatch import route_handler


healthcheck = route_handler("healthcheck")
readiness_check = route_handler("readiness_check")
cache_metrics = route_handler("cache_metrics")
invalidate_cache_metrics = route_handler("invalidate_cache_metrics")
observability_snapshot = route_handler("observability_snapshot")
performance_audit_snapshot = route_handler("performance_audit_snapshot")
reset_performance_audit = route_handler("reset_performance_audit")
pool_status = route_handler("pool_status")
stream_job_events = route_handler("stream_job_events")
refresh_company = route_handler("refresh_company")


__all__ = [
    "cache_metrics",
    "healthcheck",
    "invalidate_cache_metrics",
    "observability_snapshot",
    "performance_audit_snapshot",
    "pool_status",
    "readiness_check",
    "refresh_company",
    "reset_performance_audit",
    "stream_job_events",
]