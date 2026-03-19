from __future__ import annotations

import argparse
import json
import logging
import re
import time
import xml.etree.ElementTree as ET
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Any

import httpx
from bs4 import BeautifulSoup
from sqlalchemy import Select, case, func, or_, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.config import settings
from app.db.session import SessionLocal, get_engine
from app.model_engine import precompute_core_models
from app.models import BeneficialOwnershipReport, Company, FinancialStatement, InsiderTrade
from app.services.filing_parser import FilingParser, ParsedFilingInsight
from app.services.institutional_holdings import (
    get_company_institutional_holdings_last_checked,
    refresh_company_institutional_holdings,
)
from app.services.market_data import (
    MarketDataClient,
    MarketProfile,
    get_company_price_last_checked,
    touch_company_price_history,
    upsert_price_history,
)
from app.services.sec_cache import prune_sec_cache_periodic, sec_http_cache
from app.services.status_stream import JobReporter

logger = logging.getLogger(__name__)

SUPPORTED_FORMS = {"10-K", "10-Q", "20-F", "40-F", "6-K"}
ANNUAL_FORMS = {"10-K", "20-F", "40-F"}
INTERIM_FORMS = {"10-Q", "6-K"}
CANONICAL_STATEMENT_TYPE = "canonical_xbrl"
FILING_PARSER_STATEMENT_TYPE = "filing_parser"

CANONICAL_FACTS: dict[str, list[tuple[str, list[str]]]] = {
    "revenue": [
        (
            "us-gaap",
            [
                "RevenueFromContractWithCustomerExcludingAssessedTax",
                "SalesRevenueNet",
                "Revenues",
                "RevenueFromContractWithCustomerIncludingAssessedTax",
                "SalesRevenueServicesNet",
                "SalesRevenueGoodsNet",
            ],
        ),
        ("ifrs-full", ["Revenue"]),
    ],
    "gross_profit": [
        ("us-gaap", ["GrossProfit"]),
        ("ifrs-full", ["GrossProfit"]),
    ],
    "operating_income": [
        ("us-gaap", ["OperatingIncomeLoss"]),
        ("ifrs-full", ["ProfitLossFromOperatingActivities"]),
    ],
    "net_income": [
        ("us-gaap", ["NetIncomeLoss", "ProfitLoss"]),
        ("ifrs-full", ["ProfitLoss"]),
    ],
    "total_assets": [
        ("us-gaap", ["Assets"]),
        ("ifrs-full", ["Assets"]),
    ],
    "current_assets": [
        ("us-gaap", ["AssetsCurrent"]),
        ("ifrs-full", ["CurrentAssets"]),
    ],
    "total_liabilities": [
        ("us-gaap", ["Liabilities"]),
        ("ifrs-full", ["Liabilities"]),
    ],
    "current_liabilities": [
        ("us-gaap", ["LiabilitiesCurrent"]),
        ("ifrs-full", ["CurrentLiabilities"]),
    ],
    "retained_earnings": [
        ("us-gaap", ["RetainedEarningsAccumulatedDeficit"]),
        ("ifrs-full", ["RetainedEarnings"]),
    ],
    "sga": [
        (
            "us-gaap",
            [
                "SellingGeneralAndAdministrativeExpense",
            ],
        ),
    ],
    "research_and_development": [
        (
            "us-gaap",
            [
                "ResearchAndDevelopmentExpense",
                "ResearchAndDevelopmentExpenseExcludingAcquiredInProcessCost",
            ],
        ),
        (
            "ifrs-full",
            [
                "ResearchAndDevelopmentExpense",
            ],
        ),
    ],
    "interest_expense": [
        (
            "us-gaap",
            [
                "InterestExpenseExpense",
                "InterestExpenseAndOther",
                "InterestExpense",
            ],
        ),
        (
            "ifrs-full",
            [
                "FinanceCosts",
                "InterestExpense",
            ],
        ),
    ],
    "income_tax_expense": [
        (
            "us-gaap",
            [
                "IncomeTaxExpenseBenefit",
                "IncomeTaxes",
            ],
        ),
        (
            "ifrs-full",
            [
                "IncomeTaxExpenseContinuingOperations",
                "IncomeTaxExpense",
            ],
        ),
    ],
    "inventory": [
        ("us-gaap", ["InventoryNet"]),
        ("ifrs-full", ["Inventories"]),
    ],
    "accounts_receivable": [
        (
            "us-gaap",
            [
                "AccountsReceivableNetCurrent",
                "ReceivablesNetCurrent",
            ],
        ),
        (
            "ifrs-full",
            [
                "TradeAndOtherCurrentReceivables",
                "CurrentTradeReceivables",
            ],
        ),
    ],
    "goodwill_and_intangibles": [
        (
            "us-gaap",
            [
                "FiniteLivedIntangibleAssetsNet",
                "GoodwillAndIntangibleAssetsNet",
                "OtherThanGoodwillIntangibleAssetsNet",
            ],
        ),
        (
            "ifrs-full",
            [
                "IntangibleAssetsOtherThanGoodwill",
                "GoodwillAndOtherIntangibleAssets",
            ],
        ),
    ],
    "long_term_debt": [
        (
            "us-gaap",
            [
                "LongTermDebtNoncurrent",
                "LongTermDebtAndCapitalLeaseObligations",
                "LongTermDebt",
            ],
        ),
        (
            "ifrs-full",
            [
                "NoncurrentBorrowings",
                "BorrowingsNoncurrent",
            ],
        ),
    ],
    "lease_liabilities": [
        (
            "us-gaap",
            [
                "OperatingLeaseLiabilityNoncurrent",
                "FinanceLeaseLiabilityNoncurrent",
                "OperatingLeaseLiability",
            ],
        ),
        (
            "ifrs-full",
            [
                "LeaseLiabilitiesNoncurrent",
                "LeaseLiabilities",
            ],
        ),
    ],
    "operating_cash_flow": [
        (
            "us-gaap",
            [
                "NetCashProvidedByUsedInOperatingActivities",
                "NetCashProvidedByUsedInOperatingActivitiesContinuingOperations",
            ],
        ),
        ("ifrs-full", ["CashFlowsFromUsedInOperatingActivities"]),
    ],
    "acquisitions": [
        (
            "us-gaap",
            [
                "PaymentsToAcquireBusinessesNetOfCashAcquired",
                "BusinessAcquisitionNetOfCashAcquired",
                "PaymentsToAcquireSubsidiariesAndOtherBusinesses",
            ],
        ),
        (
            "ifrs-full",
            [
                "PaymentsToAcquireSubsidiariesNetOfCashAcquired",
                "CashFlowsUsedInObtainingControlOfSubsidiariesOrOtherBusinesses",
            ],
        ),
    ],
    "dividends": [
        (
            "us-gaap",
            [
                "PaymentsOfDividends",
                "PaymentsOfOrdinaryDividends",
                "PaymentsOfDividendsCommonStock",
            ],
        ),
        (
            "ifrs-full",
            [
                "DividendsPaidClassifiedAsFinancingActivities",
                "DividendsPaid",
            ],
        ),
    ],
    "share_buybacks": [
        (
            "us-gaap",
            [
                "PaymentsForRepurchaseOfCommonStock",
                "PaymentsForRepurchaseOfEquity",
                "PaymentsForRepurchaseOfTreasuryStock",
            ],
        ),
        (
            "ifrs-full",
            [
                "PaymentsToAcquireOrRedeemEntitysShares",
            ],
        ),
    ],
    "stock_based_compensation": [
        (
            "us-gaap",
            [
                "ShareBasedCompensation",
                "AllocatedShareBasedCompensationExpense",
            ],
        ),
        (
            "ifrs-full",
            [
                "SharebasedPaymentExpense",
            ],
        ),
    ],
    "eps": [
        (
            "us-gaap",
            [
                "EarningsPerShareDiluted",
                "EarningsPerShareBasicAndDiluted",
                "EarningsPerShareBasic",
            ],
        ),
        (
            "ifrs-full",
            [
                "DilutedEarningsLossPerShare",
                "BasicEarningsLossPerShare",
            ],
        ),
    ],
    "shares_outstanding": [
        (
            "us-gaap",
            [
                "CommonStockSharesOutstanding",
            ],
        ),
        (
            "dei",
            [
                "EntityCommonStockSharesOutstanding",
            ],
        ),
    ],
    "weighted_average_diluted_shares": [
        (
            "us-gaap",
            [
                "WeightedAverageNumberOfDilutedSharesOutstanding",
                "WeightedAverageNumberOfShareOutstandingBasicAndDiluted",
            ],
        ),
        (
            "ifrs-full",
            [
                "WeightedAverageNumberOfOrdinarySharesOutstandingDiluted",
            ],
        ),
    ],
}

CAPEX_FACTS: list[tuple[str, list[str]]] = [
    (
        "us-gaap",
        [
            "PaymentsToAcquirePropertyPlantAndEquipment",
            "PropertyPlantAndEquipmentAdditions",
            "PaymentsToAcquireProductiveAssets",
            "CapitalExpendituresIncurredButNotYetPaid",
        ],
    ),
    (
        "ifrs-full",
        [
            "PurchaseOfPropertyPlantAndEquipmentClassifiedAsInvestingActivities",
            "PurchaseOfIntangibleAssetsClassifiedAsInvestingActivities",
        ],
    ),
]

DEBT_ISSUANCE_FACTS: list[tuple[str, list[str]]] = [
    (
        "us-gaap",
        [
            "ProceedsFromIssuanceOfLongTermDebt",
            "ProceedsFromDebtNetOfDebtIssueCosts",
            "ProceedsFromIssuanceOfDebt",
        ],
    ),
    (
        "ifrs-full",
        [
            "ProceedsFromBorrowings",
        ],
    ),
]

DEBT_REPAYMENT_FACTS: list[tuple[str, list[str]]] = [
    (
        "us-gaap",
        [
            "RepaymentsOfLongTermDebt",
            "RepaymentsOfDebt",
            "RepaymentsOfDebtAndCapitalLeaseObligations",
        ],
    ),
    (
        "ifrs-full",
        [
            "RepaymentsOfBorrowings",
        ],
    ),
]


@dataclass(slots=True)
class CompanyIdentity:
    cik: str
    ticker: str
    name: str
    exchange: str | None = None
    sector: str | None = None
    market_sector: str | None = None
    market_industry: str | None = None


@dataclass(slots=True)
class FilingMetadata:
    accession_number: str
    form: str | None = None
    filing_date: date | None = None
    report_date: date | None = None
    primary_document: str | None = None
    primary_doc_description: str | None = None
    items: str | None = None


@dataclass(slots=True)
class FactCandidate:
    metric: str
    accession_number: str
    form: str
    value: int | float
    taxonomy: str
    tag: str
    tag_rank: int
    filed_at: date | None = None
    period_start: date | None = None
    period_end: date | None = None


@dataclass(slots=True)
class SegmentRevenueCandidate:
    accession_number: str
    form: str
    value: int | float
    taxonomy: str
    tag: str
    tag_rank: int
    segment_id: str
    segment_name: str
    axis_key: str
    axis_label: str
    kind: str
    filed_at: date | None = None
    period_start: date | None = None
    period_end: date | None = None


@dataclass(slots=True)
class NormalizedStatement:
    accession_number: str
    filing_type: str
    period_start: date
    period_end: date
    source: str
    data: dict[str, Any]


@dataclass(slots=True)
class NormalizedInsiderTrade:
    accession_number: str
    filing_type: str
    filing_date: date | None
    transaction_index: int
    insider_name: str
    role: str | None
    transaction_date: date | None
    action: str
    shares: float | None
    price: float | None
    value: float | None
    ownership_after: float | None
    security_title: str | None
    is_derivative: bool | None
    ownership_nature: str | None
    exercise_price: float | None
    expiration_date: date | None
    footnote_tags: list[str] | None
    transaction_code: str | None
    is_10b5_1: bool
    source: str


@dataclass(slots=True)
class IngestionResult:
    identifier: str
    company_id: int
    cik: str
    ticker: str
    status: str
    statements_written: int = 0
    insider_trades_written: int = 0
    institutional_holdings_written: int = 0
    beneficial_ownership_written: int = 0
    price_points_written: int = 0
    fetched_from_sec: bool = False
    last_checked: datetime | None = None
    detail: str | None = None


@dataclass(slots=True)
class StatementAccumulator:
    accession_number: str
    filing_type: str
    filed_at: date | None = None
    report_date: date | None = None
    source: str = ""
    metric_candidates: dict[str, list[FactCandidate]] = field(default_factory=dict)
    segment_revenue_candidates: list[SegmentRevenueCandidate] = field(default_factory=list)
    capex_candidates: list[FactCandidate] = field(default_factory=list)
    debt_issuance_candidates: list[FactCandidate] = field(default_factory=list)
    debt_repayment_candidates: list[FactCandidate] = field(default_factory=list)
    duration_candidates: list[tuple[date, date]] = field(default_factory=list)
    instant_period_ends: list[date] = field(default_factory=list)


class EdgarClient:
    def __init__(self) -> None:
        self._http = httpx.Client(
            headers={
                "User-Agent": settings.sec_user_agent,
                "Accept": "application/json",
                "Accept-Encoding": "gzip, deflate",
            },
            follow_redirects=True,
            timeout=settings.sec_timeout_seconds,
        )
        self._last_request_monotonic = 0.0
        self._company_tickers_cache: list[dict[str, Any]] | None = None

    def _request(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        params = kwargs.get("params")
        headers = kwargs.get("headers")
        cached_response = sec_http_cache.get(method, url, params=params, headers=headers)
        if cached_response is not None:
            return cached_response

        max_retries = settings.sec_max_retries
        backoff = settings.sec_retry_backoff_seconds
        attempt = 0
        while True:
            self._throttle()
            response = self._http.request(method, url, **kwargs)
            self._last_request_monotonic = time.monotonic()
            if response.status_code in {429, 500, 502, 503, 504} and attempt < max_retries - 1:
                retry_after = response.headers.get("retry-after")
                wait = _retry_wait(retry_after, backoff, attempt)
                response.close()
                time.sleep(wait)
                attempt += 1
                continue
            response.raise_for_status()
            sec_http_cache.put(method, url, response, params=params, headers=headers)
            return response

    def close(self) -> None:
        self._http.close()

    def _throttle(self) -> None:
        elapsed = time.monotonic() - self._last_request_monotonic
        wait_for = settings.sec_min_request_interval_seconds - elapsed
        if wait_for > 0:
            time.sleep(wait_for)

    def _get_json(self, url: str) -> dict[str, Any]:
        return self._request("GET", url).json()

    def _get_text(self, url: str) -> str:
        return self._request("GET", url).text

    @contextmanager
    def stream_document(self, url: str):
        response = self._request("GET", url)
        try:
            yield response
        finally:
            response.close()

    def get_company_tickers(self) -> list[dict[str, Any]]:
        global _ticker_cache, _ticker_cache_loaded_at
        if self._company_tickers_cache is not None:
            return self._company_tickers_cache

        now = time.monotonic()
        if (
            _ticker_cache is not None
            and _ticker_cache_loaded_at is not None
            and now - _ticker_cache_loaded_at < settings.sec_ticker_cache_ttl_seconds
        ):
            self._company_tickers_cache = _ticker_cache
            return self._company_tickers_cache

        payload = self._get_json(settings.sec_ticker_lookup_url)
        if isinstance(payload, dict):
            values = list(payload.values())
        elif isinstance(payload, list):
            values = payload
        else:
            raise ValueError("Unexpected SEC ticker payload shape")

        self._company_tickers_cache = [item for item in values if isinstance(item, dict)]
        _ticker_cache = self._company_tickers_cache
        _ticker_cache_loaded_at = now
        return self._company_tickers_cache

    def resolve_company(self, identifier: str) -> CompanyIdentity:
        lookup = re.sub(r"^cik\s*[:#-]?\s*", "", identifier.strip(), flags=re.IGNORECASE)
        if not lookup:
            raise ValueError("Company identifier is required")

        tickers = self.get_company_tickers()
        if lookup.isdigit():
            cik = lookup.zfill(10)
            for item in tickers:
                item_cik = str(item.get("cik_str", "")).zfill(10)
                if item_cik == cik:
                    return CompanyIdentity(
                        cik=cik,
                        ticker=str(item.get("ticker", cik)),
                        name=str(item.get("title", cik)),
                    )

            submissions = self.get_submissions(cik)
            return CompanyIdentity(
                cik=cik,
                ticker=((submissions.get("tickers") or [cik])[0]),
                name=str(submissions.get("name", cik)),
                exchange=((submissions.get("exchanges") or [None])[0]),
                sector=submissions.get("sicDescription"),
            )

        normalized_lookup = _normalize_identifier(lookup)
        exact_name_match: CompanyIdentity | None = None

        for item in tickers:
            ticker = str(item.get("ticker", "")).upper()
            title = str(item.get("title", ""))
            cik = str(item.get("cik_str", "")).zfill(10)
            if ticker == lookup.upper():
                return CompanyIdentity(cik=cik, ticker=ticker, name=title)
            if _normalize_identifier(title) == normalized_lookup and exact_name_match is None:
                exact_name_match = CompanyIdentity(cik=cik, ticker=ticker, name=title)

        if exact_name_match is not None:
            return exact_name_match

        raise ValueError(f"Unable to resolve SEC company for '{identifier}'")

    def get_submissions(self, cik: str) -> dict[str, Any]:
        return self._get_json(f"{settings.sec_submissions_base_url}/CIK{cik}.json")

    def get_companyfacts(self, cik: str) -> dict[str, Any]:
        return self._get_json(f"{settings.sec_companyfacts_base_url}/CIK{cik}.json")

    def build_filing_index(self, submissions: dict[str, Any]) -> dict[str, FilingMetadata]:
        filing_index: dict[str, FilingMetadata] = {}
        filings_root = submissions.get("filings", {})
        recent = filings_root.get("recent", {})
        self._ingest_columnar_filings(recent, filing_index)

        for extra_file in filings_root.get("files", []) or []:
            name = extra_file.get("name")
            if not name:
                continue
            extra_payload = self._get_json(f"{settings.sec_submissions_base_url}/{name}")
            if isinstance(extra_payload, dict) and "filings" in extra_payload:
                extra_payload = extra_payload.get("filings", {}).get("recent", {})
            self._ingest_columnar_filings(extra_payload, filing_index)

        return filing_index

    def _ingest_columnar_filings(
        self,
        payload: dict[str, Any],
        filing_index: dict[str, FilingMetadata],
    ) -> None:
        if not isinstance(payload, dict):
            return

        arrays = {key: value for key, value in payload.items() if isinstance(value, list)}
        if not arrays:
            return

        row_count = max(len(values) for values in arrays.values())
        for position in range(row_count):
            accession_number = _value_at(arrays.get("accessionNumber"), position)
            if not accession_number:
                continue

            filing_index[accession_number] = FilingMetadata(
                accession_number=accession_number,
                form=_value_at(arrays.get("form"), position),
                filing_date=_parse_date(_value_at(arrays.get("filingDate"), position)),
                report_date=_parse_date(_value_at(arrays.get("reportDate"), position)),
                primary_document=_value_at(arrays.get("primaryDocument"), position),
                primary_doc_description=_value_at(arrays.get("primaryDocDescription"), position),
                items=_value_at(arrays.get("items"), position),
            )

    def get_filing_directory_index(self, cik: str, accession_number: str) -> dict[str, Any]:
        accession_compact = accession_number.replace("-", "")
        numeric_cik = str(int(cik))
        return self._get_json(f"https://www.sec.gov/Archives/edgar/data/{numeric_cik}/{accession_compact}/index.json")

    def get_form4_xml(self, cik: str, filing_metadata: FilingMetadata) -> tuple[str, str]:
        accession_compact = filing_metadata.accession_number.replace("-", "")
        numeric_cik = str(int(cik))
        filing_base_url = f"https://www.sec.gov/Archives/edgar/data/{numeric_cik}/{accession_compact}"

        candidate_names: list[str] = []
        primary_document = (filing_metadata.primary_document or "").strip()
        if primary_document.lower().endswith(".xml"):
            candidate_names.append(primary_document)

        directory_index = self.get_filing_directory_index(cik, filing_metadata.accession_number)
        for item in directory_index.get("directory", {}).get("item", []) or []:
            if not isinstance(item, dict):
                continue
            name = str(item.get("name") or "").strip()
            if name.lower().endswith(".xml"):
                candidate_names.append(name)

        ranked_candidates = sorted({name for name in candidate_names if name}, key=lambda name: _form4_xml_priority(name, primary_document))
        for name in ranked_candidates:
            source_url = f"{filing_base_url}/{name}"
            payload = self._get_text(source_url)
            if "<ownershipDocument" in payload:
                return source_url, payload

        raise ValueError(f"Unable to locate raw Form 4 XML for accession {filing_metadata.accession_number}")

    def get_filing_document_text(self, cik: str, accession_number: str, document_name: str) -> tuple[str, str]:
        accession_compact = accession_number.replace("-", "")
        numeric_cik = str(int(cik))
        source_url = f"https://www.sec.gov/Archives/edgar/data/{numeric_cik}/{accession_compact}/{document_name}"
        return source_url, self._get_text(source_url)


class EdgarNormalizer:
    def normalize(
        self,
        cik: str,
        companyfacts: dict[str, Any],
        filing_index: dict[str, FilingMetadata],
    ) -> list[NormalizedStatement]:
        facts_root = companyfacts.get("facts", {})
        statements: dict[str, StatementAccumulator] = {}

        for metric, taxonomy_groups in CANONICAL_FACTS.items():
            self._collect_metric_candidates(
                metric=metric,
                taxonomy_groups=taxonomy_groups,
                facts_root=facts_root,
                filing_index=filing_index,
                statements=statements,
                cik=cik,
            )

        self._collect_segment_revenue_candidates(
            facts_root=facts_root,
            filing_index=filing_index,
            statements=statements,
            cik=cik,
        )
        self._collect_capex_candidates(
            facts_root=facts_root,
            filing_index=filing_index,
            statements=statements,
            cik=cik,
        )
        self._collect_debt_change_candidates(
            facts_root=facts_root,
            filing_index=filing_index,
            statements=statements,
            cik=cik,
        )

        normalized: list[NormalizedStatement] = []
        for accumulator in statements.values():
            statement = self._finalize_statement(accumulator)
            if statement is not None:
                normalized.append(statement)

        normalized.sort(key=lambda statement: (statement.period_end, statement.filing_type, statement.accession_number))
        return normalized

    def _collect_metric_candidates(
        self,
        metric: str,
        taxonomy_groups: list[tuple[str, list[str]]],
        facts_root: dict[str, Any],
        filing_index: dict[str, FilingMetadata],
        statements: dict[str, StatementAccumulator],
        cik: str,
    ) -> None:
        tag_rank = 0
        for taxonomy, tags in taxonomy_groups:
            taxonomy_root = facts_root.get(taxonomy, {})
            if not isinstance(taxonomy_root, dict):
                tag_rank += len(tags)
                continue

            for tag in tags:
                fact_payload = taxonomy_root.get(tag, {})
                for observation in _iter_fact_observations(metric, fact_payload):
                    candidate = _build_fact_candidate(
                        metric=metric,
                        taxonomy=taxonomy,
                        tag=tag,
                        tag_rank=tag_rank,
                        observation=observation,
                        filing_index=filing_index,
                    )
                    if candidate is None:
                        continue

                    accumulator = statements.setdefault(
                        candidate.accession_number,
                        _new_accumulator(
                            cik=cik,
                            accession_number=candidate.accession_number,
                            filing_metadata=filing_index.get(candidate.accession_number),
                            fallback_form=candidate.form,
                        ),
                    )
                    accumulator.metric_candidates.setdefault(metric, []).append(candidate)
                    _collect_period_candidate(accumulator, candidate)

                tag_rank += 1

    def _collect_capex_candidates(
        self,
        facts_root: dict[str, Any],
        filing_index: dict[str, FilingMetadata],
        statements: dict[str, StatementAccumulator],
        cik: str,
    ) -> None:
        tag_rank = 0
        for taxonomy, tags in CAPEX_FACTS:
            taxonomy_root = facts_root.get(taxonomy, {})
            if not isinstance(taxonomy_root, dict):
                tag_rank += len(tags)
                continue

            for tag in tags:
                fact_payload = taxonomy_root.get(tag, {})
                for observation in _iter_monetary_observations(fact_payload):
                    candidate = _build_fact_candidate(
                        metric="free_cash_flow",
                        taxonomy=taxonomy,
                        tag=tag,
                        tag_rank=tag_rank,
                        observation=observation,
                        filing_index=filing_index,
                    )
                    if candidate is None:
                        continue

                    accumulator = statements.setdefault(
                        candidate.accession_number,
                        _new_accumulator(
                            cik=cik,
                            accession_number=candidate.accession_number,
                            filing_metadata=filing_index.get(candidate.accession_number),
                            fallback_form=candidate.form,
                        ),
                    )
                    accumulator.capex_candidates.append(candidate)
                    _collect_period_candidate(accumulator, candidate)

                tag_rank += 1

    def _collect_debt_change_candidates(
        self,
        facts_root: dict[str, Any],
        filing_index: dict[str, FilingMetadata],
        statements: dict[str, StatementAccumulator],
        cik: str,
    ) -> None:
        self._collect_special_candidates(
            taxonomy_groups=DEBT_ISSUANCE_FACTS,
            facts_root=facts_root,
            filing_index=filing_index,
            statements=statements,
            cik=cik,
            target="debt_issuance_candidates",
        )
        self._collect_special_candidates(
            taxonomy_groups=DEBT_REPAYMENT_FACTS,
            facts_root=facts_root,
            filing_index=filing_index,
            statements=statements,
            cik=cik,
            target="debt_repayment_candidates",
        )

    def _collect_special_candidates(
        self,
        taxonomy_groups: list[tuple[str, list[str]]],
        facts_root: dict[str, Any],
        filing_index: dict[str, FilingMetadata],
        statements: dict[str, StatementAccumulator],
        cik: str,
        target: str,
    ) -> None:
        tag_rank = 0
        for taxonomy, tags in taxonomy_groups:
            taxonomy_root = facts_root.get(taxonomy, {})
            if not isinstance(taxonomy_root, dict):
                tag_rank += len(tags)
                continue

            for tag in tags:
                fact_payload = taxonomy_root.get(tag, {})
                for observation in _iter_monetary_observations(fact_payload):
                    candidate = _build_fact_candidate(
                        metric=target,
                        taxonomy=taxonomy,
                        tag=tag,
                        tag_rank=tag_rank,
                        observation=observation,
                        filing_index=filing_index,
                    )
                    if candidate is None:
                        continue

                    accumulator = statements.setdefault(
                        candidate.accession_number,
                        _new_accumulator(
                            cik=cik,
                            accession_number=candidate.accession_number,
                            filing_metadata=filing_index.get(candidate.accession_number),
                            fallback_form=candidate.form,
                        ),
                    )
                    getattr(accumulator, target).append(candidate)
                    _collect_period_candidate(accumulator, candidate)

                tag_rank += 1

    def _collect_segment_revenue_candidates(
        self,
        facts_root: dict[str, Any],
        filing_index: dict[str, FilingMetadata],
        statements: dict[str, StatementAccumulator],
        cik: str,
    ) -> None:
        tag_rank = 0
        for taxonomy, tags in CANONICAL_FACTS["revenue"]:
            taxonomy_root = facts_root.get(taxonomy, {})
            if not isinstance(taxonomy_root, dict):
                tag_rank += len(tags)
                continue

            for tag in tags:
                fact_payload = taxonomy_root.get(tag, {})
                for observation in _iter_monetary_observations(fact_payload):
                    candidate = _build_segment_revenue_candidate(
                        taxonomy=taxonomy,
                        tag=tag,
                        tag_rank=tag_rank,
                        observation=observation,
                        filing_index=filing_index,
                    )
                    if candidate is None:
                        continue

                    accumulator = statements.setdefault(
                        candidate.accession_number,
                        _new_accumulator(
                            cik=cik,
                            accession_number=candidate.accession_number,
                            filing_metadata=filing_index.get(candidate.accession_number),
                            fallback_form=candidate.form,
                        ),
                    )
                    accumulator.segment_revenue_candidates.append(candidate)
                    _collect_period_candidate(accumulator, candidate)

                tag_rank += 1

    def _finalize_statement(self, accumulator: StatementAccumulator) -> NormalizedStatement | None:
        filing_type = _base_form(accumulator.filing_type)
        period_start, period_end = _select_statement_period(
            filing_type=filing_type,
            duration_candidates=accumulator.duration_candidates,
            instant_period_ends=accumulator.instant_period_ends,
            report_date=accumulator.report_date,
        )
        if period_start is None or period_end is None:
            return None

        target_duration_days = (period_end - period_start).days if period_start and period_end else None
        data = {metric: None for metric in CANONICAL_FACTS}
        data["capex"] = None
        data["debt_changes"] = None
        data["free_cash_flow"] = None
        data["segment_breakdown"] = []

        for metric, candidates in accumulator.metric_candidates.items():
            selected = _select_best_candidate(
                candidates=candidates,
                filing_type=filing_type,
                target_start=period_start,
                target_end=period_end,
                target_duration_days=target_duration_days,
            )
            data[metric] = selected.value if selected is not None else None

        capex_candidate = _select_best_candidate(
            candidates=accumulator.capex_candidates,
            filing_type=filing_type,
            target_start=period_start,
            target_end=period_end,
            target_duration_days=target_duration_days,
        )
        debt_issuance_candidate = _select_best_candidate(
            candidates=accumulator.debt_issuance_candidates,
            filing_type=filing_type,
            target_start=period_start,
            target_end=period_end,
            target_duration_days=target_duration_days,
        )
        debt_repayment_candidate = _select_best_candidate(
            candidates=accumulator.debt_repayment_candidates,
            filing_type=filing_type,
            target_start=period_start,
            target_end=period_end,
            target_duration_days=target_duration_days,
        )
        if capex_candidate is not None:
            data["capex"] = _json_number(abs(capex_candidate.value))
        if debt_issuance_candidate is not None or debt_repayment_candidate is not None:
            issuance_value = abs(debt_issuance_candidate.value) if debt_issuance_candidate is not None else 0
            repayment_value = abs(debt_repayment_candidate.value) if debt_repayment_candidate is not None else 0
            data["debt_changes"] = _json_number(issuance_value - repayment_value)
        if data.get("operating_cash_flow") is not None and capex_candidate is not None:
            data["free_cash_flow"] = _json_number(data["operating_cash_flow"] - abs(capex_candidate.value))
        else:
            data["free_cash_flow"] = None

        data["segment_breakdown"] = _select_segment_breakdown(
            candidates=accumulator.segment_revenue_candidates,
            filing_type=filing_type,
            target_start=period_start,
            target_end=period_end,
            target_duration_days=target_duration_days,
            total_revenue=data.get("revenue"),
        )

        if not any(value is not None for key, value in data.items() if key != "segment_breakdown"):
            return None

        return NormalizedStatement(
            accession_number=accumulator.accession_number,
            filing_type=filing_type,
            period_start=period_start,
            period_end=period_end,
            source=accumulator.source,
            data=data,
        )


class EdgarIngestionService:
    def __init__(self) -> None:
        self.client = EdgarClient()
        self.market_data = MarketDataClient()
        self.normalizer = EdgarNormalizer()
        self.filing_parser = FilingParser(fetch_text=self.client._get_text)

    def close(self) -> None:
        self.client.close()
        self.market_data.close()

    def _populate_segment_breakdowns(
        self,
        normalized_statements: list[NormalizedStatement],
        reporter: JobReporter,
    ) -> None:
        targets = _select_segment_target_statements(normalized_statements)
        if not targets:
            return

        reporter.step("normalize", "Extracting segment revenue tables...")
        segment_cache: dict[str, dict[date, list[dict[str, Any]]]] = {}
        for statement in targets:
            if statement.data.get("segment_breakdown"):
                continue

            filing_base_url = _filing_directory_url(statement.source)
            if filing_base_url not in segment_cache:
                segment_cache[filing_base_url] = _extract_segment_breakdowns_from_filing(self.client, statement.source)

            statement.data["segment_breakdown"] = segment_cache[filing_base_url].get(statement.period_end, [])

    def _refresh_insider_trades(
        self,
        session: Session,
        company: Company,
        filing_index: dict[str, FilingMetadata],
        checked_at: datetime,
        reporter: JobReporter,
        *,
        force: bool = False,
    ) -> int:
        existing_accessions = _existing_insider_trade_accessions(session, company.id)
        session.commit()
        insider_filings = [
            metadata
            for metadata in filing_index.values()
            if _base_form(metadata.form) in {"4", "5"}
        ]
        insider_filings.sort(
            key=lambda metadata: (
                metadata.filing_date or date.min,
                metadata.accession_number,
            ),
            reverse=True,
        )
        insider_filings = insider_filings[: settings.sec_form4_max_filings_per_refresh]

        candidate_filings = insider_filings if force else [
            metadata for metadata in insider_filings if metadata.accession_number not in existing_accessions
        ]
        if candidate_filings:
            reporter.step("insider", f"Fetching {len(candidate_filings)} Form 4/5 filing(s)...")
        else:
            reporter.step("insider", "Checking cached Form 4/5 coverage...")

        normalized_trades: list[NormalizedInsiderTrade] = []
        for metadata in candidate_filings:
            source_url, xml_payload = self.client.get_form4_xml(company.cik, metadata)
            normalized_trades.extend(
                _parse_form4_transactions(
                    xml_payload=xml_payload,
                    source_url=source_url,
                    filing_metadata=metadata,
                )
            )

        reporter.step("database", "Saving insider trades to database...")
        trades_written = 0
        if normalized_trades:
            trades_written = _upsert_insider_trades(
                session=session,
                company=company,
                normalized_trades=normalized_trades,
                checked_at=checked_at,
            )
        _touch_company_insider_trades(session, company.id, checked_at)
        return trades_written

    def refresh_company(
        self,
        identifier: str,
        force: bool = False,
        reporter: JobReporter | None = None,
        *,
        refresh_insider_data: bool = True,
        refresh_institutional_data: bool = True,
        refresh_beneficial_ownership_data: bool = True,
    ) -> IngestionResult:
        checked_at = datetime.now(timezone.utc)
        active_reporter = reporter or JobReporter()

        if settings.sec_cache_prune_max_entries > 0:
            try:
                removed_entries = prune_sec_cache_periodic(
                    min_interval_seconds=float(settings.sec_cache_prune_interval_seconds),
                    max_entries=settings.sec_cache_prune_max_entries,
                )
                if removed_entries:
                    logger.info("SEC cache prune removed %s expired entries", removed_entries)
            except Exception:
                logger.exception("SEC cache periodic prune failed")

        active_reporter.step("lookup", "Looking up ticker -> CIK...")

        get_engine()
        with SessionLocal() as session:
            active_reporter.step("cache", "Checking database cache...")
            local_company = _find_local_company(session, identifier)
            latest_statement_checked = _latest_company_last_checked(session, local_company.id) if local_company else None
            latest_price_checked = get_company_price_last_checked(session, local_company.id) if local_company else None
            latest_insider_checked = _latest_insider_trade_last_checked(session, local_company) if local_company else None
            latest_institutional_checked = (
                get_company_institutional_holdings_last_checked(session, local_company) if local_company else None
            )
            latest_beneficial_checked = (
                _latest_beneficial_ownership_last_checked(session, local_company) if local_company else None
            )
            has_segment_breakdown_key = (
                _latest_statement_has_segment_breakdown_key(session, local_company.id) if local_company else False
            )
            freshness_cutoff = checked_at - timedelta(hours=settings.freshness_window_hours)
            statements_fresh = latest_statement_checked is not None and latest_statement_checked >= freshness_cutoff
            prices_fresh = latest_price_checked is not None and latest_price_checked >= freshness_cutoff
            insider_fresh = latest_insider_checked is not None and latest_insider_checked >= freshness_cutoff
            institutional_fresh = (
                latest_institutional_checked is not None and latest_institutional_checked >= freshness_cutoff
            )
            beneficial_fresh = (
                latest_beneficial_checked is not None and latest_beneficial_checked >= freshness_cutoff
            )
            effective_insider_fresh = insider_fresh or not refresh_insider_data
            effective_institutional_fresh = institutional_fresh or not refresh_institutional_data
            effective_beneficial_fresh = beneficial_fresh or not refresh_beneficial_ownership_data

            relevant_last_checked_values = [latest_statement_checked, latest_price_checked]
            if refresh_insider_data:
                relevant_last_checked_values.append(latest_insider_checked)
            if refresh_institutional_data:
                relevant_last_checked_values.append(latest_institutional_checked)
            if refresh_beneficial_ownership_data:
                relevant_last_checked_values.append(latest_beneficial_checked)

            if (
                local_company is not None
                and not force
                and statements_fresh
                and prices_fresh
                and has_segment_breakdown_key
                and effective_insider_fresh
                and effective_institutional_fresh
                and effective_beneficial_fresh
            ):
                active_reporter.complete("Using fresh cached data.")
                session.commit()
                return IngestionResult(
                    identifier=identifier,
                    company_id=local_company.id,
                    cik=local_company.cik,
                    ticker=local_company.ticker,
                    status="skipped",
                    statements_written=0,
                    insider_trades_written=0,
                    institutional_holdings_written=0,
                    beneficial_ownership_written=0,
                    price_points_written=0,
                    fetched_from_sec=False,
                    last_checked=min(
                        value
                        for value in relevant_last_checked_values
                        if value is not None
                    ),
                    detail="Freshness window still valid",
                )

            if local_company is not None and not force and statements_fresh and prices_fresh and not has_segment_breakdown_key:
                active_reporter.step("cache", "Cached filings need segment metadata backfill...")

            if (
                local_company is not None
                and not force
                and refresh_beneficial_ownership_data
                and statements_fresh
                and prices_fresh
                and effective_insider_fresh
                and effective_institutional_fresh
                and not beneficial_fresh
            ):
                session.commit()
                active_reporter.step("sec", "Checking SEC for new beneficial ownership filings...")
                submissions = self.client.get_submissions(local_company.cik)
                filing_index = self.client.build_filing_index(submissions)
                from app.services.beneficial_ownership import (  # local import avoids circular dependency
                    collect_beneficial_ownership_reports,
                    upsert_beneficial_ownership_reports,
                )
                reports = collect_beneficial_ownership_reports(local_company.cik, filing_index, client=self.client)
                beneficial_ownership_written = upsert_beneficial_ownership_reports(
                    session, local_company, reports, checked_at=checked_at
                )
                session.commit()
                active_reporter.complete("Refresh and compute complete.")
                return IngestionResult(
                    identifier=identifier,
                    company_id=local_company.id,
                    cik=local_company.cik,
                    ticker=local_company.ticker,
                    status="fetched",
                    statements_written=0,
                    insider_trades_written=0,
                    institutional_holdings_written=0,
                    beneficial_ownership_written=beneficial_ownership_written,
                    price_points_written=0,
                    fetched_from_sec=True,
                    last_checked=checked_at,
                    detail=(
                        f"Cached {beneficial_ownership_written} beneficial ownership filings"
                        if beneficial_ownership_written
                        else "Checked beneficial ownership filings; no new entries"
                    ),
                )

            if (
                local_company is not None
                and not force
                and refresh_insider_data
                and statements_fresh
                and prices_fresh
                and has_segment_breakdown_key
                and effective_institutional_fresh
                and not insider_fresh
            ):
                session.commit()
                active_reporter.step("sec", "Checking SEC for new Form 4 filings...")
                submissions = self.client.get_submissions(local_company.cik)
                filing_index = self.client.build_filing_index(submissions)
                insider_trades_written = self._refresh_insider_trades(
                    session=session,
                    company=local_company,
                    filing_index=filing_index,
                    checked_at=checked_at,
                    reporter=active_reporter,
                    force=force,
                )
                session.commit()
                active_reporter.complete("Refresh and compute complete.")
                return IngestionResult(
                    identifier=identifier,
                    company_id=local_company.id,
                    cik=local_company.cik,
                    ticker=local_company.ticker,
                    status="fetched",
                    statements_written=0,
                    insider_trades_written=insider_trades_written,
                    institutional_holdings_written=0,
                    price_points_written=0,
                    fetched_from_sec=True,
                    last_checked=checked_at,
                    detail=(
                        f"Cached {insider_trades_written} insider trades"
                        if insider_trades_written
                        else "Checked Form 4 filings; no new insider trades"
                    ),
                )

            if (
                local_company is not None
                and not force
                and refresh_institutional_data
                and statements_fresh
                and prices_fresh
                and has_segment_breakdown_key
                and effective_insider_fresh
                and not institutional_fresh
            ):
                session.commit()
                institutional_holdings_written = refresh_company_institutional_holdings(
                    session=session,
                    company=local_company,
                    checked_at=checked_at,
                    reporter=active_reporter,
                    force=force,
                )
                session.commit()
                active_reporter.complete("Refresh and compute complete.")
                return IngestionResult(
                    identifier=identifier,
                    company_id=local_company.id,
                    cik=local_company.cik,
                    ticker=local_company.ticker,
                    status="fetched",
                    statements_written=0,
                    insider_trades_written=0,
                    institutional_holdings_written=institutional_holdings_written,
                    beneficial_ownership_written=0,
                    price_points_written=0,
                    fetched_from_sec=True,
                    last_checked=checked_at,
                    detail=(
                        f"Cached {institutional_holdings_written} institutional holdings snapshots"
                        if institutional_holdings_written
                        else "Checked 13F filings; no institutional holdings matched"
                    ),
                )

            if (
                local_company is not None
                and not force
                and statements_fresh
                and not prices_fresh
                and has_segment_breakdown_key
                and effective_insider_fresh
                and effective_institutional_fresh
            ):
                session.commit()
                try:
                    market_profile = self.market_data.get_market_profile(local_company.ticker)
                    if market_profile.sector:
                        local_company.market_sector = market_profile.sector
                    if market_profile.industry:
                        local_company.market_industry = market_profile.industry
                    active_reporter.step("market", "Fetching price history...")
                    price_bars = self.market_data.get_price_history(local_company.ticker)
                    active_reporter.step("database", "Saving price history to database...")
                    price_points_written = upsert_price_history(
                        session=session,
                        company=local_company,
                        price_bars=price_bars,
                        checked_at=checked_at,
                    )
                    if price_points_written > 0:
                        touch_company_price_history(session, local_company.id, checked_at)
                except Exception as exc:
                    logger.exception("Market data refresh failed for %s", local_company.ticker)
                    active_reporter.step("market", f"Market data refresh failed: {exc}")
                    price_points_written = 0
                session.commit()
                active_reporter.complete("Refresh and compute complete.")
                return IngestionResult(
                    identifier=identifier,
                    company_id=local_company.id,
                    cik=local_company.cik,
                    ticker=local_company.ticker,
                    status="fetched",
                    statements_written=0,
                    insider_trades_written=0,
                    institutional_holdings_written=0,
                    beneficial_ownership_written=0,
                    price_points_written=price_points_written,
                    fetched_from_sec=False,
                    last_checked=checked_at,
                    detail=f"Cached {price_points_written} daily price bars",
                )

        active_reporter.step("sec", "Checking SEC for new filings...")
        company_identity = self.client.resolve_company(identifier)
        submissions = self.client.get_submissions(company_identity.cik)
        active_reporter.step("filing", f"Fetching {_primary_supported_form(submissions)}...")
        filing_index = self.client.build_filing_index(submissions)
        companyfacts = self.client.get_companyfacts(company_identity.cik)
        active_reporter.step("filing", "Parsing filing reports...")
        parsed_filing_insights = self.filing_parser.parse_financial_insights(
            cik=company_identity.cik,
            filing_index=filing_index,
        )
        try:
            market_profile = self.market_data.get_market_profile(company_identity.ticker)
        except Exception as exc:
            logger.exception("Market profile lookup failed for %s", company_identity.ticker)
            active_reporter.step("market", f"Market profile lookup failed: {exc}")
            market_profile = MarketProfile(sector=None, industry=None)

        enriched_identity = CompanyIdentity(
            cik=company_identity.cik,
            ticker=((submissions.get("tickers") or [company_identity.ticker])[0]),
            name=str(submissions.get("name") or company_identity.name),
            exchange=((submissions.get("exchanges") or [company_identity.exchange])[0]),
            sector=submissions.get("sicDescription") or company_identity.sector,
            market_sector=market_profile.sector,
            market_industry=market_profile.industry,
        )

        get_engine()
        with SessionLocal() as session:
            company = _upsert_company(session, enriched_identity)
            active_reporter.step("normalize", "Normalizing XBRL...")
            normalized_statements = self.normalizer.normalize(
                cik=company.cik,
                companyfacts=companyfacts,
                filing_index=filing_index,
            )
            self._populate_segment_breakdowns(normalized_statements, active_reporter)

            active_reporter.step("database", "Saving to database...")
            statements_written = _upsert_statements(
                session=session,
                company=company,
                normalized_statements=normalized_statements,
                checked_at=checked_at,
            )
            parsed_statements_written = _upsert_filing_parser_statements(
                session=session,
                company=company,
                parsed_insights=parsed_filing_insights,
                checked_at=checked_at,
            )
            _touch_company_statements(session, company.id, checked_at)
            precompute_core_models(session, company.id, reporter=active_reporter)
            session.commit()

            insider_trades_written = 0
            if refresh_insider_data and (force or not insider_fresh):
                insider_trades_written = self._refresh_insider_trades(
                    session=session,
                    company=company,
                    filing_index=filing_index,
                    checked_at=checked_at,
                    reporter=active_reporter,
                    force=force,
                )
                session.commit()

            institutional_holdings_written = 0
            if refresh_institutional_data and (force or not institutional_fresh):
                institutional_holdings_written = refresh_company_institutional_holdings(
                    session=session,
                    company=company,
                    checked_at=checked_at,
                    reporter=active_reporter,
                    force=force,
                )
                session.commit()

            beneficial_ownership_written = 0
            if refresh_beneficial_ownership_data and (force or not beneficial_fresh):
                active_reporter.step("beneficial", "Caching beneficial ownership filings...")
                from app.services.beneficial_ownership import (  # local import avoids circular dependency
                    collect_beneficial_ownership_reports,
                    upsert_beneficial_ownership_reports,
                )
                bo_reports = collect_beneficial_ownership_reports(company.cik, filing_index, client=self.client)
                beneficial_ownership_written = upsert_beneficial_ownership_reports(
                    session, company, bo_reports, checked_at=checked_at
                )
                session.commit()

            filing_events_written = 0
            active_reporter.step("events", "Caching 8-K filing events...")
            from app.services.eight_k_events import collect_filing_events, upsert_filing_events

            filing_events = collect_filing_events(company.cik, filing_index)
            filing_events_written = upsert_filing_events(
                session=session,
                company=company,
                events=filing_events,
                checked_at=checked_at,
            )
            session.commit()

            capital_markets_written = 0
            active_reporter.step("capital", "Caching capital markets filings...")
            from app.services.capital_markets import collect_capital_markets_events, upsert_capital_markets_events

            capital_markets_events = collect_capital_markets_events(company.cik, filing_index)
            capital_markets_written = upsert_capital_markets_events(
                session=session,
                company=company,
                events=capital_markets_events,
                checked_at=checked_at,
            )
            session.commit()

            price_points_written = 0
            if force or not prices_fresh:
                try:
                    active_reporter.step("market", "Fetching price history...")
                    price_bars = self.market_data.get_price_history(company.ticker)
                    active_reporter.step("database", "Saving price history to database...")
                    price_points_written = upsert_price_history(
                        session=session,
                        company=company,
                        price_bars=price_bars,
                        checked_at=checked_at,
                    )
                    if price_points_written > 0:
                        touch_company_price_history(session, company.id, checked_at)
                except Exception as exc:
                    logger.exception("Market data refresh failed for %s", company.ticker)
                    active_reporter.step("market", f"Market data refresh failed: {exc}")
                    price_points_written = 0

            session.commit()
            active_reporter.complete("Refresh and compute complete.")

            detail_parts: list[str] = [f"Normalized {statements_written} filings"]
            if refresh_insider_data and (force or not insider_fresh):
                detail_parts.append(
                    f"Cached {insider_trades_written} insider trades"
                    if insider_trades_written
                    else "Checked Form 4/5 filings"
                )
            if refresh_institutional_data and (force or not institutional_fresh):
                detail_parts.append(
                    f"Cached {institutional_holdings_written} institutional holdings snapshots"
                    if institutional_holdings_written
                    else "Checked 13F filings"
                )
            if refresh_beneficial_ownership_data and (force or not beneficial_fresh):
                detail_parts.append(
                    f"Cached {beneficial_ownership_written} beneficial ownership filings"
                    if beneficial_ownership_written
                    else "Checked beneficial ownership filings"
                )
            detail_parts.append(
                f"Cached {filing_events_written} filing event rows"
                if filing_events_written
                else "Checked 8-K filing events"
            )
            detail_parts.append(
                f"Cached {capital_markets_written} capital markets rows"
                if capital_markets_written
                else "Checked capital markets filings"
            )
            if force or not prices_fresh:
                detail_parts.append(f"Cached {price_points_written} daily price bars")

            return IngestionResult(
                identifier=identifier,
                company_id=company.id,
                cik=company.cik,
                ticker=company.ticker,
                status="fetched",
                statements_written=statements_written + parsed_statements_written,
                insider_trades_written=insider_trades_written,
                institutional_holdings_written=institutional_holdings_written,
                beneficial_ownership_written=beneficial_ownership_written,
                price_points_written=price_points_written,
                fetched_from_sec=True,
                last_checked=checked_at,
                detail="; ".join(detail_parts),
            )


def run_refresh_job(identifier: str, force: bool = False, job_id: str | None = None) -> dict[str, Any]:
    service = EdgarIngestionService()
    reporter = JobReporter(job_id)
    try:
        result = service.refresh_company(identifier=identifier, force=force, reporter=reporter)
        payload = asdict(result)
        payload["last_checked"] = result.last_checked.isoformat() if result.last_checked else None
        payload["job_id"] = job_id
        logger.info("SEC refresh completed: %s", payload)
        return payload
    except Exception as exc:
        reporter.fail(str(exc))
        raise
    finally:
        service.close()


def worker_main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Refresh SEC EDGAR filings into PostgreSQL")
    parser.add_argument("identifiers", nargs="+", help="Ticker, CIK, or exact SEC company name")
    parser.add_argument("--force", action="store_true", help="Bypass the 24-hour freshness window")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    exit_code = 0
    for identifier in args.identifiers:
        try:
            result = run_refresh_job(identifier=identifier, force=args.force)
            print(json.dumps(result, default=str))
        except Exception as exc:
            exit_code = 1
            logger.exception("SEC refresh failed for %s: %s", identifier, exc)

    return exit_code


def _existing_insider_trade_accessions(session: Session, company_id: int) -> set[str]:
    statement = select(InsiderTrade.accession_number).where(InsiderTrade.company_id == company_id).distinct()
    return {value for value in session.execute(statement).scalars() if value}


def _latest_insider_trade_last_checked(session: Session, company: Company) -> datetime | None:
    if company.insider_trades_last_checked is not None:
        return _normalize_datetime_value(company.insider_trades_last_checked)

    statement = select(func.max(InsiderTrade.last_checked)).where(InsiderTrade.company_id == company.id)
    return _normalize_datetime_value(session.execute(statement).scalar_one_or_none())


def _latest_beneficial_ownership_last_checked(session: Session, company: Company) -> datetime | None:
    if company.beneficial_ownership_last_checked is not None:
        return _normalize_datetime_value(company.beneficial_ownership_last_checked)

    statement = select(func.max(BeneficialOwnershipReport.last_checked)).where(
        BeneficialOwnershipReport.company_id == company.id
    )
    return _normalize_datetime_value(session.execute(statement).scalar_one_or_none())


def _upsert_insider_trades(
    session: Session,
    company: Company,
    normalized_trades: list[NormalizedInsiderTrade],
    checked_at: datetime,
) -> int:
    if not normalized_trades:
        return 0

    payload = [
        {
            "company_id": company.id,
            "accession_number": trade.accession_number,
            "filing_type": trade.filing_type,
            "filing_date": trade.filing_date,
            "transaction_index": trade.transaction_index,
            "insider_name": trade.insider_name,
            "role": trade.role,
            "transaction_date": trade.transaction_date,
            "action": trade.action,
            "shares": trade.shares,
            "price": trade.price,
            "value": trade.value,
            "ownership_after": trade.ownership_after,
            "security_title": trade.security_title,
            "is_derivative": trade.is_derivative,
            "ownership_nature": trade.ownership_nature,
            "exercise_price": trade.exercise_price,
            "expiration_date": trade.expiration_date,
            "footnote_tags": trade.footnote_tags,
            "transaction_code": trade.transaction_code,
            "is_10b5_1": trade.is_10b5_1,
            "source": trade.source,
            "last_checked": checked_at,
        }
        for trade in normalized_trades
    ]

    statement = insert(InsiderTrade).values(payload)
    statement = statement.on_conflict_do_update(
        index_elements=["company_id", "accession_number", "insider_name", "transaction_index"],
        set_={
            "filing_type": statement.excluded.filing_type,
            "filing_date": statement.excluded.filing_date,
            "role": statement.excluded.role,
            "transaction_date": statement.excluded.transaction_date,
            "action": statement.excluded.action,
            "shares": statement.excluded.shares,
            "price": statement.excluded.price,
            "value": statement.excluded.value,
            "ownership_after": statement.excluded.ownership_after,
            "security_title": statement.excluded.security_title,
            "is_derivative": statement.excluded.is_derivative,
            "ownership_nature": statement.excluded.ownership_nature,
            "exercise_price": statement.excluded.exercise_price,
            "expiration_date": statement.excluded.expiration_date,
            "footnote_tags": statement.excluded.footnote_tags,
            "transaction_code": statement.excluded.transaction_code,
            "is_10b5_1": statement.excluded.is_10b5_1,
            "source": statement.excluded.source,
            "last_updated": func.now(),
            "last_checked": statement.excluded.last_checked,
        },
    )
    session.execute(statement)
    return len(payload)


def _touch_company_insider_trades(session: Session, company_id: int, checked_at: datetime) -> None:
    session.execute(
        update(InsiderTrade)
        .where(InsiderTrade.company_id == company_id)
        .values(last_checked=checked_at)
    )
    session.execute(
        update(Company)
        .where(Company.id == company_id)
        .values(insider_trades_last_checked=checked_at)
    )


def _parse_form4_transactions(
    *,
    xml_payload: str,
    source_url: str,
    filing_metadata: FilingMetadata,
) -> list[NormalizedInsiderTrade]:
    try:
        root = ET.fromstring(xml_payload)
    except ET.ParseError:
        logger.warning("Unable to parse Form 4 XML for accession %s", filing_metadata.accession_number)
        return []

    footnotes = {
        str(node.attrib.get("id") or "").strip(): "".join(node.itertext()).strip()
        for node in root.findall("./footnotes/footnote")
        if str(node.attrib.get("id") or "").strip()
    }
    document_10b5_1 = _parse_form4_bool(root.findtext("./aff10b5One"))
    fallback_transaction_date = _parse_date(root.findtext("./periodOfReport")) or filing_metadata.filing_date
    owners = [_parse_reporting_owner(owner) for owner in root.findall("./reportingOwner")]
    owners = [owner for owner in owners if owner["name"]]
    if not owners:
        owners = [{"name": "Unknown Insider", "role": None}]

    trades: list[NormalizedInsiderTrade] = []
    transaction_index = 0
    for path in ("./nonDerivativeTable/nonDerivativeTransaction", "./derivativeTable/derivativeTransaction"):
        is_derivative = "derivative" in path.lower()
        for transaction in root.findall(path):
            transaction_code = _clean_text(transaction.findtext("./transactionCoding/transactionCode"))
            acquired_disposed = _clean_text(
                transaction.findtext("./transactionAmounts/transactionAcquiredDisposedCode/value")
            )
            security_title = _clean_text(transaction.findtext("./securityTitle/value"))
            transaction_date = (
                _parse_date(transaction.findtext("./transactionDate/value"))
                or _parse_date(transaction.findtext("./deemedExecutionDate/value"))
                or fallback_transaction_date
            )
            shares = _parse_optional_float(transaction.findtext("./transactionAmounts/transactionShares/value"))
            price = _parse_optional_float(transaction.findtext("./transactionAmounts/transactionPricePerShare/value"))
            exercise_price = _parse_optional_float(transaction.findtext("./conversionOrExercisePrice/value"))
            if price is None:
                price = exercise_price
            expiration_date = _parse_date(transaction.findtext("./expirationDate/value"))
            ownership_nature = _normalize_ownership_nature(
                _clean_text(transaction.findtext("./postTransactionAmounts/ownershipNature/directOrIndirectOwnership/value"))
            )
            ownership_after = _parse_optional_float(
                transaction.findtext("./postTransactionAmounts/sharesOwnedFollowingTransaction/value")
            )
            value = shares * price if shares is not None and price is not None else None
            footnote_ids = {
                str(node.attrib.get("id") or "").strip()
                for node in transaction.findall(".//footnoteId")
                if str(node.attrib.get("id") or "").strip()
            }
            footnote_tags = _normalize_form4_footnote_tags(footnote_ids, footnotes)
            is_10b5_1 = document_10b5_1 or _footnotes_indicate_10b5_1(footnote_ids, footnotes)
            action = _normalize_insider_action(transaction_code, acquired_disposed)

            for owner in owners:
                trades.append(
                    NormalizedInsiderTrade(
                        accession_number=filing_metadata.accession_number,
                        filing_type=_base_form(filing_metadata.form) or "4",
                        filing_date=filing_metadata.filing_date,
                        transaction_index=transaction_index,
                        insider_name=str(owner["name"]),
                        role=owner["role"] if isinstance(owner["role"], str) else None,
                        transaction_date=transaction_date,
                        action=action,
                        shares=shares,
                        price=price,
                        value=value,
                        ownership_after=ownership_after,
                        security_title=security_title,
                        is_derivative=is_derivative,
                        ownership_nature=ownership_nature,
                        exercise_price=exercise_price,
                        expiration_date=expiration_date,
                        footnote_tags=footnote_tags,
                        transaction_code=transaction_code,
                        is_10b5_1=is_10b5_1,
                        source=source_url,
                    )
                )
            transaction_index += 1

    return trades


def _parse_reporting_owner(owner_node: ET.Element) -> dict[str, str | None]:
    name = _clean_text(owner_node.findtext("./reportingOwnerId/rptOwnerName")) or "Unknown Insider"
    relationship = owner_node.find("./reportingOwnerRelationship")
    role = _normalize_reporting_owner_role(relationship)
    return {"name": name, "role": role}


def _normalize_reporting_owner_role(relationship: ET.Element | None) -> str | None:
    if relationship is None:
        return None

    officer_title = _clean_text(relationship.findtext("./officerTitle"))
    other_text = _clean_text(relationship.findtext("./otherText"))
    is_director = _parse_form4_bool(relationship.findtext("./isDirector"))
    is_officer = _parse_form4_bool(relationship.findtext("./isOfficer"))
    is_ten_percent_owner = _parse_form4_bool(relationship.findtext("./isTenPercentOwner"))

    if officer_title:
        normalized_title = officer_title.upper()
        if "CHIEF EXECUTIVE" in normalized_title or normalized_title == "CEO":
            return "CEO"
        if "CHIEF FINANCIAL" in normalized_title or normalized_title == "CFO":
            return "CFO"
        return officer_title
    if is_director:
        return "Director"
    if is_officer:
        return "Officer"
    if is_ten_percent_owner:
        return "10% Owner"
    if other_text:
        return other_text
    return None


def _normalize_insider_action(transaction_code: str | None, acquired_disposed: str | None) -> str:
    normalized_code = (transaction_code or "").strip().upper()
    normalized_disposition = (acquired_disposed or "").strip().upper()
    if normalized_disposition == "A":
        return "buy"
    if normalized_disposition == "D":
        return "sell"
    if normalized_code in {"P", "A", "M", "C", "L"}:
        return "buy"
    if normalized_code in {"S", "D", "F"}:
        return "sell"
    return "other"


def _footnotes_indicate_10b5_1(footnote_ids: set[str], footnotes: dict[str, str]) -> bool:
    for footnote_id in footnote_ids:
        normalized_text = re.sub(r"[^a-z0-9]+", "", footnotes.get(footnote_id, "").lower())
        if "10b51" in normalized_text:
            return True
    return False


def _normalize_form4_footnote_tags(footnote_ids: set[str], footnotes: dict[str, str]) -> list[str] | None:
    if not footnote_ids:
        return None

    tags: set[str] = set()
    for footnote_id in footnote_ids:
        text = footnotes.get(footnote_id, "")
        normalized = re.sub(r"\s+", " ", text.lower()).strip()
        compact = re.sub(r"[^a-z0-9]+", "", normalized)
        if "10b51" in compact:
            tags.add("10b5-1")
        if "gift" in normalized:
            tags.add("gift")
        if "tax" in normalized or "withhold" in normalized:
            tags.add("tax-withholding")
        if "estate" in normalized or "trust" in normalized:
            tags.add("trust-estate")
        if "option" in normalized or "exercise" in normalized:
            tags.add("option-exercise")
        if "restricted stock" in normalized or "rsu" in normalized:
            tags.add("equity-award")

    return sorted(tags) if tags else None


def _parse_form4_bool(value: Any) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "y"}


def _normalize_ownership_nature(value: str | None) -> str | None:
    normalized = (value or "").strip().upper()
    if normalized == "D":
        return "direct"
    if normalized == "I":
        return "indirect"
    return value


def _parse_optional_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(str(value).replace(",", ""))
    except (TypeError, ValueError):
        return None


def _clean_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _retry_wait(retry_after: str | None, backoff: float, attempt: int) -> float:
    if retry_after and retry_after.isdigit():
        return float(retry_after)
    return backoff * (2 ** attempt)


def _normalize_datetime_value(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _form4_xml_priority(name: str, primary_document: str | None) -> tuple[int, int, int, int, int]:
    normalized_name = name.lower()
    normalized_primary = (primary_document or "").strip().lower()
    return (
        0 if "/" not in normalized_name else 1,
        0 if normalized_name.startswith("form4") else 1,
        0 if "form4" in normalized_name else 1,
        0 if normalized_name == "ownership.xml" else 1,
        0 if normalized_name == normalized_primary and "/" not in normalized_name else 1,
        len(normalized_name),
    )


def _upsert_company(session: Session, identity: CompanyIdentity) -> Company:
    statement: Select[tuple[Company]] = select(Company).where(
        or_(Company.cik == identity.cik, Company.ticker == identity.ticker)
    )
    company = session.execute(statement).scalar_one_or_none()
    if company is None:
        company = Company(
            ticker=identity.ticker,
            cik=identity.cik,
            name=identity.name,
            sector=identity.sector,
            market_sector=identity.market_sector,
            market_industry=identity.market_industry,
        )
        session.add(company)
        session.flush()
        return company

    company.ticker = identity.ticker
    company.cik = identity.cik
    company.name = identity.name
    if identity.sector:
        company.sector = identity.sector
    if identity.market_sector:
        company.market_sector = identity.market_sector
    if identity.market_industry:
        company.market_industry = identity.market_industry
    session.flush()
    return company


def upsert_company_identity(session: Session, identity: CompanyIdentity) -> Company:
    return _upsert_company(session, identity)


def _find_local_company(session: Session, identifier: str) -> Company | None:
    lookup = identifier.strip()
    if not lookup:
        return None

    conditions = [Company.ticker == lookup.upper(), Company.name == lookup]
    if lookup.isdigit():
        conditions.append(Company.cik == lookup.zfill(10))

    statement: Select[tuple[Company]] = select(Company).where(or_(*conditions))
    return session.execute(statement).scalar_one_or_none()


def _latest_company_last_checked(session: Session, company_id: int) -> datetime | None:
    statement = select(func.max(FinancialStatement.last_checked)).where(
        FinancialStatement.company_id == company_id,
        FinancialStatement.statement_type == CANONICAL_STATEMENT_TYPE,
    )
    return session.execute(statement).scalar_one_or_none()


def _latest_statement_has_segment_breakdown_key(session: Session, company_id: int) -> bool:
    statement = (
        select(FinancialStatement.data)
        .where(
            FinancialStatement.company_id == company_id,
            FinancialStatement.statement_type == CANONICAL_STATEMENT_TYPE,
        )
        .order_by(FinancialStatement.period_end.desc(), FinancialStatement.filing_type.asc())
    )
    payloads = session.execute(statement).scalars().all()
    return any(
        isinstance(payload, dict)
        and isinstance(payload.get("segment_breakdown"), list)
        and len(payload.get("segment_breakdown") or []) > 0
        for payload in payloads
    )


def _upsert_statements(
    session: Session,
    company: Company,
    normalized_statements: list[NormalizedStatement],
    checked_at: datetime,
) -> int:
    if not normalized_statements:
        return 0

    payload = [
        {
            "company_id": company.id,
            "period_start": statement.period_start,
            "period_end": statement.period_end,
            "filing_type": statement.filing_type,
            "statement_type": CANONICAL_STATEMENT_TYPE,
            "data": statement.data,
            "source": statement.source,
            "last_updated": checked_at,
            "last_checked": checked_at,
        }
        for statement in normalized_statements
    ]

    statement = insert(FinancialStatement).values(payload)
    data_changed = or_(
        FinancialStatement.data.is_distinct_from(statement.excluded.data),
        FinancialStatement.filing_type.is_distinct_from(statement.excluded.filing_type),
    )
    statement = statement.on_conflict_do_update(
        constraint="uq_financial_statements_company_period_type_source",
        set_={
            "data": statement.excluded.data,
            "last_updated": case(
                (data_changed, statement.excluded.last_updated),
                else_=FinancialStatement.last_updated,
            ),
            "last_checked": statement.excluded.last_checked,
            "filing_type": statement.excluded.filing_type,
        },
    )
    session.execute(statement)
    return len(payload)


def _upsert_filing_parser_statements(
    session: Session,
    company: Company,
    parsed_insights: list[ParsedFilingInsight],
    checked_at: datetime,
) -> int:
    if not parsed_insights:
        return 0

    payload = [
        {
            "company_id": company.id,
            "period_start": item.period_start,
            "period_end": item.period_end,
            "filing_type": item.filing_type,
            "statement_type": FILING_PARSER_STATEMENT_TYPE,
            "data": item.data,
            "source": item.source,
            "last_updated": checked_at,
            "last_checked": checked_at,
        }
        for item in parsed_insights
    ]

    statement = insert(FinancialStatement).values(payload)
    data_changed = or_(
        FinancialStatement.data.is_distinct_from(statement.excluded.data),
        FinancialStatement.filing_type.is_distinct_from(statement.excluded.filing_type),
    )
    statement = statement.on_conflict_do_update(
        constraint="uq_financial_statements_company_period_type_source",
        set_={
            "data": statement.excluded.data,
            "last_updated": case(
                (data_changed, statement.excluded.last_updated),
                else_=FinancialStatement.last_updated,
            ),
            "last_checked": statement.excluded.last_checked,
            "filing_type": statement.excluded.filing_type,
        },
    )
    session.execute(statement)
    return len(payload)


def _touch_company_statements(session: Session, company_id: int, checked_at: datetime) -> None:
    statement = (
        update(FinancialStatement)
        .where(
            FinancialStatement.company_id == company_id,
            FinancialStatement.statement_type == CANONICAL_STATEMENT_TYPE,
        )
        .values(last_checked=checked_at)
    )
    session.execute(statement)


def _new_accumulator(
    cik: str,
    accession_number: str,
    filing_metadata: FilingMetadata | None,
    fallback_form: str,
) -> StatementAccumulator:
    primary_document = filing_metadata.primary_document if filing_metadata else None
    filing_type = filing_metadata.form if filing_metadata and filing_metadata.form else fallback_form
    source = _build_filing_source_url(cik=cik, accession_number=accession_number, primary_document=primary_document)
    return StatementAccumulator(
        accession_number=accession_number,
        filing_type=filing_type,
        filed_at=filing_metadata.filing_date if filing_metadata else None,
        report_date=filing_metadata.report_date if filing_metadata else None,
        source=source,
    )


def _collect_period_candidate(accumulator: StatementAccumulator, candidate: FactCandidate) -> None:
    if candidate.period_start and candidate.period_end:
        accumulator.duration_candidates.append((candidate.period_start, candidate.period_end))
    elif candidate.period_end:
        accumulator.instant_period_ends.append(candidate.period_end)


def _build_fact_candidate(
    metric: str,
    taxonomy: str,
    tag: str,
    tag_rank: int,
    observation: dict[str, Any],
    filing_index: dict[str, FilingMetadata],
) -> FactCandidate | None:
    accession_number = observation.get("accn")
    if not accession_number:
        return None

    filing_metadata = filing_index.get(accession_number)
    form = _base_form(observation.get("form") or (filing_metadata.form if filing_metadata else None))
    if form not in SUPPORTED_FORMS:
        return None

    value = observation.get("val")
    if value is None:
        return None

    return FactCandidate(
        metric=metric,
        accession_number=accession_number,
        form=form,
        value=_json_number(value),
        taxonomy=taxonomy,
        tag=tag,
        tag_rank=tag_rank,
        filed_at=_parse_date(observation.get("filed")) or (filing_metadata.filing_date if filing_metadata else None),
        period_start=_parse_date(observation.get("start")),
        period_end=_parse_date(observation.get("end")) or (filing_metadata.report_date if filing_metadata else None),
    )


def _build_segment_revenue_candidate(
    taxonomy: str,
    tag: str,
    tag_rank: int,
    observation: dict[str, Any],
    filing_index: dict[str, FilingMetadata],
) -> SegmentRevenueCandidate | None:
    accession_number = observation.get("accn")
    if not accession_number:
        return None

    filing_metadata = filing_index.get(accession_number)
    form = _base_form(observation.get("form") or (filing_metadata.form if filing_metadata else None))
    if form not in SUPPORTED_FORMS:
        return None

    value = observation.get("val")
    if value is None:
        return None

    dimension = _pick_segment_dimension(observation.get("segment"))
    if dimension is None:
        return None

    revenue_value = _json_number(value)
    if revenue_value <= 0:
        return None

    return SegmentRevenueCandidate(
        accession_number=accession_number,
        form=form,
        value=revenue_value,
        taxonomy=taxonomy,
        tag=tag,
        tag_rank=tag_rank,
        segment_id=dimension["segment_id"],
        segment_name=dimension["segment_name"],
        axis_key=dimension["axis_key"],
        axis_label=dimension["axis_label"],
        kind=dimension["kind"],
        filed_at=_parse_date(observation.get("filed")) or (filing_metadata.filing_date if filing_metadata else None),
        period_start=_parse_date(observation.get("start")),
        period_end=_parse_date(observation.get("end")) or (filing_metadata.report_date if filing_metadata else None),
    )


def _select_segment_target_statements(statements: list[NormalizedStatement]) -> list[NormalizedStatement]:
    ordered = sorted(statements, key=lambda item: (item.period_end, item.filing_type, item.accession_number), reverse=True)
    annual = [statement for statement in ordered if statement.filing_type in ANNUAL_FORMS]
    targets = annual[:4]
    if len(targets) >= 2:
        return targets

    for statement in ordered:
        if statement not in targets:
            targets.append(statement)
        if len(targets) >= 4:
            break
    return targets


def _extract_segment_breakdowns_from_filing(client: EdgarClient, source_url: str) -> dict[date, list[dict[str, Any]]]:
    filing_base_url = _filing_directory_url(source_url)
    try:
        filing_summary = client._get_text(f"{filing_base_url}/FilingSummary.xml")
    except Exception:
        return {}

    best_rank: tuple[int, int, int] | None = None
    best_parsed: dict[date, list[dict[str, Any]]] = {}
    for score, report_name, report_title in _candidate_segment_reports(filing_summary):
        try:
            report_html = client._get_text(f"{filing_base_url}/{report_name}")
        except Exception:
            continue

        parsed = _parse_segment_report_html(report_html, report_title=report_title)
        if not parsed:
            continue

        total_segments = sum(len(items) for items in parsed.values())
        rank = (score, -total_segments, -len(parsed))
        if best_rank is None or rank < best_rank:
            best_rank = rank
            best_parsed = parsed

    return best_parsed


def _filing_directory_url(source_url: str) -> str:
    return source_url.rsplit("/", 1)[0]


def _candidate_segment_reports(filing_summary_xml: str) -> list[tuple[int, str, str]]:
    try:
        root = ET.fromstring(filing_summary_xml)
    except ET.ParseError:
        return []

    candidates: list[tuple[int, str, str]] = []
    for report in root.findall(".//Report"):
        html_file = (report.findtext("HtmlFileName") or "").strip()
        if not html_file:
            continue

        short_name = report.findtext("ShortName") or ""
        long_name = report.findtext("LongName") or ""
        title = f"{short_name} {long_name}".strip()
        score = _segment_report_score(title)
        if score is None:
            continue
        candidates.append((score, html_file, title))

    candidates.sort(key=lambda item: (item[0], item[1]))
    return candidates


def _segment_report_score(title: str) -> int | None:
    normalized_title = title.lower()
    if "segment" not in normalized_title:
        return None

    score = 10
    if "financial information by segment" in normalized_title:
        score -= 8
    if "reportable segment" in normalized_title or "operating segment" in normalized_title:
        score -= 6
    if "details" in normalized_title:
        score -= 2
    if "table" in normalized_title:
        score += 1
    if "revenue" in normalized_title:
        score -= 1
    if "country" in normalized_title or "countries" in normalized_title or "geographic" in normalized_title:
        score += 8
    if "individually accounted for more than 10%" in normalized_title:
        score += 8
    if "long-lived assets" in normalized_title:
        score += 6
    if "major customers" in normalized_title or "customers" in normalized_title:
        score += 6
    if "narrative" in normalized_title:
        score += 6
    return score


def _parse_segment_report_html(report_html: str, *, report_title: str = "") -> dict[date, list[dict[str, Any]]]:
    soup = BeautifulSoup(report_html, "html.parser")
    table = soup.find("table", class_="report")
    if table is None:
        return {}

    axis_key, axis_label, kind = _segment_axis_metadata_from_title(report_title)

    header_dates = _extract_report_header_dates(table)
    if not header_dates:
        return {}

    segments_by_period: dict[date, list[tuple[str, int | float]]] = {period_end: [] for period_end in header_dates}
    current_segment: str | None = None

    for row in table.find_all("tr"):
        cells = row.find_all(["td", "th"], recursive=False)
        if not cells:
            continue

        first_cell = cells[0]
        label = _clean_table_text(first_cell.get_text(" ", strip=True))
        if not label:
            continue

        onclick_text = " ".join(link.get("onclick", "") for link in first_cell.find_all("a"))
        row_classes = {str(value).lower() for value in row.get("class", [])}
        if _is_segment_header_row(label, onclick_text, row_classes):
            current_segment = _normalize_segment_header_label(label)
            continue

        if current_segment is None or not _is_revenue_metric_label(label):
            continue

        value_cells = cells[1 : 1 + len(header_dates)]
        for index, cell in enumerate(value_cells):
            value = _parse_table_number(cell.get_text(" ", strip=True))
            if value is not None and value > 0:
                segments_by_period[header_dates[index]].append((current_segment, value))

    payload_by_period: dict[date, list[dict[str, Any]]] = {}
    for period_end, segment_rows in segments_by_period.items():
        deduped: dict[str, int | float] = {}
        for segment_name, value in segment_rows:
            if segment_name not in deduped or value > deduped[segment_name]:
                deduped[segment_name] = value

        if len(deduped) < 2:
            continue

        total_revenue = sum(deduped.values())
        payload_by_period[period_end] = [
            {
                "segment_id": _normalize_identifier(segment_name),
                "segment_name": segment_name,
                "axis_key": axis_key,
                "axis_label": axis_label,
                "kind": kind,
                "revenue": _json_number(value),
                "share_of_revenue": _json_number(value / total_revenue) if total_revenue else None,
            }
            for segment_name, value in sorted(deduped.items(), key=lambda item: item[1], reverse=True)
        ]

    return payload_by_period


def _segment_axis_metadata_from_title(title: str) -> tuple[str, str, str]:
    normalized_title = _normalize_identifier(title)
    if "reportablesegment" in normalized_title or "operatingsegment" in normalized_title:
        return ("reportable_segments", "Reportable Segments", "business")
    if any(keyword in normalized_title for keyword in ("geographic", "country", "countries", "region", "market")):
        return ("geographic_segments", "Geographic Segments", "geographic")
    return ("operating_segments", "Operating Segments", "business")


def _extract_report_header_dates(table: Any) -> list[date]:
    for row in table.find_all("tr"):
        header_cells = row.find_all("th", recursive=False)
        if not header_cells:
            continue

        parsed_dates = [
            parsed_date
            for parsed_date in (_parse_report_header_date(_clean_table_text(cell.get_text(" ", strip=True))) for cell in header_cells)
            if parsed_date is not None
        ]
        if parsed_dates:
            return parsed_dates
    return []


def _parse_report_header_date(value: str) -> date | None:
    cleaned = value.replace("Sept.", "Sep.").replace(".", "")
    try:
        return datetime.strptime(cleaned, "%b %d, %Y").date()
    except ValueError:
        return None


def _is_segment_header_row(label: str, onclick_text: str, row_classes: set[str]) -> bool:
    normalized_label = _normalize_identifier(label)
    normalized_onclick = _normalize_identifier(onclick_text)
    if "lineitems" in normalized_label:
        return False
    if "statementbusinesssegmentsaxis" in normalized_onclick:
        return True
    if "|" in label and normalized_label.startswith("operatingsegments"):
        return True
    return any(row_class.startswith("rh") for row_class in row_classes) and not _is_revenue_metric_label(label)


def _normalize_segment_header_label(label: str) -> str | None:
    cleaned = _clean_table_text(label)
    if not cleaned:
        return None
    if "|" in cleaned:
        for part in (item.strip() for item in cleaned.split("|")):
            if part and not _is_aggregate_segment_name(part):
                return part
        return None
    if _is_aggregate_segment_name(cleaned):
        return None
    return cleaned


def _is_revenue_metric_label(label: str) -> bool:
    normalized_label = _normalize_identifier(label)
    return normalized_label.startswith(
        (
            "revenue",
            "salesrevenue",
            "netsales",
            "netrevenue",
        )
    )


def _clean_table_text(value: str) -> str:
    return " ".join(value.replace("\xa0", " ").split())


def _parse_table_number(value: str) -> int | float | None:
    cleaned = _clean_table_text(value)
    if not cleaned or cleaned in {"-", "—"}:
        return None
    cleaned = cleaned.replace("$", "").replace(",", "")
    if cleaned.startswith("(") and cleaned.endswith(")"):
        cleaned = f"-{cleaned[1:-1]}"
    try:
        return _json_number(cleaned)
    except ValueError:
        return None


def _iter_fact_observations(metric: str, fact_payload: dict[str, Any]) -> list[dict[str, Any]]:
    if metric == "eps":
        return _iter_ratio_observations(fact_payload)
    if metric in {"shares_outstanding", "weighted_average_diluted_shares"}:
        return _iter_share_observations(fact_payload)
    return _iter_monetary_observations(fact_payload)


def _iter_monetary_observations(fact_payload: dict[str, Any]) -> list[dict[str, Any]]:
    if not isinstance(fact_payload, dict):
        return []

    units_root = fact_payload.get("units", {})
    if not isinstance(units_root, dict):
        return []

    observations: list[dict[str, Any]] = []
    preferred_units = ["USD"] + [unit for unit in units_root if unit.startswith("USD") and unit != "USD"]
    for unit in preferred_units:
        unit_observations = units_root.get(unit)
        if not isinstance(unit_observations, list):
            continue
        observations.extend(observation for observation in unit_observations if isinstance(observation, dict))

    return observations


def _iter_ratio_observations(fact_payload: dict[str, Any]) -> list[dict[str, Any]]:
    if not isinstance(fact_payload, dict):
        return []

    units_root = fact_payload.get("units", {})
    if not isinstance(units_root, dict):
        return []

    observations: list[dict[str, Any]] = []
    preferred_units = [
        unit
        for unit in units_root
        if unit.startswith("USD/")
        or unit.endswith("/shares")
        or unit.endswith("/share")
    ]
    for unit in preferred_units:
        unit_observations = units_root.get(unit)
        if not isinstance(unit_observations, list):
            continue
        observations.extend(observation for observation in unit_observations if isinstance(observation, dict))

    return observations


def _iter_share_observations(fact_payload: dict[str, Any]) -> list[dict[str, Any]]:
    if not isinstance(fact_payload, dict):
        return []

    units_root = fact_payload.get("units", {})
    if not isinstance(units_root, dict):
        return []

    observations: list[dict[str, Any]] = []
    preferred_units = [
        unit
        for unit in units_root
        if unit == "shares" or unit.endswith("shares") or unit.endswith("share")
    ]
    for unit in preferred_units:
        unit_observations = units_root.get(unit)
        if not isinstance(unit_observations, list):
            continue
        observations.extend(observation for observation in unit_observations if isinstance(observation, dict))

    return observations


def _select_statement_period(
    filing_type: str,
    duration_candidates: list[tuple[date, date]],
    instant_period_ends: list[date],
    report_date: date | None,
) -> tuple[date | None, date | None]:
    unique_durations = sorted(set(duration_candidates), key=lambda item: (item[1] - item[0]).days)
    if report_date is not None:
        report_date_matches = [item for item in unique_durations if item[1] == report_date]
        if report_date_matches:
            if filing_type in ANNUAL_FORMS:
                return report_date_matches[-1]
            return report_date_matches[0]

    if unique_durations:
        if filing_type in ANNUAL_FORMS:
            period_start, period_end = unique_durations[-1]
        else:
            period_start, period_end = unique_durations[0]
        return period_start, period_end

    if report_date is not None:
        return report_date, report_date

    if instant_period_ends:
        period_end = max(instant_period_ends)
        return period_end, period_end

    return None, None


def _select_best_candidate(
    candidates: list[FactCandidate],
    filing_type: str,
    target_start: date | None,
    target_end: date | None,
    target_duration_days: int | None,
) -> FactCandidate | None:
    if not candidates:
        return None

    def score(candidate: FactCandidate) -> tuple[Any, ...]:
        start_penalty = 0
        end_penalty = 0
        duration_penalty = 10**9
        if target_end is not None:
            end_penalty = 0 if candidate.period_end == target_end else 1
        if target_start is not None and candidate.period_start is not None:
            start_penalty = 0 if candidate.period_start == target_start else 1
        elif target_start is not None:
            start_penalty = 1

        if candidate.period_start and candidate.period_end and target_duration_days is not None:
            duration_penalty = abs((candidate.period_end - candidate.period_start).days - target_duration_days)
            if filing_type in INTERIM_FORMS and (candidate.period_end - candidate.period_start).days > 130:
                duration_penalty += 1000

        filed_penalty = -(candidate.filed_at.toordinal()) if candidate.filed_at else 0
        return (candidate.tag_rank, end_penalty, start_penalty, duration_penalty, filed_penalty)

    return min(candidates, key=score)


def _select_best_segment_candidate(
    candidates: list[SegmentRevenueCandidate],
    filing_type: str,
    target_start: date | None,
    target_end: date | None,
    target_duration_days: int | None,
) -> SegmentRevenueCandidate | None:
    if not candidates:
        return None

    def score(candidate: SegmentRevenueCandidate) -> tuple[Any, ...]:
        start_penalty = 0
        end_penalty = 0
        duration_penalty = 10**9
        if target_end is not None:
            end_penalty = 0 if candidate.period_end == target_end else 1
        if target_start is not None and candidate.period_start is not None:
            start_penalty = 0 if candidate.period_start == target_start else 1
        elif target_start is not None:
            start_penalty = 1

        if candidate.period_start and candidate.period_end and target_duration_days is not None:
            duration_penalty = abs((candidate.period_end - candidate.period_start).days - target_duration_days)
            if filing_type in INTERIM_FORMS and (candidate.period_end - candidate.period_start).days > 130:
                duration_penalty += 1000

        filed_penalty = -(candidate.filed_at.toordinal()) if candidate.filed_at else 0
        return (candidate.tag_rank, end_penalty, start_penalty, duration_penalty, filed_penalty)

    return min(candidates, key=score)


def _select_segment_breakdown(
    candidates: list[SegmentRevenueCandidate],
    filing_type: str,
    target_start: date | None,
    target_end: date | None,
    target_duration_days: int | None,
    total_revenue: int | float | None,
) -> list[dict[str, Any]]:
    if not candidates:
        return []

    candidates_by_axis: dict[str, list[SegmentRevenueCandidate]] = {}
    for candidate in candidates:
        axis_group = f"{candidate.kind}:{candidate.axis_key}"
        candidates_by_axis.setdefault(axis_group, []).append(candidate)

    best_segments: list[SegmentRevenueCandidate] = []
    best_score: tuple[Any, ...] | None = None
    normalized_total_revenue = abs(total_revenue) if total_revenue not in (None, 0) else None

    for axis_candidates in candidates_by_axis.values():
        segments_by_member: dict[str, list[SegmentRevenueCandidate]] = {}
        for candidate in axis_candidates:
            segments_by_member.setdefault(candidate.segment_id, []).append(candidate)

        selected_segments: list[SegmentRevenueCandidate] = []
        for member_candidates in segments_by_member.values():
            selected = _select_best_segment_candidate(
                candidates=member_candidates,
                filing_type=filing_type,
                target_start=target_start,
                target_end=target_end,
                target_duration_days=target_duration_days,
            )
            if selected is not None:
                selected_segments.append(selected)

        selected_segments = [candidate for candidate in selected_segments if candidate.value > 0]
        if len(selected_segments) < 2:
            continue

        axis_revenue = sum(candidate.value for candidate in selected_segments)
        coverage_gap = 1.0
        if normalized_total_revenue:
            coverage_gap = abs(axis_revenue - normalized_total_revenue) / normalized_total_revenue

        score = (_segment_kind_penalty(selected_segments[0].kind), coverage_gap, -len(selected_segments), -axis_revenue)
        if best_score is None or score < best_score:
            best_score = score
            best_segments = selected_segments

    if not best_segments:
        return []

    segment_total = sum(candidate.value for candidate in best_segments)
    denominator = segment_total
    if normalized_total_revenue and segment_total <= normalized_total_revenue * 1.2:
        denominator = normalized_total_revenue

    payload: list[dict[str, Any]] = []
    for candidate in sorted(best_segments, key=lambda item: item.value, reverse=True):
        share = None
        if denominator:
            share = _json_number(candidate.value / denominator)
        payload.append(
            {
                "segment_id": candidate.segment_id,
                "segment_name": candidate.segment_name,
                "axis_key": candidate.axis_key,
                "axis_label": candidate.axis_label,
                "kind": candidate.kind,
                "revenue": candidate.value,
                "share_of_revenue": share,
            }
        )

    return payload


def _pick_segment_dimension(raw_value: Any) -> dict[str, str] | None:
    if raw_value in (None, ""):
        return None

    best_match: dict[str, str] | None = None
    best_rank = 99
    for part in str(raw_value).split(";"):
        axis_raw, separator, member_raw = part.strip().partition("=")
        if not separator:
            continue

        axis_key = _xbrl_local_name(axis_raw)
        member_key = _xbrl_local_name(member_raw)
        if not axis_key or not member_key:
            continue

        kind = _classify_segment_axis(axis_key)
        if kind == "other":
            continue

        segment_name = _humanize_xbrl_token(member_key)
        if _is_aggregate_segment_name(segment_name):
            continue

        rank = _segment_kind_penalty(kind)
        if rank < best_rank:
            best_rank = rank
            best_match = {
                "segment_id": _normalize_identifier(member_key),
                "segment_name": segment_name,
                "axis_key": axis_key,
                "axis_label": _humanize_xbrl_token(axis_key),
                "kind": kind,
            }

    return best_match


def _segment_kind_penalty(kind: str) -> int:
    if kind == "business":
        return 0
    if kind == "geographic":
        return 1
    return 2


def _classify_segment_axis(axis_key: str) -> str:
    normalized_axis = _normalize_identifier(axis_key)
    if any(keyword in normalized_axis for keyword in ("geograph", "region", "country", "area", "market")):
        return "geographic"
    if any(
        keyword in normalized_axis
        for keyword in ("segment", "business", "product", "service", "operating", "reportable", "lineofbusiness")
    ):
        return "business"
    return "other"


def _is_aggregate_segment_name(segment_name: str) -> bool:
    normalized_name = _normalize_identifier(segment_name)
    return normalized_name in {
        "consolidated",
        "totalsegments",
        "allsegments",
        "otherall",
        "eliminations",
        "intersegmenteliminations",
        "companywide",
        "operatingsegments",
        "reportablesegments",
        "geographicsegments",
        "businesssegments",
    } or normalized_name.startswith("total") or "elimination" in normalized_name


def _xbrl_local_name(value: str) -> str:
    token = value.split(":")[-1].split("/")[-1].split("#")[-1]
    return token.strip()


def _humanize_xbrl_token(value: str) -> str:
    token = _xbrl_local_name(value)
    for suffix in ("Axis", "Member", "Domain"):
        if token.endswith(suffix):
            token = token[: -len(suffix)]
            break
    token = token.replace("_", " ").replace("-", " ")
    token = re.sub(r"(?<!^)(?=[A-Z])", " ", token)
    return " ".join(part for part in token.split() if part)


def _build_filing_source_url(cik: str, accession_number: str, primary_document: str | None) -> str:
    accession_compact = accession_number.replace("-", "")
    numeric_cik = str(int(cik))
    if primary_document:
        return f"https://www.sec.gov/Archives/edgar/data/{numeric_cik}/{accession_compact}/{primary_document}"
    return f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json#accn={accession_number}"


def _base_form(value: str | None) -> str:
    if not value:
        return ""
    return value.split("/")[0].upper()


def _parse_date(value: Any) -> date | None:
    if value in (None, ""):
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    return date.fromisoformat(str(value))


def _json_number(value: Any) -> int | float:
    if isinstance(value, bool):
        raise ValueError("Boolean values are not valid financial facts")
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value) if value.is_integer() else value
    coerced = float(value)
    return int(coerced) if coerced.is_integer() else coerced


def _normalize_identifier(value: str) -> str:
    return "".join(character for character in value.lower() if character.isalnum())


def _value_at(values: list[Any] | None, index: int) -> Any:
    if values is None or index >= len(values):
        return None
    return values[index]


def _primary_supported_form(submissions: dict[str, Any]) -> str:
    recent = submissions.get("filings", {}).get("recent", {})
    for form in recent.get("form", []) or []:
        normalized_form = _base_form(form)
        if normalized_form in SUPPORTED_FORMS:
            return normalized_form
    return "10-K"
_ticker_cache: list[dict[str, Any]] | None = None
_ticker_cache_loaded_at: float | None = None
