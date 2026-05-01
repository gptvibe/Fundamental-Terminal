from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Any

from app.api.handlers._dispatch import route_handler
from app.api.handlers import _shared as shared
from app.services.market_context import get_company_market_context_v2, get_market_context_v2


# Keep dispatch target discovery for static guard tests.
_company_market_context_dispatch = route_handler("company_market_context")
_global_market_context_dispatch = route_handler("global_market_context")
company_sector_context = route_handler("company_sector_context")
company_brief = route_handler("company_brief")
company_overview = route_handler("company_overview")
company_workspace_bootstrap = route_handler("company_workspace_bootstrap")
company_peers = route_handler("company_peers")


@shared.app.get("/api/companies/{ticker}/market-context", response_model=shared.CompanyMarketContextResponse)
def company_market_context(
	ticker: str,
	session: shared.Session = shared.Depends(shared.get_db_session),
) -> shared.CompanyMarketContextResponse:
	normalized_ticker = shared._normalize_ticker(ticker)
	snapshot = shared._resolve_cached_company_snapshot(session, normalized_ticker)
	if snapshot is None:
		payload = {
			"status": "insufficient_data",
			"curve_points": [],
			"slope_2s10s": {},
			"slope_3m10y": {},
			"fred_series": [],
			"provenance": {
				"treasury": {"status": "missing"},
				"fred": {
					"enabled": bool(shared.settings.fred_api_key),
					"status": "missing_api_key" if not shared.settings.fred_api_key else "missing",
				},
			},
			"rates_credit": [],
			"inflation_labor": [],
			"growth_activity": [],
			"relevant_series": [],
			"sector_exposure": [],
			"hqm_snapshot": None,
		}
		refresh = shared._trigger_refresh(normalized_ticker, reason="missing")
		fetched_at = datetime.now(timezone.utc)
		return shared.CompanyMarketContextResponse(
			company=None,
			status="insufficient_data",
			curve_points=[],
			slope_2s10s=shared.MarketSlopePayload(
				label="2s10s",
				value=None,
				short_tenor="2y",
				long_tenor="10y",
				observation_date=None,
			),
			slope_3m10y=shared.MarketSlopePayload(
				label="3m10y",
				value=None,
				short_tenor="3m",
				long_tenor="10y",
				observation_date=None,
			),
			fred_series=[],
			provenance_details=payload["provenance"],
			fetched_at=fetched_at,
			refresh=refresh,
			**_market_context_provenance_contract(payload, fetched_at=fetched_at, refresh=refresh),
		)

	refresh = shared._refresh_for_snapshot(snapshot)
	company = snapshot.company
	payload = get_company_market_context_v2(
		session,
		company.id,
		sector=company.sector,
		market_sector=company.market_sector,
		market_industry=company.market_industry,
	)
	return _v2_dict_to_response(payload, company=shared._serialize_company(snapshot), refresh=refresh)


def _v2_dict_to_response(
	payload: dict[str, Any],
	*,
	company: "shared.CompanyPayload | None",
	refresh: "shared.RefreshState",
) -> "shared.CompanyMarketContextResponse":
	curve_points: list[shared.MarketCurvePointPayload] = []
	for point in payload.get("curve_points") or []:
		if not isinstance(point, dict):
			continue

		tenor = str(point.get("tenor") or "").strip()
		rate = _coerce_market_context_number(point.get("rate"))
		observation_date = point.get("observation_date")
		if not tenor or rate is None or observation_date is None:
			continue

		curve_points.append(
			shared.MarketCurvePointPayload(
				tenor=tenor,
				rate=rate,
				observation_date=observation_date,
			)
		)

	s2 = payload.get("slope_2s10s") or {}
	s3 = payload.get("slope_3m10y") or {}
	slope_2s10s = shared.MarketSlopePayload(
		label=str(s2.get("label") or "2s10s"),
		value=_coerce_market_context_number(s2.get("value")),
		short_tenor=str(s2.get("short_tenor") or "2y"),
		long_tenor=str(s2.get("long_tenor") or "10y"),
		observation_date=s2.get("observation_date"),
	)
	slope_3m10y = shared.MarketSlopePayload(
		label=str(s3.get("label") or "3m10y"),
		value=_coerce_market_context_number(s3.get("value")),
		short_tenor=str(s3.get("short_tenor") or "3m"),
		long_tenor=str(s3.get("long_tenor") or "10y"),
		observation_date=s3.get("observation_date"),
	)
	fred_series: list[shared.MarketFredSeriesPayload] = []
	for item in payload.get("fred_series") or []:
		if not isinstance(item, dict):
			continue
		fred_series.append(
			shared.MarketFredSeriesPayload(
				series_id=str(item.get("series_id", "")),
				label=str(item.get("label", "")),
				category=str(item.get("category", "")),
				units=str(item.get("units", "")),
				value=_coerce_market_context_number(item.get("value")),
				observation_date=item.get("observation_date"),
				state=str(item.get("state", "ok")),
			)
		)

	def _items(section_key: str) -> list[shared.MacroSeriesItemPayload]:
		items: list[shared.MacroSeriesItemPayload] = []
		for raw_item in payload.get(section_key) or []:
			if not isinstance(raw_item, dict):
				continue

			history: list[shared.MacroHistoryPointPayload] = []
			for raw_history_point in raw_item.get("history") or []:
				if not isinstance(raw_history_point, dict):
					continue

				history_date = str(raw_history_point.get("date") or "").strip()
				history_value = _coerce_market_context_number(raw_history_point.get("value"))
				if not history_date or history_value is None:
					continue

				history.append(shared.MacroHistoryPointPayload(date=history_date, value=history_value))

			items.append(
				shared.MacroSeriesItemPayload(
					series_id=str(raw_item.get("series_id", "")),
					label=str(raw_item.get("label", "")),
					source_name=str(raw_item.get("source_name", "")),
					source_url=str(raw_item.get("source_url", "")),
					units=str(raw_item.get("units", "")),
					value=_coerce_market_context_number(raw_item.get("value")),
					previous_value=_coerce_market_context_number(raw_item.get("previous_value")),
					change=_coerce_market_context_number(raw_item.get("change")),
					change_percent=_coerce_market_context_number(raw_item.get("change_percent")),
					observation_date=raw_item.get("observation_date"),
					release_date=raw_item.get("release_date"),
					history=history,
					status=str(raw_item.get("status", "ok")),
				)
			)

		return items

	fetched_raw = payload.get("fetched_at") or ""
	try:
		fetched_at = datetime.fromisoformat(str(fetched_raw))
	except Exception:
		fetched_at = datetime.now(timezone.utc)

	return shared.CompanyMarketContextResponse(
		company=company,
		status=str(payload.get("status") or "ok"),
		curve_points=curve_points,
		slope_2s10s=slope_2s10s,
		slope_3m10y=slope_3m10y,
		fred_series=fred_series,
		provenance_details=payload.get("provenance") or {},
		fetched_at=fetched_at,
		refresh=refresh,
		rates_credit=_items("rates_credit"),
		inflation_labor=_items("inflation_labor"),
		growth_activity=_items("growth_activity"),
		cyclical_demand=_items("cyclical_demand"),
		cyclical_costs=_items("cyclical_costs"),
		relevant_series=[str(item) for item in (payload.get("relevant_series") or []) if isinstance(item, str)],
		relevant_indicators=_items("relevant_indicators"),
		sector_exposure=[str(item) for item in (payload.get("sector_exposure") or []) if isinstance(item, str)],
		hqm_snapshot=payload.get("hqm_snapshot") if isinstance(payload.get("hqm_snapshot"), dict) else None,
		**_market_context_provenance_contract(payload, fetched_at=fetched_at, refresh=refresh),
	)


def _coerce_market_context_number(value: Any) -> float | None:
	if value is None or value == "" or isinstance(value, bool):
		return None

	if isinstance(value, (int, float)):
		numeric_value = float(value)
	elif isinstance(value, str):
		try:
			numeric_value = float(value)
		except ValueError:
			return None
	else:
		return None

	if not math.isfinite(numeric_value):
		return None

	return numeric_value


@shared.app.get("/api/market-context", response_model=shared.CompanyMarketContextResponse)
def global_market_context(
	session: shared.Session = shared.Depends(shared.get_db_session),
) -> shared.CompanyMarketContextResponse:
	payload = get_market_context_v2(session)
	return _v2_dict_to_response(
		payload,
		company=None,
		refresh=shared.RefreshState(triggered=False, reason="none", ticker=None, job_id=None),
	)


def _market_context_provenance_contract(
	payload: dict[str, Any],
	*,
	fetched_at: datetime,
	refresh: shared.RefreshState | None = None,
) -> dict[str, Any]:
	usages: list[shared.SourceUsage] = []
	provenance_details = payload.get("provenance") if isinstance(payload.get("provenance"), dict) else {}
	treasury_details = provenance_details.get("treasury") if isinstance(provenance_details.get("treasury"), dict) else {}
	fred_details = provenance_details.get("fred") if isinstance(provenance_details.get("fred"), dict) else {}

	treasury_usage = shared._source_usage_from_hint(
		str(treasury_details.get("source_name") or treasury_details.get("source_url") or ""),
		role="primary",
		as_of=treasury_details.get("observation_date"),
		last_refreshed_at=fetched_at,
		default_source_id="us_treasury_daily_par_yield_curve",
	)
	if treasury_usage is not None:
		usages.append(treasury_usage)

	fred_usage = shared._source_usage_from_hint(
		str(fred_details.get("source") or fred_details.get("source_name") or ""),
		role="supplemental",
		as_of=shared._latest_as_of(*[item.get("observation_date") for item in payload.get("fred_series") or [] if isinstance(item, dict)]),
		last_refreshed_at=fetched_at,
	)
	if fred_usage is not None:
		usages.append(fred_usage)

	for section_key in ("rates_credit", "inflation_labor", "growth_activity", "cyclical_demand", "cyclical_costs", "relevant_indicators"):
		for item in payload.get(section_key) or []:
			if not isinstance(item, dict):
				continue
			usage = shared._source_usage_from_hint(
				str(item.get("source_url") or item.get("source_name") or ""),
				role="supplemental",
				as_of=item.get("observation_date") or item.get("release_date"),
				last_refreshed_at=fetched_at,
			)
			if usage is not None:
				usages.append(usage)

	hqm_snapshot = payload.get("hqm_snapshot")
	if isinstance(hqm_snapshot, dict):
		hqm_usage = shared._source_usage_from_hint(
			str(hqm_snapshot.get("source_url") or hqm_snapshot.get("source_name") or ""),
			role="supplemental",
			as_of=hqm_snapshot.get("observation_date"),
			last_refreshed_at=fetched_at,
		)
		if hqm_usage is not None:
			usages.append(hqm_usage)

	as_of_values: list[Any] = []
	as_of_values.extend(point.get("observation_date") for point in payload.get("curve_points") or [] if isinstance(point, dict))
	as_of_values.extend(item.get("observation_date") for item in payload.get("fred_series") or [] if isinstance(item, dict))
	as_of_values.extend(item.get("observation_date") or item.get("release_date") for item in payload.get("rates_credit") or [] if isinstance(item, dict))
	as_of_values.extend(item.get("observation_date") or item.get("release_date") for item in payload.get("inflation_labor") or [] if isinstance(item, dict))
	as_of_values.extend(item.get("observation_date") or item.get("release_date") for item in payload.get("growth_activity") or [] if isinstance(item, dict))
	as_of_values.extend(item.get("observation_date") or item.get("release_date") for item in payload.get("cyclical_demand") or [] if isinstance(item, dict))
	as_of_values.extend(item.get("observation_date") or item.get("release_date") for item in payload.get("cyclical_costs") or [] if isinstance(item, dict))
	if isinstance(hqm_snapshot, dict):
		as_of_values.append(hqm_snapshot.get("observation_date"))

	status_value = str(payload.get("status") or "ok")
	confidence_flags = [*shared._confidence_flags_from_refresh(refresh)]
	if status_value != "ok":
		confidence_flags.append(f"market_context_{status_value}")
	treasury_status = str(treasury_details.get("status") or "ok")
	if treasury_status != "ok":
		confidence_flags.append(f"treasury_{treasury_status}")
	if bool(treasury_details.get("fallback_used")):
		confidence_flags.append("treasury_fallback_used")
	fred_status = str(fred_details.get("status") or "ok")
	if fred_status == "missing_api_key":
		confidence_flags.append("supplemental_fred_unconfigured")
	elif fred_status != "ok":
		confidence_flags.append(f"fred_{fred_status}")
	census_details = provenance_details.get("census") if isinstance(provenance_details.get("census"), dict) else {}
	census_status = str(census_details.get("status") or "ok")
	if census_status != "ok":
		confidence_flags.append(f"census_{census_status}")
	bls_details = provenance_details.get("bls") if isinstance(provenance_details.get("bls"), dict) else {}
	bls_status = str(bls_details.get("status") or "ok")
	if bls_status != "ok":
		confidence_flags.append(f"bls_{bls_status}")
	bea_details = provenance_details.get("bea") if isinstance(provenance_details.get("bea"), dict) else {}
	if not bool(bea_details.get("configured", True)):
		confidence_flags.append("bea_unconfigured")
	bea_status = str(bea_details.get("status") or "ok")
	if bea_status != "ok":
		confidence_flags.append(f"bea_{bea_status}")

	return shared._build_provenance_contract(
		usages,
		as_of=shared._latest_as_of(*as_of_values),
		last_refreshed_at=fetched_at,
		confidence_flags=confidence_flags,
	)


company_market_context = shared._wrap_db_handler(company_market_context)
global_market_context = shared._wrap_db_handler(global_market_context)


__all__ = [
	"company_brief",
	"company_market_context",
	"company_overview",
	"company_peers",
	"company_sector_context",
	"company_workspace_bootstrap",
	"global_market_context",
]
