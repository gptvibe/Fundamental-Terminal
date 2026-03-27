from __future__ import annotations

from datetime import datetime, timezone

from app.source_registry import SourceUsage, build_provenance_entries, build_source_mix, infer_source_id


def test_infer_source_id_maps_supported_provider_hints() -> None:
    assert infer_source_id("https://data.sec.gov/api/xbrl/companyfacts/CIK0000320193.json") == "sec_companyfacts"
    assert infer_source_id("https://www.sec.gov/Archives/edgar/data/320193/10-k.htm") == "sec_edgar"
    assert infer_source_id("https://finance.yahoo.com/quote/AAPL") == "yahoo_finance"
    assert infer_source_id("U.S. Treasury Daily Par Yield Curve") == "us_treasury_daily_par_yield_curve"
    assert infer_source_id("https://fred.stlouisfed.org/series/T10YIE") == "fred"
    assert infer_source_id("Manual Override") == "manual_override"


def test_build_provenance_entries_merges_roles_and_timestamps() -> None:
    refreshed_early = datetime(2026, 3, 20, tzinfo=timezone.utc)
    refreshed_late = datetime(2026, 3, 22, tzinfo=timezone.utc)

    entries = build_provenance_entries(
        [
            SourceUsage(
                source_id="sec_companyfacts",
                role="supplemental",
                as_of="2025-09-30",
                last_refreshed_at=refreshed_early,
            ),
            SourceUsage(
                source_id="sec_companyfacts",
                role="primary",
                as_of="2025-12-31",
                last_refreshed_at=refreshed_late,
            ),
            SourceUsage(
                source_id="yahoo_finance",
                role="fallback",
                as_of="2026-03-21",
                last_refreshed_at=refreshed_early,
            ),
        ]
    )

    by_source = {entry["source_id"]: entry for entry in entries}
    sec_entry = by_source["sec_companyfacts"]
    assert sec_entry["role"] == "primary"
    assert sec_entry["as_of"] == "2025-12-31"
    assert sec_entry["last_refreshed_at"] == refreshed_late
    assert by_source["yahoo_finance"]["role"] == "fallback"


def test_build_source_mix_flags_fallback_presence() -> None:
    entries = build_provenance_entries(
        [
            SourceUsage(source_id="ft_model_engine", role="derived", as_of="2025-12-31"),
            SourceUsage(source_id="sec_companyfacts", role="primary", as_of="2025-12-31"),
            SourceUsage(source_id="yahoo_finance", role="fallback", as_of="2026-03-21"),
        ]
    )

    source_mix = build_source_mix(entries)

    assert source_mix["source_ids"] == ["sec_companyfacts", "ft_model_engine", "yahoo_finance"]
    assert source_mix["primary_source_ids"] == ["sec_companyfacts"]
    assert source_mix["fallback_source_ids"] == ["yahoo_finance"]
    assert source_mix["official_only"] is False
