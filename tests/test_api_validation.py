from __future__ import annotations

from datetime import datetime, timezone

import pytest
from fastapi import HTTPException

from app.api.validation import _normalize_company_models_query_controls, _validated_as_of


def test_validated_as_of_accepts_iso_date() -> None:
    parsed = _validated_as_of("2026-04-13")

    assert parsed == datetime(2026, 4, 13, 23, 59, 59, 999999, tzinfo=timezone.utc)


def test_validated_as_of_rejects_invalid_value() -> None:
    with pytest.raises(HTTPException) as exc:
        _validated_as_of("not-a-date")

    assert exc.value.status_code == 400
    assert exc.value.detail == "as_of must be an ISO-8601 date or timestamp"


def test_normalize_company_models_query_controls_normalizes_inputs() -> None:
    parsed_as_of, expansions, normalized_mode, normalized_as_of = _normalize_company_models_query_controls(
        requested_as_of="2026-04-13",
        expand="formula_details,input_periods, formula_details ",
        dupont_mode="AUTO",
    )

    assert parsed_as_of == datetime(2026, 4, 13, 23, 59, 59, 999999, tzinfo=timezone.utc)
    assert expansions == {"formula_details", "input_periods"}
    assert normalized_mode == "auto"
    assert normalized_as_of == "2026-04-13T23:59:59.999999+00:00"


def test_normalize_company_models_query_controls_rejects_invalid_expand() -> None:
    with pytest.raises(HTTPException) as exc:
        _normalize_company_models_query_controls(
            requested_as_of=None,
            expand="formula_details,unknown",
            dupont_mode=None,
        )

    assert exc.value.status_code == 400
    assert exc.value.detail == "expand must be one of: formula_details, input_periods"