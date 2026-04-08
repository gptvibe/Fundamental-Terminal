from __future__ import annotations

import json
from datetime import date, datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import app.main as main_module
from app.services.capital_markets import collect_capital_markets_events
from app.services.capital_structure_intelligence import build_capital_structure_snapshots
from app.services.eight_k_events import collect_filing_events
from app.services.earnings_release import collect_earnings_releases
from app.services.proxy_parser import parse_proxy_filing_signals
from app.services.sec_edgar import EdgarNormalizer, FilingMetadata, ParsedFilingInsight, _build_statement_reconciliation, _segment_axis_metadata_from_title


FIXTURES_DIR = Path(__file__).parent / "fixtures"
GOLDEN_DIR = FIXTURES_DIR / "golden"


class _FixtureBackedEarningsClient:
    def __init__(self, payload_by_name: dict[str, str], directory_items: list[dict[str, str]]) -> None:
        self._payload_by_name = payload_by_name
        self._directory_items = directory_items

    def get_filing_directory_index(self, cik: str, accession_number: str):
        return {"directory": {"item": self._directory_items}}

    def get_filing_document_text(self, cik: str, accession_number: str, document_name: str):
        source_url = f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{accession_number.replace('-', '')}/{document_name}"
        return source_url, self._payload_by_name[document_name]


def test_canonical_financial_extraction_golden_fixture() -> None:
    fixture = _load_golden("canonical_financial_extraction.json")
    filing_index = {
        fixture["accession_number"]: FilingMetadata(
            accession_number=fixture["accession_number"],
            form=fixture["filing"]["form"],
            filing_date=_parse_date(fixture["filing"]["filing_date"]),
            report_date=_parse_date(fixture["filing"]["report_date"]),
            primary_document=fixture["filing"]["primary_document"],
        )
    }

    statements = EdgarNormalizer().normalize(fixture["cik"], fixture["companyfacts"], filing_index)

    assert len(statements) == 1
    statement = statements[0]
    expected = fixture["expected"]
    assert statement.filing_type == expected["filing_type"]
    assert statement.period_end == _parse_date(expected["period_end"])
    assert statement.source.endswith(expected["source_suffix"])
    for key, value in expected["data"].items():
        assert statement.data[key] == value


def test_capital_structure_intelligence_golden_fixture() -> None:
    fixture = _load_golden("capital_structure_intelligence.json")
    filing_index = {
        fixture["accession_number"]: FilingMetadata(
            accession_number=fixture["accession_number"],
            form=fixture["filing"]["form"],
            filing_date=_parse_date(fixture["filing"]["filing_date"]),
            report_date=_parse_date(fixture["filing"]["report_date"]),
            primary_document=fixture["filing"]["primary_document"],
        )
    }

    statements = EdgarNormalizer().normalize(fixture["cik"], fixture["companyfacts"], filing_index)

    assert len(statements) == 1
    statement = statements[0]
    for key, value in fixture["expected"]["canonical_data"].items():
        assert statement.data[key] == value

    snapshots = build_capital_structure_snapshots(
        [
                SimpleNamespace(
                    id=1,
                    period_start=statement.period_start,
                    period_end=statement.period_end,
                    filing_type=statement.filing_type,
                    statement_type="canonical_xbrl",
                    source=statement.source,
                    filing_acceptance_at=statement.filing_acceptance_at,
                    last_updated=datetime(2026, 3, 21, tzinfo=timezone.utc),
                last_checked=datetime(2026, 3, 22, tzinfo=timezone.utc),
                data=statement.data,
            )
        ]
    )

    assert len(snapshots) == 1
    latest = snapshots[0]["data"]
    for section_name, expected_payload in fixture["expected"]["snapshot"].items():
        for key, value in expected_payload.items():
            assert latest[section_name][key] == value


def test_earnings_release_parser_golden_fixture() -> None:
    fixture = _load_golden("earnings_release_parsing.json")
    filing = fixture["filings"][0]
    filing_index = {
        filing["accession_number"]: FilingMetadata(
            accession_number=filing["accession_number"],
            form=filing["form"],
            filing_date=_parse_date(filing["filing_date"]),
            report_date=_parse_date(filing["report_date"]),
            primary_document=filing["primary_document"],
            primary_doc_description=filing["primary_doc_description"],
            items=filing["items"],
        )
    }
    client = _FixtureBackedEarningsClient(
        payload_by_name={name: _load_text_fixture(path) for name, path in fixture["payload_by_name"].items()},
        directory_items=fixture["directory_items"],
    )

    releases = collect_earnings_releases(fixture["cik"], filing_index, client=client)

    assert len(releases) == 1
    release = releases[0]
    expected = fixture["expected"]
    assert release.parse_state == expected["parse_state"]
    assert release.exhibit_document == expected["exhibit_document"]
    assert release.exhibit_type == expected["exhibit_type"]
    assert release.reported_period_label == expected["reported_period_label"]
    assert release.reported_period_end == _parse_date(expected["reported_period_end"])
    assert release.revenue == expected["revenue"]
    assert release.operating_income == expected["operating_income"]
    assert release.net_income == expected["net_income"]
    assert release.diluted_eps == expected["diluted_eps"]
    assert release.revenue_guidance_low == expected["revenue_guidance_low"]
    assert release.revenue_guidance_high == expected["revenue_guidance_high"]
    assert release.eps_guidance_low == expected["eps_guidance_low"]
    assert release.eps_guidance_high == expected["eps_guidance_high"]
    assert release.share_repurchase_amount == expected["share_repurchase_amount"]
    assert release.dividend_per_share == expected["dividend_per_share"]
    assert release.source_url.endswith(expected["source_url_suffix"])


def test_proxy_governance_parser_golden_fixture() -> None:
    fixture = _load_golden("proxy_governance_parsing.json")
    payload = _load_text_fixture(fixture["source_fixture"])

    signals = parse_proxy_filing_signals(payload)
    expected = fixture["expected"]

    assert signals.meeting_date == _parse_date(expected["meeting_date"])
    assert signals.executive_comp_table_detected is expected["executive_comp_table_detected"]
    assert signals.vote_item_count == expected["vote_item_count"]
    assert signals.board_nominee_count == expected["board_nominee_count"]

    vote_outcome = signals.vote_outcomes[0]
    expected_outcome = expected["vote_outcomes"][0]
    assert vote_outcome.proposal_number == expected_outcome["proposal_number"]
    assert vote_outcome.for_votes == expected_outcome["for_votes"]
    assert vote_outcome.against_votes == expected_outcome["against_votes"]
    assert vote_outcome.abstain_votes == expected_outcome["abstain_votes"]
    assert vote_outcome.broker_non_votes == expected_outcome["broker_non_votes"]

    expected_exec = expected["named_exec_rows"][0]
    matching_rows = [row for row in signals.named_exec_rows if expected_exec["executive_name_contains"] in row.executive_name]
    assert matching_rows
    assert matching_rows[0].salary == expected_exec["salary"]
    assert matching_rows[0].total_compensation == expected_exec["total_compensation"]


def test_capital_markets_and_event_classification_golden_fixture() -> None:
    fixture = _load_golden("capital_markets_event_classification.json")

    capital_index = {
        item["accession_number"]: FilingMetadata(
            accession_number=item["accession_number"],
            form=item["form"],
            filing_date=_parse_date(item["filing_date"]),
            report_date=_parse_date(item["report_date"]),
            primary_document=item["primary_document"],
            primary_doc_description=item["primary_doc_description"],
        )
        for item in fixture["capital_filings"]
    }
    capital_rows = collect_capital_markets_events(fixture["cik"], capital_index)
    actual_capital_rows = sorted(
        [
        {
            "form": row.form,
            "event_type": row.event_type,
            "security_type": row.security_type,
            "offering_amount": row.offering_amount,
            "shelf_size": row.shelf_size,
            "is_late_filer": row.is_late_filer,
        }
        for row in capital_rows
        ],
        key=lambda item: item["form"],
    )
    expected_capital_rows = sorted(fixture["expected"]["capital_markets"], key=lambda item: item["form"])
    assert actual_capital_rows == expected_capital_rows

    event_index = {
        item["accession_number"]: FilingMetadata(
            accession_number=item["accession_number"],
            form=item["form"],
            filing_date=_parse_date(item["filing_date"]),
            report_date=_parse_date(item["report_date"]),
            primary_document=item["primary_document"],
            primary_doc_description=item["primary_doc_description"],
            items=item["items"],
        )
        for item in fixture["event_filings"]
    }
    event_rows = collect_filing_events(fixture["cik"], event_index)
    actual_by_item = {
        row.item_code: {
            "category": row.category,
            "key_amounts": list(row.key_amounts),
            "exhibit_references": list(row.exhibit_references),
        }
        for row in event_rows
    }
    assert actual_by_item == fixture["expected"]["filing_events"]


def test_filing_parser_insight_serialization_regression() -> None:
    statement = SimpleNamespace(
        accession_number="0000320193-26-000010",
        filing_type="10-Q",
        period_start=date(2025, 10, 1),
        period_end=date(2025, 12, 31),
        source="https://data.sec.gov/api/xbrl/companyfacts/CIK0000320193.json",
        last_updated=datetime(2026, 3, 21, 12, 0, tzinfo=timezone.utc),
        last_checked=datetime(2026, 3, 22, 8, 30, tzinfo=timezone.utc),
        data={
            "revenue": 124_300_000_000,
            "net_income": 36_300_000_000,
            "operating_income": 42_100_000_000,
            "segments": [
                {"name": "Products", "revenue": 98_100_000_000},
                {"name": "Services", "revenue": 26_200_000_000},
            ],
        },
    )

    payload = main_module._serialize_filing_parser_insight(statement)

    assert payload.model_dump(mode="json") == {
        "accession_number": None,
        "filing_type": "10-Q",
        "period_start": "2025-10-01",
        "period_end": "2025-12-31",
        "source": "https://data.sec.gov/api/xbrl/companyfacts/CIK0000320193.json",
        "last_updated": "2026-03-21T12:00:00Z",
        "last_checked": "2026-03-22T08:30:00Z",
        "revenue": 124300000000,
        "net_income": 36300000000,
        "operating_income": 42100000000,
        "segments": [
            {"name": "Products", "revenue": 98100000000},
            {"name": "Services", "revenue": 26200000000},
        ],
        "mdna": None,
        "footnotes": [],
        "non_gaap": {
            "mention_count": 0,
            "terms": [],
            "reconciliation_mentions": 0,
            "has_reconciliation": False,
            "source": None,
            "excerpt": None,
        },
        "controls": {
            "auditor_names": [],
            "auditor_change_terms": [],
            "control_terms": [],
            "material_weakness": False,
            "ineffective_controls": False,
            "non_reliance": False,
            "source": None,
            "excerpt": None,
        },
    }


def test_financial_reconciliation_preserves_exact_tags_and_periods() -> None:
    statement = SimpleNamespace(
        filing_type="10-K",
        period_end=date(2025, 12, 31),
        data={
            "revenue": 1_000,
            "net_income": 200,
            "operating_income": 260,
        },
        selected_facts={
            "revenue": {
                "accession_number": "0000123456-26-000010",
                "form": "10-K",
                "taxonomy": "us-gaap",
                "tag": "Revenues",
                "unit": "USD",
                "source": "https://data.sec.gov/api/xbrl/companyfacts/CIK0000123456.json",
                "filed_at": date(2026, 2, 20),
                "period_start": date(2025, 1, 1),
                "period_end": date(2025, 12, 31),
                "value": 1_000,
            },
            "net_income": {
                "accession_number": "0000123456-26-000010",
                "form": "10-K",
                "taxonomy": "us-gaap",
                "tag": "NetIncomeLoss",
                "unit": "USD",
                "source": "https://data.sec.gov/api/xbrl/companyfacts/CIK0000123456.json",
                "filed_at": date(2026, 2, 20),
                "period_start": date(2025, 1, 1),
                "period_end": date(2025, 12, 31),
                "value": 200,
            },
        },
    )
    parser_insight = ParsedFilingInsight(
        accession_number="0000123456-26-000010",
        filing_type="10-K",
        period_start=date(2025, 1, 1),
        period_end=date(2025, 12, 31),
        source="https://www.sec.gov/Archives/edgar/data/123456/000012345626000010/form10k.htm",
        data={
            "revenue": 950,
            "net_income": 200,
            "operating_income": 240,
        },
    )

    reconciliation = _build_statement_reconciliation(
        statement,
        parser_insight,
        datetime(2026, 3, 28, 9, 0, tzinfo=timezone.utc),
    )

    revenue = next(item for item in reconciliation["comparisons"] if item["metric_key"] == "revenue")
    assert reconciliation["status"] == "disagreement"
    assert reconciliation["matched_accession_number"] == "0000123456-26-000010"
    assert revenue["companyfacts_fact"]["tag"] == "Revenues"
    assert revenue["companyfacts_fact"]["period_start"] == date(2025, 1, 1)
    assert revenue["filing_parser_fact"]["period_end"] == date(2025, 12, 31)
    assert revenue["status"] == "disagreement"
    assert reconciliation["confidence_penalty"] > 0


def test_segment_axis_metadata_distinguishes_business_and_geography_titles() -> None:
    assert _segment_axis_metadata_from_title("Net sales by geographic region")[2] == "geographic"
    assert _segment_axis_metadata_from_title("Revenue by reportable operating segments")[2] == "business"


def _load_golden(name: str) -> dict:
    return json.loads((GOLDEN_DIR / name).read_text(encoding="utf-8"))


def _load_text_fixture(name: str) -> str:
    return (FIXTURES_DIR / name).read_text(encoding="utf-8")


def _parse_date(value: str) -> date:
    return date.fromisoformat(value)
