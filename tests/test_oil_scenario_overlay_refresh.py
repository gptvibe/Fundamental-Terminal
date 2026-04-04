from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import app.services.oil_scenario_overlay as overlay_service


def test_oil_scenario_overlay_refresh_persists_official_inputs_and_direct_evidence(monkeypatch):
    checked_at = datetime(2026, 4, 4, tzinfo=timezone.utc)
    company = SimpleNamespace(
        id=7,
        ticker="XOM",
        cik="0000034088",
        name="Exxon Mobil Corporation",
        sector="Energy",
        market_sector="Energy",
        market_industry="Oil & Gas Integrated",
    )
    written_payload: dict[str, object] = {}

    monkeypatch.setattr(overlay_service, "acquire_refresh_lock", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(overlay_service, "release_refresh_lock", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        overlay_service,
        "fetch_official_oil_inputs",
        lambda **_kwargs: SimpleNamespace(
            as_of="2026-04-04",
            spot_history=(
                SimpleNamespace(
                    series_id="wti_spot_history",
                    label="WTI spot history",
                    units="usd_per_barrel",
                    status="ok",
                    points=(SimpleNamespace(label="2026-04-03", value=83.4, units="usd_per_barrel", observation_date="2026-04-03"),),
                    latest_value=83.4,
                    latest_observation_date="2026-04-03",
                ),
            ),
            short_term_baseline=(
                SimpleNamespace(
                    series_id="wti_short_term_baseline",
                    label="WTI short-term official baseline",
                    units="usd_per_barrel",
                    status="ok",
                    points=(SimpleNamespace(label="2026-05", value=82.2, units="usd_per_barrel", observation_date="2026-05"),),
                    latest_value=82.2,
                    latest_observation_date="2026-05",
                ),
            ),
            freshness={"stale_flags": []},
            confidence_flags=("official_oil_ready",),
            provenance=(
                {
                    "source_id": "eia_petroleum_spot_prices",
                    "source_tier": "official_statistical",
                    "display_label": "EIA Petroleum Spot Prices",
                    "url": "https://www.eia.gov/",
                    "default_freshness_ttl_seconds": 86400,
                    "disclosure_note": "Official EIA petroleum spot-price history used for WTI and Brent benchmark normalization.",
                    "role": "primary",
                    "as_of": "2026-04-03",
                    "last_refreshed_at": checked_at,
                },
                {
                    "source_id": "eia_steo",
                    "source_tier": "official_statistical",
                    "display_label": "EIA Short-Term Energy Outlook",
                    "url": "https://www.eia.gov/outlooks/steo/",
                    "default_freshness_ttl_seconds": 86400,
                    "disclosure_note": "Official EIA short-term oil price baseline scenarios.",
                    "role": "primary",
                    "as_of": "2026-05",
                    "last_refreshed_at": checked_at,
                },
            ),
        ),
    )
    monkeypatch.setattr(
        overlay_service,
        "collect_company_oil_evidence",
        lambda *_args, **_kwargs: {
            "status": "partial",
            "checked_at": checked_at.isoformat(),
            "parser_confidence_flags": ["oil_sensitivity_disclosed"],
            "disclosed_sensitivity": {
                "status": "available",
                "benchmark": "brent",
                "oil_price_change_per_bbl": 1.0,
                "annual_after_tax_earnings_change": 650000000.0,
                "annual_after_tax_sensitivity": 650000000.0,
                "metric_basis": "annual_after_tax_earnings_usd",
                "source_url": "https://www.sec.gov/Archives/edgar/data/34088/xom.htm",
                "accession_number": "0000034088-26-000012",
                "filing_form": "10-K",
                "confidence_flags": ["oil_sensitivity_disclosed"],
                "provenance_sources": ["sec_edgar"],
            },
            "diluted_shares": {
                "status": "available",
                "value": 4200000000.0,
                "unit": "shares",
                "source_url": "https://data.sec.gov/api/xbrl/companyfacts/CIK0000034088.json#accn=0000034088-26-000012",
                "accession_number": "0000034088-26-000012",
                "filing_form": "10-K",
                "taxonomy": "us-gaap",
                "tag": "WeightedAverageNumberOfDilutedSharesOutstanding",
                "confidence_flags": ["weighted_average_diluted_shares_companyfacts"],
                "provenance_sources": ["sec_companyfacts"],
            },
            "realized_price_comparison": {
                "status": "not_available",
                "reason": "No clearly structured realized-price-versus-benchmark table was found in the parsed filing text.",
                "benchmark": None,
                "rows": [],
                "confidence_flags": ["realized_vs_benchmark_not_available"],
                "provenance_sources": ["sec_edgar"],
            },
        },
    )
    monkeypatch.setattr(
        overlay_service,
        "upsert_company_oil_scenario_overlay_snapshot",
        lambda *_args, **kwargs: written_payload.update(kwargs["payload"]),
    )

    written = overlay_service.refresh_company_oil_scenario_overlay(object(), company, checked_at=checked_at, job_id="job-1")

    assert written == 1
    assert written_payload["benchmark_series"][0]["series_id"] == "wti_spot_history"
    assert written_payload["direct_company_evidence"]["disclosed_sensitivity"]["status"] == "available"
    assert written_payload["sensitivity"]["status"] == "disclosed"