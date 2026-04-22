from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone

from fastapi.testclient import TestClient

from app.main import app
import app.main as main_module
from app.services.status_stream import JobEvent


def test_job_event_stream_route_delivers_terminal_backlog_and_cleans_up(monkeypatch) -> None:
    unsubscribe_calls = 0

    backlog = [
        JobEvent(
            sequence=1,
            timestamp=datetime(2026, 4, 22, tzinfo=timezone.utc),
            ticker="AAPL",
            kind="refresh",
            stage="sync",
            message="Refresh running",
            status="running",
        ),
        JobEvent(
            sequence=2,
            timestamp=datetime(2026, 4, 22, 0, 0, 1, tzinfo=timezone.utc),
            ticker="AAPL",
            kind="refresh",
            stage="complete",
            message="Refresh complete",
            status="completed",
            level="success",
        ),
    ]

    class _FakeBroker:
        async def async_subscribe(self, job_id: str):
            assert job_id == "job-1"

            def unsubscribe() -> None:
                nonlocal unsubscribe_calls
                unsubscribe_calls += 1

            return backlog, asyncio.Queue(), unsubscribe

        def format_sse(self, job_id: str, event: JobEvent) -> str:
            payload = json.dumps(event.to_payload(job_id))
            return f"event: status\ndata: {payload}\n\n"

    monkeypatch.setattr(main_module, "status_broker", _FakeBroker())

    client = TestClient(app)
    with client.stream("GET", "/api/jobs/job-1/events") as response:
        assert response.status_code == 200
        body = "\n".join(response.iter_lines())

    assert '"sequence": 1' in body
    assert '"sequence": 2' in body
    assert '"status": "completed"' in body
    assert body.count("event: status") == 2
    assert unsubscribe_calls == 1
