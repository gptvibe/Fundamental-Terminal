from __future__ import annotations

from datetime import datetime, timezone
from email.utils import formatdate
from urllib.parse import urlencode

from starlette.requests import Request

from app.api import validation
from app.api.handlers import _shared
from app.config import settings
from app.query_params import DuplicateSingletonQueryParamError, read_singleton_query_param


COMPANY_ROUTE_CACHE_CONTROL = "public, max-age=20, stale-while-revalidate=300"
BOOTSTRAP_SECTION_NAMES = {
    "company_summary",
    "latest_financials",
    "recent_filings",
    "recent_events",
    "ownership_summary",
    "source_freshness",
    "warnings",
}


def _legacy_or_shared_attr(name: str):
    try:
        import app.main as main_module
    except Exception:  # pragma: no cover - defensive during bootstrap
        main_module = None

    if main_module is not None and hasattr(main_module, name):
        return getattr(main_module, name)

    try:
        import app.legacy_api as legacy_module
    except Exception:  # pragma: no cover - defensive during bootstrap
        legacy_module = None

    if legacy_module is not None and hasattr(legacy_module, name):
        return getattr(legacy_module, name)
    return getattr(_shared, name, None)


def _should_apply_company_route_cache(path: str) -> bool:
    return "/charts/scenarios" not in path and "/charts/share-snapshots" not in path


def _normalize_company_cache_datetime(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _format_company_cache_last_modified(value: datetime | None) -> str | None:
    normalized = _normalize_company_cache_datetime(value)
    if normalized is None:
        return None
    return formatdate(normalized.timestamp(), usegmt=True)


def _canonicalize_company_query_string(request: Request) -> str:
    singleton_values: dict[str, str | None] = {}
    singleton_names = {"as_of"}
    if request.url.path == "/api/companies/compare":
        singleton_names.add("tickers")
    elif request.url.path.startswith("/api/companies/") and request.url.path.endswith("/financials"):
        singleton_names.add("view")
    elif request.url.path.startswith("/api/companies/") and request.url.path.endswith("/overview"):
        singleton_names.add("financials_view")
    elif request.url.path.startswith("/api/companies/") and request.url.path.endswith("/workspace-bootstrap"):
        singleton_names.update(
            {
                "compact",
                "financials_view",
                "include_overview_brief",
                "include_insiders",
                "include_institutional",
                "include_earnings_summary",
                "price_end_date",
                "price_latest_n",
                "price_max_points",
                "price_start_date",
                "sections",
            }
        )
    elif request.url.path.startswith("/api/companies/") and request.url.path.endswith("/models"):
        singleton_names.update({"expand", "dupont_mode"})

    for name in singleton_names:
        try:
            singleton_values[name] = read_singleton_query_param(request, name)
        except DuplicateSingletonQueryParamError as exc:
            raise ValueError(str(exc)) from exc

    requested_as_of = singleton_values.get("as_of")
    if requested_as_of is not None:
        validation._validated_as_of(requested_as_of)

    if request.url.path.startswith("/api/companies/") and request.url.path.endswith("/models"):
        _parsed_as_of, requested_expansions, normalized_mode, normalized_as_of = validation._normalize_company_models_query_controls(
            requested_as_of=singleton_values.get("as_of"),
            expand=singleton_values.get("expand"),
            dupont_mode=singleton_values.get("dupont_mode"),
        )
        singleton_values["as_of"] = None if normalized_as_of == "latest" else normalized_as_of
        singleton_values["expand"] = ",".join(sorted(requested_expansions)) or None
        singleton_values["dupont_mode"] = normalized_mode
    elif request.url.path.startswith("/api/companies/") and request.url.path.endswith("/financials"):
        _parsed_as_of, normalized_view, normalized_as_of = validation._normalize_company_financials_query_controls(
            requested_as_of=singleton_values.get("as_of"),
            view=singleton_values.get("view"),
        )
        singleton_values["as_of"] = None if normalized_as_of == "latest" else normalized_as_of
        singleton_values["view"] = None if normalized_view == "full" else normalized_view
    elif request.url.path.startswith("/api/companies/") and request.url.path.endswith("/overview"):
        _parsed_as_of, normalized_view, normalized_as_of = validation._normalize_company_financials_query_controls(
            requested_as_of=singleton_values.get("as_of"),
            view=singleton_values.get("financials_view"),
        )
        singleton_values["as_of"] = None if normalized_as_of == "latest" else normalized_as_of
        singleton_values["financials_view"] = None if normalized_view == "full" else normalized_view
    elif request.url.path.startswith("/api/companies/") and request.url.path.endswith("/workspace-bootstrap"):
        _parsed_as_of, normalized_view, normalized_as_of = validation._normalize_company_financials_query_controls(
            requested_as_of=singleton_values.get("as_of"),
            view=singleton_values.get("financials_view"),
        )
        singleton_values["as_of"] = None if normalized_as_of == "latest" else normalized_as_of
        singleton_values["financials_view"] = None if normalized_view == "full" else normalized_view

        for flag_name in (
            "include_overview_brief",
            "include_insiders",
            "include_institutional",
            "include_earnings_summary",
        ):
            raw_value = singleton_values.get(flag_name)
            if raw_value is None:
                continue
            normalized = raw_value.strip().lower()
            singleton_values[flag_name] = "true" if normalized in {"1", "true", "yes", "on"} else None

        price_controls, price_controls_are_valid = _resolved_company_price_controls_from_values(singleton_values)
        if not price_controls_are_valid or price_controls is None:
            raise ValueError("Invalid workspace-bootstrap price history controls")
        singleton_values["price_start_date"] = price_controls["start"]
        singleton_values["price_end_date"] = price_controls["end"]
        singleton_values["price_latest_n"] = price_controls["latest"]
        singleton_values["price_max_points"] = price_controls["max_points"]

        raw_sections = singleton_values.get("sections")
        normalized_sections = _normalized_bootstrap_sections(
            raw_sections,
            include_overview_brief=singleton_values.get("include_overview_brief") == "true",
            include_insiders=singleton_values.get("include_insiders") == "true",
            include_institutional=singleton_values.get("include_institutional") == "true",
            include_earnings_summary=singleton_values.get("include_earnings_summary") == "true",
        )
        singleton_values["sections"] = ",".join(sorted(normalized_sections)) if normalized_sections else None

        raw_compact = singleton_values.get("compact")
        singleton_values["compact"] = "true" if raw_compact is not None and raw_compact.strip().lower() in {"1", "true", "yes"} else None

    query_items = sorted(
        [
            (name, value)
            for name, value in request.query_params.multi_items()
            if name not in singleton_names
        ]
        + [
            (name, value)
            for name, value in singleton_values.items()
            if value is not None
        ],
        key=lambda item: (item[0], item[1]),
    )
    return urlencode(query_items, doseq=True)


def _resolved_company_as_of(request: Request) -> tuple[str | None, bool]:
    try:
        requested_as_of = read_singleton_query_param(request, "as_of")
    except DuplicateSingletonQueryParamError:
        return None, False
    if requested_as_of is None:
        return "latest", True

    try:
        parsed_as_of = validation._validated_as_of(requested_as_of)
        normalized = validation._normalize_as_of(parsed_as_of)
    except Exception:
        return None, False

    if parsed_as_of is None:
        return None, False
    return normalized or requested_as_of, True


def _resolved_company_models_controls(request: Request) -> tuple[dict[str, str | None] | None, bool]:
    try:
        requested_as_of = read_singleton_query_param(request, "as_of")
        requested_expand = read_singleton_query_param(request, "expand")
        requested_dupont_mode = read_singleton_query_param(request, "dupont_mode")
    except DuplicateSingletonQueryParamError:
        return None, False

    try:
        _parsed_as_of, requested_expansions, normalized_mode, normalized_as_of = validation._normalize_company_models_query_controls(
            requested_as_of=requested_as_of,
            expand=requested_expand,
            dupont_mode=requested_dupont_mode,
        )
    except Exception:
        return None, False

    return {
        "as_of": normalized_as_of,
        "expand": ",".join(sorted(requested_expansions)) or "default",
        "dupont_mode": normalized_mode,
    }, True


def _resolved_company_financials_controls(
    request: Request,
    *,
    view_param_name: str,
) -> tuple[dict[str, str] | None, bool]:
    try:
        requested_as_of = read_singleton_query_param(request, "as_of")
        requested_view = read_singleton_query_param(request, view_param_name)
    except DuplicateSingletonQueryParamError:
        return None, False

    try:
        _parsed_as_of, normalized_view, normalized_as_of = validation._normalize_company_financials_query_controls(
            requested_as_of=requested_as_of,
            view=requested_view,
        )
    except Exception:
        return None, False

    return {"as_of": normalized_as_of, "view": normalized_view}, True


def _normalized_company_flag(request: Request, name: str) -> tuple[bool | None, bool]:
    try:
        raw_value = read_singleton_query_param(request, name)
    except DuplicateSingletonQueryParamError:
        return None, False
    if raw_value is None:
        return False, True
    return raw_value.strip().lower() in {"1", "true", "yes", "on"}, True


def _read_company_singleton_query_param(request: Request, name: str) -> tuple[str | None, bool]:
    try:
        return read_singleton_query_param(request, name), True
    except DuplicateSingletonQueryParamError:
        return None, False


def _coerce_optional_positive_int(value: str | None) -> tuple[int | None, bool]:
    if value is None or value.strip() == "":
        return None, True
    try:
        return int(value), True
    except ValueError:
        return None, False


def _resolved_company_price_controls_from_values(
    values: dict[str, str | None],
) -> tuple[dict[str, str | None] | None, bool]:
    latest_n, latest_is_valid = _coerce_optional_positive_int(values.get("price_latest_n"))
    max_points, max_points_is_valid = _coerce_optional_positive_int(values.get("price_max_points"))
    if not latest_is_valid or not max_points_is_valid:
        return None, False

    try:
        start_date, end_date, latest_n, max_points = _shared._normalize_price_history_query_controls(
            price_start_date=values.get("price_start_date"),
            price_end_date=values.get("price_end_date"),
            price_latest_n=latest_n,
            price_max_points=max_points,
        )
    except Exception:
        return None, False

    return {
        "start": start_date.isoformat() if start_date is not None else None,
        "end": end_date.isoformat() if end_date is not None else None,
        "latest": str(latest_n) if latest_n is not None else None,
        "max_points": str(max_points) if max_points is not None else None,
        "token": _shared._price_history_cache_token(
            start_date=start_date,
            end_date=end_date,
            latest_n=latest_n,
            max_points=max_points,
        ),
    }, True


def _resolved_company_price_controls(request: Request) -> tuple[dict[str, str | None] | None, bool]:
    values: dict[str, str | None] = {}
    for name in ("price_start_date", "price_end_date", "price_latest_n", "price_max_points"):
        raw_value, is_valid = _read_company_singleton_query_param(request, name)
        if not is_valid:
            return None, False
        values[name] = raw_value
    return _resolved_company_price_controls_from_values(values)


def _normalized_bootstrap_sections(
    raw_sections: str | None,
    *,
    include_overview_brief: bool,
    include_insiders: bool,
    include_institutional: bool,
    include_earnings_summary: bool,
) -> list[str]:
    sections = [
        value.strip().lower()
        for value in (raw_sections or "").split(",")
        if value.strip()
    ]
    requested_sections = [section for section in sections if section in BOOTSTRAP_SECTION_NAMES]
    if requested_sections:
        return list(dict.fromkeys(requested_sections))

    legacy_sections: list[str] = []
    if include_overview_brief:
        legacy_sections.extend(["company_summary", "recent_filings", "recent_events"])
    if include_insiders or include_institutional:
        legacy_sections.append("ownership_summary")
    if include_earnings_summary:
        legacy_sections.append("recent_events")
    return list(dict.fromkeys(legacy_sections))


def _company_route_hot_cache_keys(request: Request) -> list[str]:
    path = request.url.path
    if not path.startswith("/api/companies/"):
        return []

    suffix = path[len("/api/companies/") :]
    ticker, separator, rest = suffix.partition("/")
    if not separator or not ticker or ticker in {"search", "resolve", "compare"}:
        return []

    normalized_ticker = ticker.strip().upper()
    normalized_as_of, as_of_is_valid = _resolved_company_as_of(request)
    if not as_of_is_valid or normalized_as_of is None:
        return []

    route_name = rest.strip()
    if not route_name:
        return []

    if route_name == "financials":
        financial_controls, controls_are_valid = _resolved_company_financials_controls(request, view_param_name="view")
        if not controls_are_valid or financial_controls is None:
            return []
        return [f"financials:{normalized_ticker}:view={financial_controls['view']}:asof={financial_controls['as_of']}"]

    if route_name == "overview":
        financial_controls, controls_are_valid = _resolved_company_financials_controls(request, view_param_name="financials_view")
        if not controls_are_valid or financial_controls is None:
            return []
        build_overview_key = _legacy_or_shared_attr("_company_overview_hot_key")
        if callable(build_overview_key):
            return [
                build_overview_key(
                    normalized_ticker,
                    financials_view=financial_controls["view"],
                    as_of=financial_controls["as_of"],
                )
            ]
        return []

    if route_name == "workspace-bootstrap":
        financial_controls, controls_are_valid = _resolved_company_financials_controls(request, view_param_name="financials_view")
        if not controls_are_valid or financial_controls is None:
            return []
        include_overview_brief, overview_is_valid = _normalized_company_flag(request, "include_overview_brief")
        include_insiders, insiders_are_valid = _normalized_company_flag(request, "include_insiders")
        include_institutional, institutional_is_valid = _normalized_company_flag(request, "include_institutional")
        include_earnings_summary, earnings_is_valid = _normalized_company_flag(request, "include_earnings_summary")
        if not all((overview_is_valid, insiders_are_valid, institutional_is_valid, earnings_is_valid)):
            return []
        price_controls, price_controls_are_valid = _resolved_company_price_controls(request)
        if not price_controls_are_valid or price_controls is None:
            return []
        raw_sections, sections_are_valid = _read_company_singleton_query_param(request, "sections")
        raw_compact, compact_is_valid = _read_company_singleton_query_param(request, "compact")
        if not sections_are_valid or not compact_is_valid:
            return []
        sections = _normalized_bootstrap_sections(
            raw_sections,
            include_overview_brief=bool(include_overview_brief),
            include_insiders=bool(include_insiders),
            include_institutional=bool(include_institutional),
            include_earnings_summary=bool(include_earnings_summary),
        )
        compact = raw_compact is not None and raw_compact.strip().lower() in {"1", "true", "yes"}
        build_workspace_key = _legacy_or_shared_attr("_company_workspace_bootstrap_hot_key")
        if callable(build_workspace_key):
            return [
                build_workspace_key(
                    normalized_ticker,
                    financials_view=financial_controls["view"],
                    as_of=financial_controls["as_of"],
                    include_overview_brief=bool(include_overview_brief),
                    include_insiders=bool(include_insiders),
                    include_institutional=bool(include_institutional),
                    include_earnings_summary=bool(include_earnings_summary),
                    price_token=str(price_controls["token"] or "default"),
                    sections=tuple(sorted(sections)),
                    compact=compact,
                )
            ]
        return []

    if route_name == "brief":
        return [f"financials:{normalized_ticker}:view=full:asof={normalized_as_of}"]

    if route_name == "charts":
        return [f"charts:{normalized_ticker}:asof={normalized_as_of}"]

    if route_name == "capital-structure":
        try:
            max_periods = int(request.query_params.get("max_periods", "8"))
        except ValueError:
            return []
        return [f"capital_structure:{normalized_ticker}:periods={max_periods}:asof={normalized_as_of}"]

    if route_name == "models":
        model_controls, controls_are_valid = _resolved_company_models_controls(request)
        if not controls_are_valid or model_controls is None:
            return []
        parse_requested_models = _legacy_or_shared_attr("_parse_requested_models")
        requested_models = parse_requested_models(request.query_params.get("model")) if callable(parse_requested_models) else []
        if not settings.valuation_workbench_enabled:
            requested_models = [
                item
                for item in requested_models
                if item not in {"reverse_dcf", "roic", "capital_allocation"}
            ]
        return [
            (
                f"models:{normalized_ticker}:models={','.join(requested_models)}:dupont={model_controls['dupont_mode'] or 'default'}"
                f":expand={model_controls['expand']}:asof={model_controls['as_of']}"
            )
        ]

    if route_name == "peers":
        parse_csv_values = _legacy_or_shared_attr("_parse_csv_values")
        selected_tickers = parse_csv_values(request.query_params.get("peers")) if callable(parse_csv_values) else []
        return [f"peers:{normalized_ticker}:selected={','.join(selected_tickers)}:asof={normalized_as_of}"]

    if route_name == "oil-scenario-overlay":
        return [f"oil_scenario_overlay:{normalized_ticker}"]

    if route_name == "oil":
        return [f"oil_scenario:{normalized_ticker}"]

    return []


__all__ = [
    "COMPANY_ROUTE_CACHE_CONTROL",
    "_canonicalize_company_query_string",
    "_company_route_hot_cache_keys",
    "_format_company_cache_last_modified",
    "_normalize_company_cache_datetime",
    "_should_apply_company_route_cache",
]
