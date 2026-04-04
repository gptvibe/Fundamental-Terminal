from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any, Literal

from sqlalchemy.orm import Session

from app.config import settings
from app.services import get_company_financials, get_company_models, get_company_price_history
from app.services.oil_overlay_engine import OilCurveYearPoint, OilOverlayEngineInputs, compute_oil_fair_value_overlay_payload
from app.source_registry import SourceUsage, build_provenance_entries, build_source_mix


SensitivitySourceKind = Literal["manual", "disclosed", "derived_from_official"]


def build_company_oil_scenario_public_payload(
    session: Session,
    company: Any,
    *,
    overlay_payload: dict[str, Any],
    checked_at: datetime,
) -> dict[str, Any]:
    strict_official_mode = bool(settings.strict_official_mode or overlay_payload.get("strict_official_mode"))
    exposure_profile = overlay_payload.get("exposure_profile") if isinstance(overlay_payload.get("exposure_profile"), dict) else {}
    benchmark_series = [item for item in (overlay_payload.get("benchmark_series") or []) if isinstance(item, dict)]
    sensitivity = overlay_payload.get("sensitivity") if isinstance(overlay_payload.get("sensitivity"), dict) else None

    models = get_company_models(session, company.id, model_names=["dcf", "residual_income"])
    financials = get_company_financials(session, company.id)
    price_history = [] if strict_official_mode else get_company_price_history(session, company.id)

    base_fair_value_per_share, model_refreshed_at = _resolve_base_fair_value_per_share(models)
    diluted_shares = _resolve_diluted_shares(financials)
    current_share_price, current_price_as_of = _resolve_current_share_price(price_history)

    selected_benchmark_id = _resolve_selected_benchmark_id(benchmark_series)
    benchmark_options = [_benchmark_option(series) for series in benchmark_series]
    selected_series = next((series for series in benchmark_series if series.get("series_id") == selected_benchmark_id), None)
    official_base_curve = _annualize_curve_series(selected_series)
    user_short_term_curve = _build_default_short_term_curve(official_base_curve)
    long_term_anchor = _resolve_default_long_term_anchor(official_base_curve)
    fade_years = 2

    sensitivity_source_kind, default_sensitivity_value = _resolve_sensitivity_source(sensitivity)
    manual_sensitivity_required = default_sensitivity_value is None
    manual_price_required = current_share_price is None
    manual_price_reason = _manual_price_reason(current_share_price, strict_official_mode=strict_official_mode)
    manual_sensitivity_reason = (
        "No disclosed or derived official oil sensitivity is cached yet."
        if manual_sensitivity_required
        else None
    )

    overlay_outputs = compute_oil_fair_value_overlay_payload(
        OilOverlayEngineInputs(
            base_fair_value_per_share=base_fair_value_per_share,
            official_base_curve=tuple(OilCurveYearPoint(year=point["year"], price=point["price"]) for point in official_base_curve),
            user_edited_short_term_curve=tuple(OilCurveYearPoint(year=point["year"], price=point["price"]) for point in user_short_term_curve),
            user_long_term_anchor=long_term_anchor,
            fade_years=fade_years,
            annual_after_tax_oil_sensitivity=default_sensitivity_value,
            diluted_shares=diluted_shares,
            current_share_price=current_share_price,
            oil_support_status=_support_status(exposure_profile.get("oil_support_status")),
            confidence_flags=tuple(str(flag) for flag in (overlay_payload.get("confidence_flags") or []) if isinstance(flag, str)),
        )
    )

    provenance_entries = _merge_provenance_entries(
        overlay_payload.get("provenance") or [],
        model_refreshed_at=model_refreshed_at,
        current_price_as_of=current_price_as_of,
        checked_at=checked_at,
        include_market_price=current_share_price is not None and not strict_official_mode,
    )
    source_mix = build_source_mix(provenance_entries)

    diagnostics = dict(overlay_payload.get("diagnostics") or {})
    missing_field_flags = set(str(flag) for flag in diagnostics.get("missing_field_flags") or [] if isinstance(flag, str))
    if not official_base_curve:
        missing_field_flags.add("official_oil_curve_missing")
    if base_fair_value_per_share is None:
        missing_field_flags.add("base_fair_value_missing")
    if diluted_shares in (None, 0):
        missing_field_flags.add("diluted_shares_missing")
    if manual_sensitivity_required:
        missing_field_flags.add("annual_after_tax_sensitivity_manual_required")
    diagnostics["missing_field_flags"] = sorted(missing_field_flags)

    confidence_flags = set(str(flag) for flag in (overlay_payload.get("confidence_flags") or []) if isinstance(flag, str))
    confidence_flags.update(str(flag) for flag in (overlay_outputs.get("confidence_flags") or []) if isinstance(flag, str))
    if manual_sensitivity_required:
        confidence_flags.add("oil_sensitivity_manual_required")
    if manual_price_required:
        confidence_flags.add("oil_price_manual_required")
    if strict_official_mode:
        confidence_flags.add("strict_official_mode")
    if any(str(entry.get("source_tier") or "") == "commercial_fallback" for entry in provenance_entries):
        confidence_flags.add("commercial_fallback_present")

    return {
        "status": str(overlay_payload.get("status") or exposure_profile.get("oil_support_status") or "insufficient_data"),
        "fetched_at": overlay_payload.get("fetched_at") or checked_at.isoformat(),
        "as_of": overlay_payload.get("as_of") or checked_at.date().isoformat(),
        "last_refreshed_at": overlay_payload.get("last_refreshed_at") or checked_at.isoformat(),
        "strict_official_mode": strict_official_mode,
        "exposure_profile": exposure_profile,
        "eligibility": {
            "eligible": _support_status(exposure_profile.get("oil_support_status")) in {"supported", "partial"},
            "status": _support_status(exposure_profile.get("oil_support_status")),
            "oil_exposure_type": str(exposure_profile.get("oil_exposure_type") or "non_oil"),
            "reasons": [
                str(reason)
                for reason in (exposure_profile.get("oil_support_reasons") or [])
                if isinstance(reason, str)
            ],
        },
        "benchmark_series": benchmark_series,
        "official_base_curve": {
            "benchmark_id": selected_benchmark_id,
            "label": str(selected_series.get("label") or "") if isinstance(selected_series, dict) else None,
            "units": str(selected_series.get("units") or "usd_per_barrel") if isinstance(selected_series, dict) else "usd_per_barrel",
            "points": official_base_curve,
            "available_benchmarks": benchmark_options,
        },
        "user_editable_defaults": {
            "benchmark_id": selected_benchmark_id,
            "benchmark_options": benchmark_options,
            "short_term_curve": user_short_term_curve,
            "long_term_anchor": long_term_anchor,
            "fade_years": fade_years,
            "annual_after_tax_sensitivity": default_sensitivity_value,
            "base_fair_value_per_share": base_fair_value_per_share,
            "diluted_shares": diluted_shares,
            "current_share_price": current_share_price,
            "current_share_price_source": "cached_market_price" if current_share_price is not None else "manual_required",
        },
        "scenarios": [item for item in (overlay_payload.get("scenarios") or []) if isinstance(item, dict)],
        "sensitivity": sensitivity,
        "sensitivity_source": {
            "kind": sensitivity_source_kind,
            "value": default_sensitivity_value,
            "metric_basis": None if sensitivity is None else sensitivity.get("metric_basis"),
            "status": None if sensitivity is None else sensitivity.get("status"),
            "confidence_flags": [] if sensitivity is None else [
                str(flag) for flag in (sensitivity.get("confidence_flags") or []) if isinstance(flag, str)
            ],
        },
        "overlay_outputs": overlay_outputs,
        "requirements": {
            "strict_official_mode": strict_official_mode,
            "manual_price_required": manual_price_required,
            "manual_price_reason": manual_price_reason,
            "manual_sensitivity_required": manual_sensitivity_required,
            "manual_sensitivity_reason": manual_sensitivity_reason,
            "price_input_mode": "manual" if manual_price_required else "cached_market_price",
        },
        "diagnostics": diagnostics,
        "confidence_flags": sorted(confidence_flags),
        "provenance": provenance_entries,
        "source_mix": source_mix,
    }


def _resolve_base_fair_value_per_share(models: list[Any]) -> tuple[float | None, datetime | None]:
    model_by_name = {str(getattr(model, "model_name", "")).lower(): model for model in models}
    dcf = model_by_name.get("dcf")
    dcf_result = getattr(dcf, "result", None) if dcf is not None else None
    if isinstance(dcf_result, dict):
        value = _as_float(dcf_result.get("fair_value_per_share"))
        if value is not None:
            return value, _normalize_datetime(getattr(dcf, "created_at", None))

    residual = model_by_name.get("residual_income")
    residual_result = getattr(residual, "result", None) if residual is not None else None
    if isinstance(residual_result, dict):
        value = _as_float(residual_result.get("intrinsic_value_per_share"))
        nested = residual_result.get("intrinsic_value") if isinstance(residual_result.get("intrinsic_value"), dict) else None
        nested_value = _as_float(nested.get("intrinsic_value_per_share")) if nested is not None else None
        resolved = value if value is not None else nested_value
        if resolved is not None:
            return resolved, _normalize_datetime(getattr(residual, "created_at", None))

    return None, None


def _resolve_diluted_shares(financials: list[Any]) -> float | None:
    latest = financials[0] if financials else None
    if latest is None:
        return None
    return _as_float(getattr(latest, "weighted_average_diluted_shares", None)) or _as_float(getattr(latest, "shares_outstanding", None))


def _resolve_current_share_price(price_history: list[Any]) -> tuple[float | None, str | None]:
    latest = price_history[-1] if price_history else None
    if latest is None:
        return None, None
    trade_date = getattr(latest, "trade_date", None)
    return _as_float(getattr(latest, "close", None)), trade_date.isoformat() if isinstance(trade_date, date) else None


def _resolve_selected_benchmark_id(series_list: list[dict[str, Any]]) -> str | None:
    preferred = next((series for series in series_list if "wti" in str(series.get("series_id") or "").lower()), None)
    if preferred is not None:
        return str(preferred.get("series_id") or "") or None
    first = series_list[0] if series_list else None
    return str(first.get("series_id") or "") or None if isinstance(first, dict) else None


def _benchmark_option(series: dict[str, Any]) -> dict[str, str]:
    series_id = str(series.get("series_id") or "")
    label = str(series.get("label") or series_id)
    normalized_id = series_id.lower()
    if "wti" in normalized_id:
        label = "WTI"
    elif "brent" in normalized_id:
        label = "Brent"
    return {"value": series_id, "label": label}


def _annualize_curve_series(series: dict[str, Any] | None) -> list[dict[str, float | int]]:
    if not isinstance(series, dict):
        return []

    grouped: dict[int, list[float]] = {}
    for point in series.get("points") or []:
        if not isinstance(point, dict):
            continue
        year = _extract_year(point.get("observation_date") or point.get("label"))
        value = _as_float(point.get("value"))
        if year is None or value is None:
            continue
        grouped.setdefault(year, []).append(value)

    annualized: list[dict[str, float | int]] = []
    for year in sorted(grouped):
        values = grouped[year]
        annualized.append({"year": year, "price": sum(values) / len(values)})
    return annualized


def _build_default_short_term_curve(points: list[dict[str, float | int]]) -> list[dict[str, float | int]]:
    if not points:
        return []
    return [{"year": int(point["year"]), "price": float(point["price"])} for point in points[-min(3, len(points)):]]


def _resolve_default_long_term_anchor(points: list[dict[str, float | int]]) -> float | None:
    if not points:
        return None
    return _as_float(points[-1].get("price"))


def _resolve_sensitivity_source(sensitivity: dict[str, Any] | None) -> tuple[SensitivitySourceKind, float | None]:
    if not isinstance(sensitivity, dict):
        return "manual", None

    value = _as_float(sensitivity.get("elasticity"))
    if value is None or str(sensitivity.get("status") or "").lower() == "placeholder":
        return "manual", None

    markers = " ".join(
        [
            str(sensitivity.get("status") or ""),
            str(sensitivity.get("metric_basis") or ""),
            " ".join(str(flag) for flag in (sensitivity.get("confidence_flags") or []) if isinstance(flag, str)),
        ]
    ).lower()
    if "disclosed" in markers:
        return "disclosed", value
    return "derived_from_official", value


def _manual_price_reason(current_share_price: float | None, *, strict_official_mode: bool) -> str | None:
    if current_share_price is not None:
        return None
    if strict_official_mode:
        return "STRICT_OFFICIAL_MODE disables fallback-backed market prices for public oil scenario outputs."
    return "A cached current share price is unavailable, so manual price entry is required for upside or downside outputs."


def _merge_provenance_entries(
    existing_entries: Any,
    *,
    model_refreshed_at: datetime | None,
    current_price_as_of: str | None,
    checked_at: datetime,
    include_market_price: bool,
) -> list[dict[str, Any]]:
    merged: list[dict[str, Any]] = []
    seen: set[str] = set()

    for entry in existing_entries or []:
        if not isinstance(entry, dict):
            continue
        source_id = str(entry.get("source_id") or "").strip()
        if not source_id or source_id in seen:
            continue
        merged.append(entry)
        seen.add(source_id)

    extra_usages: list[SourceUsage] = []
    if model_refreshed_at is not None:
        extra_usages.append(
            SourceUsage(
                source_id="ft_model_engine",
                role="supplemental",
                as_of=model_refreshed_at.date().isoformat(),
                last_refreshed_at=model_refreshed_at,
            )
        )
    if include_market_price:
        extra_usages.append(
            SourceUsage(
                source_id="yahoo_finance",
                role="fallback",
                as_of=current_price_as_of,
                last_refreshed_at=checked_at,
            )
        )

    for entry in build_provenance_entries(extra_usages):
        source_id = str(entry.get("source_id") or "").strip()
        if not source_id or source_id in seen:
            continue
        merged.append(entry)
        seen.add(source_id)

    return merged


def _extract_year(value: Any) -> int | None:
    text = str(value or "").strip()
    if len(text) < 4:
        return None
    for start in range(0, len(text) - 3):
        candidate = text[start : start + 4]
        if candidate.isdigit() and candidate.startswith(("19", "20")):
            return int(candidate)
    return None


def _support_status(value: Any) -> Literal["supported", "partial", "unsupported"]:
    normalized = str(value or "unsupported").strip().lower()
    if normalized == "supported":
        return "supported"
    if normalized == "partial":
        return "partial"
    return "unsupported"


def _as_float(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        numeric = float(value)
        return numeric if numeric == numeric and numeric not in (float("inf"), float("-inf")) else None
    try:
        numeric = float(str(value).strip())
    except (TypeError, ValueError):
        return None
    return numeric if numeric == numeric and numeric not in (float("inf"), float("-inf")) else None


def _normalize_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)
    return None