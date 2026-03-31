from __future__ import annotations

from app.api.handlers._dispatch import route_handler


healthcheck = route_handler("healthcheck")
cache_metrics = route_handler("cache_metrics")
stream_job_events = route_handler("stream_job_events")
refresh_company = route_handler("refresh_company")


__all__ = ["cache_metrics", "healthcheck", "refresh_company", "stream_job_events"]