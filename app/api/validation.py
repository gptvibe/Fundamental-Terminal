from __future__ import annotations

from datetime import date as DateType, datetime, timezone

from fastapi import HTTPException, status


def _normalize_as_of(value: DateType | datetime | str | None) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc).isoformat()
        return value.astimezone(timezone.utc).isoformat()
    if isinstance(value, DateType):
        return value.isoformat()
    text = str(value).strip()
    return text or None


def _parse_as_of(value: DateType | datetime | str | None) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)
    if isinstance(value, DateType):
        return datetime(value.year, value.month, value.day, 23, 59, 59, 999999, tzinfo=timezone.utc)
    text = str(value).strip()
    if not text:
        return None
    if len(text) == 10 and text.count("-") == 2 and "T" not in text and " " not in text:
        try:
            parsed_date = DateType.fromisoformat(text)
        except ValueError:
            return None
        return datetime(parsed_date.year, parsed_date.month, parsed_date.day, 23, 59, 59, 999999, tzinfo=timezone.utc)
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        try:
            parsed_date = DateType.fromisoformat(text)
        except ValueError:
            return None
        return datetime(parsed_date.year, parsed_date.month, parsed_date.day, 23, 59, 59, 999999, tzinfo=timezone.utc)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _validated_as_of(value: str | None) -> datetime | None:
    if value is None:
        return None
    parsed = _parse_as_of(value)
    if parsed is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="as_of must be an ISO-8601 date or timestamp")
    return parsed


def _normalize_company_models_query_controls(
    *,
    requested_as_of: str | None,
    expand: str | None,
    dupont_mode: str | None,
) -> tuple[datetime | None, set[str], str | None, str]:
    parsed_as_of = _validated_as_of(requested_as_of)
    requested_expansions = {item.strip().lower() for item in (expand or "").split(",") if item.strip()}
    allowed_expansions = {"input_periods", "formula_details"}
    if requested_expansions - allowed_expansions:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="expand must be one of: formula_details, input_periods",
        )

    normalized_mode = (dupont_mode or "").lower() or None
    if normalized_mode is not None and normalized_mode not in {"auto", "annual", "ttm"}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="dupont_mode must be one of: auto, annual, ttm")

    normalized_as_of = _normalize_as_of(parsed_as_of) or "latest"
    return parsed_as_of, requested_expansions, normalized_mode, normalized_as_of


def _normalize_company_financials_query_controls(
    *,
    requested_as_of: str | None,
    view: str | None,
) -> tuple[datetime | None, str, str]:
    parsed_as_of = _validated_as_of(requested_as_of)
    normalized_view = (view or "").strip().lower() or "full"
    if normalized_view not in {"full", "core_segments", "core"}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="view must be one of: full, core_segments, core")

    normalized_as_of = _normalize_as_of(parsed_as_of) or "latest"
    return parsed_as_of, normalized_view, normalized_as_of