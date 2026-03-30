from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

import app.main as main_module
from app.db import get_db_session
from app.main import app


@contextmanager
def _client():
    app.dependency_overrides[get_db_session] = lambda: object()
    try:
        with TestClient(app) as client:
            yield client
    finally:
        app.dependency_overrides.pop(get_db_session, None)


def _serialized_model_evaluation_run() -> dict[str, object]:
    return {
        "id": 7,
        "suite_key": "cache_suite",
        "candidate_label": "candidate",
        "baseline_label": "baseline",
        "status": "completed",
        "completed_at": datetime(2026, 3, 29, tzinfo=timezone.utc),
        "configuration": {"horizon_days": 420, "earnings_horizon_days": 30},
        "summary": {
            "company_count": 2,
            "snapshot_count": 8,
            "model_count": 5,
            "provenance_mode": "historical_cache",
            "latest_as_of": "2025-02-15",
            "latest_future_as_of": "2026-01-31",
        },
        "models": [
            {
                "model_name": "dcf",
                "sample_count": 8,
                "calibration": 0.75,
                "stability": 0.08,
                "mean_absolute_error": 0.11,
                "root_mean_square_error": 0.13,
                "mean_signed_error": 0.02,
                "status": "ok",
                "delta": {
                    "calibration": 0,
                    "stability": 0,
                    "mean_absolute_error": 0,
                    "root_mean_square_error": 0,
                    "mean_signed_error": 0,
                    "sample_count": 0,
                },
            }
        ],
        "deltas_present": False,
    }


def test_runtime_rejects_unauthorized_sources_in_route_payload(monkeypatch) -> None:
    monkeypatch.setattr(
        main_module,
        "get_latest_model_evaluation_run",
        lambda *_args, **_kwargs: SimpleNamespace(
            created_at=datetime(2026, 3, 29, tzinfo=timezone.utc),
            completed_at=datetime(2026, 3, 29, tzinfo=timezone.utc),
        ),
    )
    monkeypatch.setattr(main_module, "serialize_model_evaluation_run", lambda *_args, **_kwargs: _serialized_model_evaluation_run())
    monkeypatch.setattr(
        main_module,
        "_build_provenance_contract",
        lambda *_args, **_kwargs: {
            "provenance": [
                {
                    "source_id": "manual_override",
                    "source_tier": "manual_override",
                    "display_label": "Manual Override",
                    "url": "https://github.com/gptvibe/Fundamental-Terminal",
                    "default_freshness_ttl_seconds": 0,
                    "disclosure_note": "Manually overridden data should be treated as exceptional and disclosed explicitly to users.",
                    "role": "fallback",
                    "as_of": "2025-02-15",
                    "last_refreshed_at": datetime(2026, 3, 29, tzinfo=timezone.utc),
                }
            ],
            "as_of": "2025-02-15",
            "last_refreshed_at": datetime(2026, 3, 29, tzinfo=timezone.utc),
            "source_mix": {
                "source_ids": ["manual_override"],
                "source_tiers": ["manual_override"],
                "primary_source_ids": [],
                "fallback_source_ids": ["manual_override"],
                "official_only": False,
            },
            "confidence_flags": ["manual_override_present"],
        },
    )

    with _client() as client, pytest.raises(RuntimeError, match="unauthorized source ids in payload: manual_override"):
        client.get("/api/model-evaluations/latest")


def test_runtime_rejects_commercial_fallback_payload_in_strict_official_mode(monkeypatch) -> None:
    monkeypatch.setattr(main_module, "settings", SimpleNamespace(strict_official_mode=True))
    monkeypatch.setattr(
        main_module,
        "get_latest_model_evaluation_run",
        lambda *_args, **_kwargs: SimpleNamespace(
            created_at=datetime(2026, 3, 29, tzinfo=timezone.utc),
            completed_at=datetime(2026, 3, 29, tzinfo=timezone.utc),
        ),
    )
    monkeypatch.setattr(main_module, "serialize_model_evaluation_run", lambda *_args, **_kwargs: _serialized_model_evaluation_run())
    monkeypatch.setattr(
        main_module,
        "_build_provenance_contract",
        lambda *_args, **_kwargs: {
            "provenance": [
                {
                    "source_id": "ft_model_evaluation_harness",
                    "source_tier": "derived_from_official",
                    "display_label": "Fundamental Terminal Model Evaluation Harness",
                    "url": "https://github.com/gptvibe/Fundamental-Terminal",
                    "default_freshness_ttl_seconds": 21600,
                    "disclosure_note": "Historical-snapshot backtests computed from cached fundamentals, labeled price history, and persisted model metrics.",
                    "role": "derived",
                    "as_of": "2025-02-15",
                    "last_refreshed_at": datetime(2026, 3, 29, tzinfo=timezone.utc),
                },
                {
                    "source_id": "yahoo_finance",
                    "source_tier": "commercial_fallback",
                    "display_label": "Yahoo Finance",
                    "url": "https://finance.yahoo.com/",
                    "default_freshness_ttl_seconds": 3600,
                    "disclosure_note": "Commercial fallback used only for price, volume, and market-profile context; never for core fundamentals.",
                    "role": "fallback",
                    "as_of": "2026-01-31",
                    "last_refreshed_at": datetime(2026, 3, 29, tzinfo=timezone.utc),
                },
            ],
            "as_of": "2025-02-15",
            "last_refreshed_at": datetime(2026, 3, 29, tzinfo=timezone.utc),
            "source_mix": {
                "source_ids": ["ft_model_evaluation_harness", "yahoo_finance"],
                "source_tiers": ["derived_from_official", "commercial_fallback"],
                "primary_source_ids": [],
                "fallback_source_ids": ["yahoo_finance"],
                "official_only": False,
            },
            "confidence_flags": ["strict_official_mode", "commercial_fallback_present"],
        },
    )

    with _client() as client, pytest.raises(RuntimeError, match="strict official mode payload still exposes fallback sources: yahoo_finance"):
        client.get("/api/model-evaluations/latest")