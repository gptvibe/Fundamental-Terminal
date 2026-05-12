from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


DatasetSourceType = Literal[
    "official_sec",
    "official_market_fallback",
    "derived_internal",
]

RefreshCostClass = Literal["low", "medium", "high"]
RefreshPolicy = Literal["request_path_or_worker", "background_worker_only"]


@dataclass(frozen=True, slots=True)
class DatasetDefinition:
    dataset_key: str
    source_type: DatasetSourceType
    freshness_ttl_seconds: int
    refresh_cost_class: RefreshCostClass
    refresh_function_path: str
    supports_point_in_time_reads: bool
    refresh_policy: RefreshPolicy
    source_ids: tuple[str, ...]
    runtime_dataset_keys: tuple[str, ...]


DATASET_REGISTRY: dict[str, DatasetDefinition] = {
    "company_profile_submissions": DatasetDefinition(
        dataset_key="company_profile_submissions",
        source_type="official_sec",
        freshness_ttl_seconds=6 * 60 * 60,
        refresh_cost_class="medium",
        refresh_function_path="app.services.sec.refresh_orchestrator.refresh_company",
        supports_point_in_time_reads=True,
        refresh_policy="request_path_or_worker",
        source_ids=("sec_edgar",),
        runtime_dataset_keys=("filings",),
    ),
    "companyfacts": DatasetDefinition(
        dataset_key="companyfacts",
        source_type="official_sec",
        freshness_ttl_seconds=6 * 60 * 60,
        refresh_cost_class="medium",
        refresh_function_path="app.services.sec.refresh_orchestrator.refresh_company",
        supports_point_in_time_reads=True,
        refresh_policy="request_path_or_worker",
        source_ids=("sec_companyfacts",),
        runtime_dataset_keys=("financials",),
    ),
    "financial_statements": DatasetDefinition(
        dataset_key="financial_statements",
        source_type="official_sec",
        freshness_ttl_seconds=6 * 60 * 60,
        refresh_cost_class="high",
        refresh_function_path="app.services.sec.refresh_orchestrator.refresh_company",
        supports_point_in_time_reads=True,
        refresh_policy="request_path_or_worker",
        source_ids=("sec_companyfacts",),
        runtime_dataset_keys=("financials",),
    ),
    "price_history": DatasetDefinition(
        dataset_key="price_history",
        source_type="official_market_fallback",
        freshness_ttl_seconds=24 * 60 * 60,
        refresh_cost_class="low",
        refresh_function_path="app.services.sec.refresh_orchestrator.refresh_company",
        supports_point_in_time_reads=True,
        refresh_policy="request_path_or_worker",
        source_ids=("yahoo_finance",),
        runtime_dataset_keys=("prices",),
    ),
    "insider_trades": DatasetDefinition(
        dataset_key="insider_trades",
        source_type="official_sec",
        freshness_ttl_seconds=6 * 60 * 60,
        refresh_cost_class="medium",
        refresh_function_path="app.services.sec.refresh_orchestrator.refresh_company",
        supports_point_in_time_reads=True,
        refresh_policy="request_path_or_worker",
        source_ids=("sec_edgar",),
        runtime_dataset_keys=("insiders",),
    ),
    "form144_filings": DatasetDefinition(
        dataset_key="form144_filings",
        source_type="official_sec",
        freshness_ttl_seconds=6 * 60 * 60,
        refresh_cost_class="medium",
        refresh_function_path="app.services.sec.refresh_orchestrator.refresh_company",
        supports_point_in_time_reads=True,
        refresh_policy="request_path_or_worker",
        source_ids=("sec_edgar",),
        runtime_dataset_keys=("form144",),
    ),
    "institutional_holdings": DatasetDefinition(
        dataset_key="institutional_holdings",
        source_type="official_sec",
        freshness_ttl_seconds=24 * 60 * 60,
        refresh_cost_class="high",
        refresh_function_path="app.services.sec.refresh_orchestrator.refresh_company",
        supports_point_in_time_reads=True,
        refresh_policy="request_path_or_worker",
        source_ids=("sec_edgar",),
        runtime_dataset_keys=("institutional",),
    ),
    "beneficial_ownership": DatasetDefinition(
        dataset_key="beneficial_ownership",
        source_type="official_sec",
        freshness_ttl_seconds=6 * 60 * 60,
        refresh_cost_class="medium",
        refresh_function_path="app.services.sec.refresh_orchestrator.refresh_company",
        supports_point_in_time_reads=True,
        refresh_policy="request_path_or_worker",
        source_ids=("sec_edgar",),
        runtime_dataset_keys=("beneficial_ownership",),
    ),
    "proxy": DatasetDefinition(
        dataset_key="proxy",
        source_type="official_sec",
        freshness_ttl_seconds=24 * 60 * 60,
        refresh_cost_class="high",
        refresh_function_path="app.services.sec.refresh_orchestrator.refresh_company",
        supports_point_in_time_reads=True,
        refresh_policy="request_path_or_worker",
        source_ids=("sec_edgar",),
        runtime_dataset_keys=("proxy",),
    ),
    "events_8k": DatasetDefinition(
        dataset_key="events_8k",
        source_type="official_sec",
        freshness_ttl_seconds=6 * 60 * 60,
        refresh_cost_class="medium",
        refresh_function_path="app.services.sec.refresh_orchestrator.refresh_company",
        supports_point_in_time_reads=True,
        refresh_policy="request_path_or_worker",
        source_ids=("sec_edgar",),
        runtime_dataset_keys=("filings",),
    ),
    "capital_markets": DatasetDefinition(
        dataset_key="capital_markets",
        source_type="official_sec",
        freshness_ttl_seconds=24 * 60 * 60,
        refresh_cost_class="medium",
        refresh_function_path="app.services.capital_markets.refresh_capital_markets_for_company",
        supports_point_in_time_reads=True,
        refresh_policy="request_path_or_worker",
        source_ids=("sec_edgar",),
        runtime_dataset_keys=("capital_markets",),
    ),
    "comment_letters": DatasetDefinition(
        dataset_key="comment_letters",
        source_type="official_sec",
        freshness_ttl_seconds=24 * 60 * 60,
        refresh_cost_class="medium",
        refresh_function_path="app.services.sec.refresh_orchestrator.refresh_company",
        supports_point_in_time_reads=True,
        refresh_policy="request_path_or_worker",
        source_ids=("sec_edgar_corresp",),
        runtime_dataset_keys=("comment_letters",),
    ),
    "earnings_releases": DatasetDefinition(
        dataset_key="earnings_releases",
        source_type="official_sec",
        freshness_ttl_seconds=6 * 60 * 60,
        refresh_cost_class="medium",
        refresh_function_path="app.services.sec.refresh_orchestrator.refresh_company",
        supports_point_in_time_reads=True,
        refresh_policy="request_path_or_worker",
        source_ids=("sec_edgar",),
        runtime_dataset_keys=("earnings",),
    ),
    "capital_structure": DatasetDefinition(
        dataset_key="capital_structure",
        source_type="derived_internal",
        freshness_ttl_seconds=24 * 60 * 60,
        refresh_cost_class="high",
        refresh_function_path="app.services.capital_structure_intelligence.recompute_and_persist_company_capital_structure",
        supports_point_in_time_reads=True,
        refresh_policy="background_worker_only",
        source_ids=("ft_capital_structure_intelligence",),
        runtime_dataset_keys=("capital_structure",),
    ),
    "earnings_models": DatasetDefinition(
        dataset_key="earnings_models",
        source_type="derived_internal",
        freshness_ttl_seconds=24 * 60 * 60,
        refresh_cost_class="high",
        refresh_function_path="app.services.earnings_intelligence.recompute_and_persist_company_earnings_model_points",
        supports_point_in_time_reads=True,
        refresh_policy="background_worker_only",
        source_ids=("ft_model_engine",),
        runtime_dataset_keys=("earnings_models",),
    ),
    "derived_metrics": DatasetDefinition(
        dataset_key="derived_metrics",
        source_type="derived_internal",
        freshness_ttl_seconds=24 * 60 * 60,
        refresh_cost_class="high",
        refresh_function_path="app.services.derived_metrics_mart.recompute_and_persist_company_derived_metrics",
        supports_point_in_time_reads=True,
        refresh_policy="background_worker_only",
        source_ids=("ft_derived_metrics_mart",),
        runtime_dataset_keys=("derived_metrics",),
    ),
    "filing_risk_signals": DatasetDefinition(
        dataset_key="filing_risk_signals",
        source_type="derived_internal",
        freshness_ttl_seconds=24 * 60 * 60,
        refresh_cost_class="medium",
        refresh_function_path="app.services.filing_risk_signals.build_non_timely_filing_signals",
        supports_point_in_time_reads=True,
        refresh_policy="background_worker_only",
        source_ids=("sec_edgar",),
        runtime_dataset_keys=("filing_risk_signals",),
    ),
    "company_research_brief": DatasetDefinition(
        dataset_key="company_research_brief",
        source_type="derived_internal",
        freshness_ttl_seconds=24 * 60 * 60,
        refresh_cost_class="high",
        refresh_function_path="app.services.company_research_brief.recompute_and_persist_company_research_brief",
        supports_point_in_time_reads=True,
        refresh_policy="background_worker_only",
        source_ids=("ft_company_research_brief",),
        runtime_dataset_keys=("company_research_brief",),
    ),
    "charts_dashboard": DatasetDefinition(
        dataset_key="charts_dashboard",
        source_type="derived_internal",
        freshness_ttl_seconds=24 * 60 * 60,
        refresh_cost_class="high",
        refresh_function_path="app.services.company_charts_dashboard.recompute_and_persist_company_charts_dashboard",
        supports_point_in_time_reads=True,
        refresh_policy="background_worker_only",
        source_ids=("ft_company_charts_dashboard",),
        runtime_dataset_keys=("charts_dashboard",),
    ),
    "charts_forecast_accuracy": DatasetDefinition(
        dataset_key="charts_forecast_accuracy",
        source_type="derived_internal",
        freshness_ttl_seconds=24 * 60 * 60,
        refresh_cost_class="high",
        refresh_function_path="app.services.company_charts_dashboard.recompute_and_persist_company_charts_forecast_accuracy",
        supports_point_in_time_reads=True,
        refresh_policy="background_worker_only",
        source_ids=("ft_company_charts_dashboard",),
        runtime_dataset_keys=("charts_forecast_accuracy",),
    ),
    "oil_scenario_overlay": DatasetDefinition(
        dataset_key="oil_scenario_overlay",
        source_type="derived_internal",
        freshness_ttl_seconds=24 * 60 * 60,
        refresh_cost_class="medium",
        refresh_function_path="app.services.oil_scenario_overlay.refresh_company_oil_scenario_overlay",
        supports_point_in_time_reads=True,
        refresh_policy="background_worker_only",
        source_ids=("ft_oil_scenario_overlay",),
        runtime_dataset_keys=("oil_scenario_overlay",),
    ),
    "company_refresh": DatasetDefinition(
        dataset_key="company_refresh",
        source_type="derived_internal",
        freshness_ttl_seconds=24 * 60 * 60,
        refresh_cost_class="high",
        refresh_function_path="app.services.sec.refresh_orchestrator.run_refresh_job",
        supports_point_in_time_reads=False,
        refresh_policy="background_worker_only",
        source_ids=("sec_edgar", "sec_companyfacts"),
        runtime_dataset_keys=("company_refresh",),
    ),
    "sec_frames": DatasetDefinition(
        dataset_key="sec_frames",
        source_type="official_sec",
        freshness_ttl_seconds=24 * 60 * 60,
        refresh_cost_class="high",
        refresh_function_path="app.services.sec.sec_frames.update_sec_frames_cache",
        supports_point_in_time_reads=True,
        refresh_policy="background_worker_only",
        source_ids=("sec_xbrl_frames",),
        runtime_dataset_keys=("sec_frames",),
    ),
}


def iter_dataset_definitions() -> tuple[DatasetDefinition, ...]:
    return tuple(DATASET_REGISTRY.values())


def get_dataset_definition(dataset_key: str) -> DatasetDefinition | None:
    key = str(dataset_key).strip().lower()
    if not key:
        return None
    direct = DATASET_REGISTRY.get(key)
    if direct is not None:
        return direct
    for definition in DATASET_REGISTRY.values():
        if key in definition.runtime_dataset_keys:
            return definition
    return None


def get_dataset_freshness_ttl_seconds(dataset_key: str, *, default_seconds: int) -> int:
    definition = get_dataset_definition(dataset_key)
    if definition is None:
        return int(default_seconds)
    return int(definition.freshness_ttl_seconds)


def get_dataset_refresh_policy(dataset_key: str) -> RefreshPolicy | None:
    definition = get_dataset_definition(dataset_key)
    if definition is None:
        return None
    return definition.refresh_policy


def dataset_source_ids_by_runtime_dataset() -> dict[str, tuple[str, ...]]:
    mapping: dict[str, set[str]] = {}
    for definition in DATASET_REGISTRY.values():
        for runtime_dataset_key in definition.runtime_dataset_keys:
            bucket = mapping.setdefault(runtime_dataset_key, set())
            bucket.update(definition.source_ids)
    return {key: tuple(sorted(values)) for key, values in mapping.items()}


def build_endpoint_freshness_metadata(
    *,
    dataset_key: str,
    refresh_reason: str,
    refresh_triggered: bool,
    job_id: str | None,
    source: str,
) -> dict[str, str | bool | None]:
    # Unknown dataset keys intentionally degrade to conservative stale semantics.
    if refresh_reason == "fresh" and not refresh_triggered:
        freshness = "fresh"
    elif refresh_reason == "missing":
        freshness = "missing"
    else:
        freshness = "stale"

    definition = get_dataset_definition(dataset_key)
    effective_source = source or (definition.source_ids[0] if definition and definition.source_ids else "none")
    return {
        "freshness": freshness,
        "source": effective_source,
        "isStale": freshness != "fresh",
        "refreshQueued": bool(refresh_triggered),
        "jobId": job_id,
    }
