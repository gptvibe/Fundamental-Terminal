from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

from app.model_engine.engine import _latest_model_runs
from app.model_engine.registry import MODEL_REGISTRY


class _ScalarResult:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return self._rows


class _FakeSession:
    def __init__(self, rows):
        self._rows = rows

    def execute(self, _statement):
        return _ScalarResult(self._rows)


def test_latest_model_runs_prefers_current_calculation_version_over_newer_legacy_row() -> None:
    definition = MODEL_REGISTRY["dcf"]
    legacy_row = SimpleNamespace(
        id=2,
        model_name="dcf",
        model_version=definition.version,
        calculation_version=None,
        result={},
        created_at=datetime(2026, 4, 24, tzinfo=timezone.utc),
    )
    current_row = SimpleNamespace(
        id=1,
        model_name="dcf",
        model_version=definition.version,
        calculation_version=definition.calculation_version,
        result={"calculation_version": definition.calculation_version},
        created_at=datetime(2026, 4, 23, tzinfo=timezone.utc),
    )

    latest = _latest_model_runs(_FakeSession([legacy_row, current_row]), 1, [definition])

    assert latest[(definition.name, definition.version)].id == 1