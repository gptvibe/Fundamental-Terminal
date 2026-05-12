from __future__ import annotations

from app.services.dataset_registry import (
    build_endpoint_freshness_metadata,
    dataset_source_ids_by_runtime_dataset,
    get_dataset_definition,
    get_dataset_freshness_ttl_seconds,
    get_dataset_refresh_policy,
    iter_dataset_definitions,
)


def test_every_registered_dataset_has_positive_ttl() -> None:
    for definition in iter_dataset_definitions():
        assert definition.freshness_ttl_seconds > 0, definition.dataset_key


def test_every_registered_dataset_has_refresh_policy() -> None:
    for definition in iter_dataset_definitions():
        assert definition.refresh_policy in {"request_path_or_worker", "background_worker_only"}
        assert get_dataset_refresh_policy(definition.dataset_key) == definition.refresh_policy


def test_unknown_dataset_keys_fail_safely() -> None:
    assert get_dataset_definition("unknown_dataset") is None
    assert get_dataset_refresh_policy("unknown_dataset") is None
    assert get_dataset_freshness_ttl_seconds("unknown_dataset", default_seconds=1234) == 1234

    mapping = dataset_source_ids_by_runtime_dataset()
    assert "unknown_dataset" not in mapping

    payload = build_endpoint_freshness_metadata(
        dataset_key="unknown_dataset",
        refresh_reason="stale",
        refresh_triggered=True,
        job_id="job-123",
        source="",
    )
    assert payload == {
        "freshness": "stale",
        "source": "none",
        "isStale": True,
        "refreshQueued": True,
        "jobId": "job-123",
    }


def test_endpoint_freshness_metadata_generated_from_registry() -> None:
    payload = build_endpoint_freshness_metadata(
        dataset_key="companyfacts",
        refresh_reason="fresh",
        refresh_triggered=False,
        job_id=None,
        source="",
    )

    assert payload == {
        "freshness": "fresh",
        "source": "sec_companyfacts",
        "isStale": False,
        "refreshQueued": False,
        "jobId": None,
    }
