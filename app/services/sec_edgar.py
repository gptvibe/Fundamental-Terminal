from __future__ import annotations

import argparse
from concurrent.futures import Future, ThreadPoolExecutor
import hashlib
import json
import logging
import re
import time
from urllib.parse import quote_plus
import xml.etree.ElementTree as ET
from collections.abc import Callable
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from typing import Any

import httpx
from bs4 import BeautifulSoup
from sqlalchemy import Select, case, delete, func, or_, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.config import SecClientConfig, build_sec_client_config, settings
from app.db.session import SessionLocal, get_engine
from app.model_engine import precompute_core_models
from app.observability import emit_structured_log
from app.models import BeneficialOwnershipReport, CapitalMarketsEvent, CommentLetter, Company, EarningsRelease, FilingEvent, FilingRiskSignal, FinancialRestatement, FinancialStatement, Form144Filing, InsiderTrade
from app.services.filing_parser import FilingParser, ParsedFilingInsight, SUPPORTED_PARSER_FORMS
from app.services.institutional_holdings import (
    get_company_institutional_holdings_last_checked,
    refresh_company_institutional_holdings,
)
from app.services.market_data import (
    build_price_history_payload_hash,
    MarketDataClient,
    MarketDataUnavailableError,
    MarketProfile,
    PriceBar,
    get_company_latest_trade_date,
    get_company_price_last_checked,
    get_company_price_history_tail,
    price_bar_windows_match,
    touch_company_price_history,
    upsert_price_history,
)
from app.services.capital_structure_intelligence import recompute_and_persist_company_capital_structure
from app.services.derived_metrics_mart import recompute_and_persist_company_derived_metrics
from app.services.earnings_intelligence import recompute_and_persist_company_earnings_model_points
from app.services.oil_scenario_overlay import refresh_company_oil_scenario_overlay
from app.services.regulated_financials import BANK_REGULATORY_STATEMENT_TYPE, collect_regulated_financial_statements
from app.services.sec_cache import prune_sec_cache_periodic, sec_http_cache
from app.services.shared_upstream_cache import shared_upstream_cache
from app.services.sec_sic import resolve_sec_sic_profile
from app.services.refresh_state import build_payload_version_hash, cache_state_for_dataset, get_dataset_state, mark_dataset_checked, release_refresh_lock, release_refresh_lock_failed
from app.services.status_stream import JobReporter

logger = logging.getLogger(__name__)

SUPPORTED_FORMS = {"10-K", "10-Q", "20-F", "40-F", "6-K"}
ANNUAL_FORMS = {"10-K", "20-F", "40-F"}
INTERIM_FORMS = {"10-Q", "6-K"}
CANONICAL_STATEMENT_TYPE = "canonical_xbrl"
FILING_PARSER_STATEMENT_TYPE = "filing_parser"
FILING_RISK_SIGNALS_DATASET = "filing_risk_signals"
RESTATEMENT_TRACKED_FORMS = {"10-K", "10-Q"}
RECONCILIATION_METRICS = ("revenue", "net_income", "operating_income")
RECONCILIATION_SUPPORTED_FORMS = SUPPORTED_PARSER_FORMS & RESTATEMENT_TRACKED_FORMS
FINANCIALS_REFRESH_FINGERPRINT_VERSION = "financials-refresh-fingerprint-v1"
INSIDER_FILINGS_FINGERPRINT_VERSION = "insider-filings-v1"
FORM144_FILINGS_FINGERPRINT_VERSION = "form144-filings-v1"
EARNINGS_RELEASES_FINGERPRINT_VERSION = "earnings-releases-v1"
COMMENT_LETTERS_FINGERPRINT_VERSION = "comment-letters-v1"
DERIVED_METRICS_INPUT_FINGERPRINT_VERSION = "derived-metrics-inputs-v1"
CAPITAL_STRUCTURE_INPUT_FINGERPRINT_VERSION = "capital-structure-inputs-v1"
EARNINGS_MODELS_INPUT_FINGERPRINT_VERSION = "earnings-models-inputs-v1"
COMPANY_RESEARCH_BRIEF_INPUT_FINGERPRINT_VERSION = "company-research-brief-inputs-v1"
CHARTS_DASHBOARD_INPUT_FINGERPRINT_VERSION = "company-charts-dashboard-inputs-v9"

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
    "cash_and_cash_equivalents": [
        (
            "us-gaap",
            [
                "CashAndCashEquivalentsAtCarryingValue",
                "Cash",
                "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents",
            ],
        ),
        (
            "ifrs-full",
            [
                "CashAndCashEquivalents",
            ],
        ),
    ],
    "short_term_investments": [
        (
            "us-gaap",
            [
                "ShortTermInvestments",
                "MarketableSecuritiesCurrent",
                "AvailableForSaleSecuritiesCurrent",
            ],
        ),
        (
            "ifrs-full",
            [
                "CurrentInvestments",
                "ShorttermInvestments",
            ],
        ),
    ],
    "cash_and_short_term_investments": [
        (
            "us-gaap",
            [
                "CashCashEquivalentsAndShortTermInvestments",
                "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalentsAndShortTermInvestments",
            ],
        ),
        (
            "ifrs-full",
            [
                "CashAndShorttermInvestments",
            ],
        ),
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
    "accounts_payable": [
        (
            "us-gaap",
            [
                "AccountsPayableCurrent",
                "AccountsPayableTradeCurrent",
            ],
        ),
        (
            "ifrs-full",
            [
                "TradeAndOtherCurrentPayables",
                "CurrentTradePayables",
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
    "current_debt": [
        (
            "us-gaap",
            [
                "DebtCurrent",
                "LongTermDebtCurrent",
                "ShortTermBorrowings",
                "CommercialPaper",
            ],
        ),
        (
            "ifrs-full",
            [
                "CurrentBorrowings",
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
    "stockholders_equity": [
        (
            "us-gaap",
            [
                "StockholdersEquity",
                "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest",
            ],
        ),
        (
            "ifrs-full",
            [
                "Equity",
                "EquityAttributableToOwnersOfParent",
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
    "depreciation_and_amortization": [
        (
            "us-gaap",
            [
                "DepreciationDepletionAndAmortization",
                "DepreciationAmortizationAndAccretionNet",
                "DepreciationAndAmortization",
            ],
        ),
        (
            "ifrs-full",
            [
                "DepreciationAmortisationAndImpairment",
                "DepreciationAndAmortisationExpense",
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

SEGMENT_SUPPLEMENTAL_TAGS: dict[str, list[tuple[str, list[str]]]] = {
    "operating_income": [
        ("us-gaap", ["OperatingIncomeLoss"]),
        ("ifrs-full", ["ProfitLossFromOperatingActivities"]),
    ],
    "assets": [
        ("us-gaap", ["NoncurrentAssets", "Assets"]),
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

SUPPLEMENTAL_CAPITAL_STRUCTURE_FACTS: dict[str, list[tuple[str, list[str]]]] = {
    "shares_issued": [
        (
            "us-gaap",
            [
                "CommonStockSharesIssued",
                "CommonStockIssuedDuringPeriodSharesNewIssues",
            ],
        ),
    ],
    "shares_repurchased": [
        (
            "us-gaap",
            [
                "CommonStockSharesRepurchased",
                "ShareRepurchasedAndRetiredDuringPeriodShares",
            ],
        ),
    ],
    "debt_maturity_due_next_twelve_months": [
        ("us-gaap", ["LongTermDebtMaturitiesRepaymentsOfPrincipalInNextTwelveMonths"]),
    ],
    "debt_maturity_due_year_two": [
        ("us-gaap", ["LongTermDebtMaturitiesRepaymentsOfPrincipalInYearTwo"]),
    ],
    "debt_maturity_due_year_three": [
        ("us-gaap", ["LongTermDebtMaturitiesRepaymentsOfPrincipalInYearThree"]),
    ],
    "debt_maturity_due_year_four": [
        ("us-gaap", ["LongTermDebtMaturitiesRepaymentsOfPrincipalInYearFour"]),
    ],
    "debt_maturity_due_year_five": [
        ("us-gaap", ["LongTermDebtMaturitiesRepaymentsOfPrincipalInYearFive"]),
    ],
    "debt_maturity_due_thereafter": [
        (
            "us-gaap",
            [
                "LongTermDebtMaturitiesRepaymentsOfPrincipalThereafter",
                "LongTermDebtMaturitiesRepaymentsOfPrincipalAfterYearFive",
            ],
        ),
    ],
    "lease_due_next_twelve_months": [
        ("us-gaap", ["OperatingLeaseLiabilityPaymentsDueNextTwelveMonths"]),
    ],
    "lease_due_year_two": [
        ("us-gaap", ["OperatingLeaseLiabilityPaymentsDueYearTwo"]),
    ],
    "lease_due_year_three": [
        ("us-gaap", ["OperatingLeaseLiabilityPaymentsDueYearThree"]),
    ],
    "lease_due_year_four": [
        ("us-gaap", ["OperatingLeaseLiabilityPaymentsDueYearFour"]),
    ],
    "lease_due_year_five": [
        ("us-gaap", ["OperatingLeaseLiabilityPaymentsDueYearFive"]),
    ],
    "lease_due_thereafter": [
        ("us-gaap", ["OperatingLeaseLiabilityPaymentsDueThereafter"]),
    ],
}


@dataclass(slots=True)
class CompanyIdentity:
    cik: str
    ticker: str
    name: str
    exchange: str | None = None
    sector: str | None = None
    market_sector: str | None = None
    market_industry: str | None = None
    sic: str | None = None


@dataclass(slots=True)
class FilingMetadata:
    accession_number: str
    form: str | None = None
    filing_date: date | None = None
    report_date: date | None = None
    acceptance_datetime: datetime | None = None
    primary_document: str | None = None
    primary_doc_description: str | None = None
    items: str | None = None


@dataclass(slots=True)
class FactCandidate:
    metric: str
    accession_number: str
    form: str
    value: int | float
    unit: str | None
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
    form: str
    filing_type: str
    filing_date: date | None
    period_start: date
    period_end: date
    source: str
    filing_acceptance_at: datetime | None
    data: dict[str, Any]
    selected_facts: dict[str, dict[str, Any]]
    reconciliation: dict[str, Any] = field(default_factory=dict)


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
    sale_context: str | None
    plan_adoption_date: date | None
    plan_modification: str | None
    plan_modification_date: date | None
    plan_signal_confidence: str | None
    plan_signal_provenance: list[str] | None
    source: str


@dataclass(slots=True)
class Form4PlanSignal:
    is_10b5_1: bool
    sale_context: str | None = None
    plan_adoption_date: date | None = None
    plan_modification: str | None = None
    plan_modification_date: date | None = None
    plan_signal_confidence: str | None = None
    plan_signal_provenance: list[str] | None = None


@dataclass(slots=True)
class NormalizedForm144Filing:
    accession_number: str
    form: str
    filing_date: date | None
    report_date: date | None
    transaction_index: int
    filer_name: str | None
    relationship_to_issuer: str | None
    issuer_name: str | None
    security_title: str | None
    planned_sale_date: date | None
    shares_to_be_sold: float | None
    aggregate_market_value: float | None
    shares_owned_after_sale: float | None
    broker_name: str | None
    source_url: str
    summary: str


@dataclass(slots=True)
class NormalizedCommentLetter:
    accession_number: str
    filing_date: date | None
    description: str
    sec_url: str


@dataclass(slots=True)
class IngestionResult:
    identifier: str
    company_id: int
    cik: str
    ticker: str
    status: str
    statements_written: int = 0
    insider_trades_written: int = 0
    form144_filings_written: int = 0
    institutional_holdings_written: int = 0
    beneficial_ownership_written: int = 0
    earnings_releases_written: int = 0
    price_points_written: int = 0
    fetched_from_sec: bool = False
    last_checked: datetime | None = None
    detail: str | None = None


@dataclass(slots=True)
class DatasetRefreshOutcome:
    written: int = 0
    error: str | None = None


@dataclass(slots=True)
class RefreshPolicy:
    company: Company | None
    force: bool
    refresh_insider_data: bool
    refresh_institutional_data: bool
    refresh_beneficial_ownership_data: bool
    statements_fresh: bool
    prices_fresh: bool
    insider_fresh: bool
    form144_fresh: bool
    earnings_fresh: bool
    institutional_fresh: bool
    beneficial_fresh: bool
    filings_fresh: bool
    capital_markets_fresh: bool
    comment_letters_fresh: bool
    has_segment_breakdown_key: bool
    relevant_last_checked_values: list[datetime | None]

    @property
    def effective_insider_fresh(self) -> bool:
        return (self.insider_fresh and self.form144_fresh) or not self.refresh_insider_data

    @property
    def effective_institutional_fresh(self) -> bool:
        return self.institutional_fresh or not self.refresh_institutional_data

    @property
    def effective_beneficial_fresh(self) -> bool:
        return self.beneficial_fresh or not self.refresh_beneficial_ownership_data

    @property
    def effective_non_core_fresh(self) -> bool:
        return self.filings_fresh and self.capital_markets_fresh and self.comment_letters_fresh

    def can_skip_sec_refresh(self) -> bool:
        return (
            self.company is not None
            and not self.force
            and self.statements_fresh
            and self.prices_fresh
            and self.has_segment_breakdown_key
            and self.effective_insider_fresh
            and self.effective_institutional_fresh
            and self.effective_beneficial_fresh
            and self.earnings_fresh
            and self.effective_non_core_fresh
        )

    def needs_segment_backfill(self) -> bool:
        return (
            self.company is not None
            and not self.force
            and self.statements_fresh
            and self.prices_fresh
            and not self.has_segment_breakdown_key
        )

    def can_refresh_beneficial_only(self) -> bool:
        return (
            self.company is not None
            and not self.force
            and self.refresh_beneficial_ownership_data
            and self.statements_fresh
            and self.prices_fresh
            and self.has_segment_breakdown_key
            and self.effective_insider_fresh
            and self.effective_institutional_fresh
            and self.earnings_fresh
            and not self.beneficial_fresh
        )

    def can_refresh_earnings_only(self) -> bool:
        return (
            self.company is not None
            and not self.force
            and self.statements_fresh
            and self.prices_fresh
            and self.has_segment_breakdown_key
            and self.effective_insider_fresh
            and self.effective_institutional_fresh
            and self.effective_beneficial_fresh
            and not self.earnings_fresh
        )

    def can_refresh_insiders_only(self) -> bool:
        return (
            self.company is not None
            and not self.force
            and self.refresh_insider_data
            and self.statements_fresh
            and self.prices_fresh
            and self.has_segment_breakdown_key
            and self.effective_institutional_fresh
            and self.effective_beneficial_fresh
            and self.earnings_fresh
            and not self.effective_insider_fresh
        )

    def can_refresh_institutional_only(self) -> bool:
        return (
            self.company is not None
            and not self.force
            and self.refresh_institutional_data
            and self.statements_fresh
            and self.prices_fresh
            and self.has_segment_breakdown_key
            and self.effective_insider_fresh
            and self.effective_beneficial_fresh
            and self.earnings_fresh
            and not self.institutional_fresh
        )

    def can_refresh_prices_only(self) -> bool:
        return (
            self.company is not None
            and not self.force
            and self.statements_fresh
            and not self.prices_fresh
            and self.has_segment_breakdown_key
            and self.effective_insider_fresh
            and self.effective_institutional_fresh
            and self.effective_beneficial_fresh
            and self.earnings_fresh
        )

    def can_refresh_filings_only(self) -> bool:
        return (
            self.company is not None
            and not self.force
            and self.statements_fresh
            and self.prices_fresh
            and self.has_segment_breakdown_key
            and self.effective_insider_fresh
            and self.effective_institutional_fresh
            and self.effective_beneficial_fresh
            and self.earnings_fresh
            and self.capital_markets_fresh
            and self.comment_letters_fresh
            and not self.filings_fresh
        )

    def can_refresh_capital_markets_only(self) -> bool:
        return (
            self.company is not None
            and not self.force
            and self.statements_fresh
            and self.prices_fresh
            and self.has_segment_breakdown_key
            and self.effective_insider_fresh
            and self.effective_institutional_fresh
            and self.effective_beneficial_fresh
            and self.earnings_fresh
            and self.filings_fresh
            and self.comment_letters_fresh
            and not self.capital_markets_fresh
        )

    def can_refresh_comment_letters_only(self) -> bool:
        return (
            self.company is not None
            and not self.force
            and self.statements_fresh
            and self.prices_fresh
            and self.has_segment_breakdown_key
            and self.effective_insider_fresh
            and self.effective_institutional_fresh
            and self.effective_beneficial_fresh
            and self.earnings_fresh
            and self.filings_fresh
            and self.capital_markets_fresh
            and not self.comment_letters_fresh
        )


@dataclass(slots=True)
class StatementAccumulator:
    accession_number: str
    filing_type: str
    filed_at: date | None = None
    report_date: date | None = None
    filing_acceptance_at: datetime | None = None
    source: str = ""
    metric_candidates: dict[str, list[FactCandidate]] = field(default_factory=dict)
    segment_revenue_candidates: list[SegmentRevenueCandidate] = field(default_factory=list)
    segment_supplemental: dict[tuple[date, str], dict[str, int | float]] = field(default_factory=dict)
    capex_candidates: list[FactCandidate] = field(default_factory=list)
    debt_issuance_candidates: list[FactCandidate] = field(default_factory=list)
    debt_repayment_candidates: list[FactCandidate] = field(default_factory=list)
    duration_candidates: list[tuple[date, date]] = field(default_factory=list)
    instant_period_ends: list[date] = field(default_factory=list)


@dataclass(slots=True)
class RefreshBootstrapInputs:
    company_identity: CompanyIdentity
    submissions: dict[str, Any]
    filing_index: dict[str, FilingMetadata]
    companyfacts: dict[str, Any]
    financials_fingerprint: str
    market_profile: MarketProfile


@dataclass(slots=True)
class PriceHistoryPrefetchResult:
    incremental_start_date: date | None
    existing_payload_hash: str | None
    price_bars: list[PriceBar] | None = None
    error: Exception | None = None


class EdgarClient:
    def __init__(self) -> None:
        self._client_config = build_sec_client_config(settings)
        self._http = httpx.Client(
            headers={
                "User-Agent": self._client_config.user_agent,
                "Accept": "application/json",
                "Accept-Encoding": "gzip, deflate",
            },
            follow_redirects=True,
            timeout=self._client_config.timeout_seconds,
        )
        self._last_request_monotonic = 0.0
        self._company_tickers_cache: list[dict[str, Any]] | None = None

    def _request(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        params = kwargs.get("params")
        headers = dict(kwargs.get("headers") or {})
        cached_response = sec_http_cache.get(method, url, params=params, headers=headers)
        if cached_response is not None:
            return cached_response

        def _fetch_response() -> httpx.Response:
            stale_entry = sec_http_cache.get_stale(method, url, params=params, headers=headers)
            request_kwargs = dict(kwargs)
            conditional_headers = None
            if stale_entry is not None:
                conditional_headers = sec_http_cache.build_conditional_headers(stale_entry, headers=headers)
            if conditional_headers is not None:
                request_kwargs["headers"] = conditional_headers
            elif headers:
                request_kwargs["headers"] = headers

            max_retries = self._client_config.max_retries
            attempt = 0
            while True:
                self._throttle()
                response = self._http.request(method, url, **request_kwargs)
                self._last_request_monotonic = time.monotonic()
                if response.status_code == 304 and stale_entry is not None:
                    response.read()
                    return sec_http_cache.revalidate(
                        method,
                        url,
                        stale_entry,
                        response,
                        params=params,
                        headers=headers,
                    )
                if response.status_code in {429, 500, 502, 503, 504} and attempt < max_retries - 1:
                    retry_after = response.headers.get("retry-after")
                    wait = _retry_wait(retry_after, self._client_config, attempt)
                    response.close()
                    time.sleep(wait)
                    attempt += 1
                    continue
                response.raise_for_status()
                sec_http_cache.put(method, url, response, params=params, headers=headers)
                return response

        cache_key = sec_http_cache.cache_key(method, url, params=params)
        if cache_key is None:
            return _fetch_response()
        return shared_upstream_cache.run_singleflight(
            f"sec:{method.upper()}:{cache_key}",
            wait_for=lambda: sec_http_cache.get(method, url, params=params, headers=headers),
            fill=_fetch_response,
        )

    def close(self) -> None:
        self._http.close()

    def _throttle(self) -> None:
        elapsed = time.monotonic() - self._last_request_monotonic
        wait_for = self._client_config.min_request_interval_seconds - elapsed
        if wait_for > 0:
            time.sleep(wait_for)

    def _get_json(self, url: str) -> dict[str, Any]:
        response = self._request("GET", url)
        cached_json = response.extensions.get("cached_json_payload")
        if isinstance(cached_json, dict):
            return cached_json
        return response.json()

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
                sic=str(submissions.get("sic") or "").strip() or None,
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

        browse_edgar_match = self._resolve_company_from_browse_edgar(lookup)
        if browse_edgar_match is not None:
            return browse_edgar_match

        raise ValueError(f"Unable to resolve SEC company for '{identifier}'")

    def _resolve_company_from_browse_edgar(self, lookup: str) -> CompanyIdentity | None:
        # The SEC ticker file can lag behind active symbols; browse-edgar often resolves them.
        lookup_token = quote_plus(lookup)
        url = (
            "https://www.sec.gov/cgi-bin/browse-edgar"
            f"?action=getcompany&owner=exclude&count=1&CIK={lookup_token}&output=atom"
        )

        try:
            payload = self._get_text(url)
        except Exception:
            return None

        atom_identity = self._parse_browse_edgar_atom_identity(payload, lookup)
        if atom_identity is not None:
            return atom_identity

        return self._parse_browse_edgar_html_identity(payload, lookup)

    def _parse_browse_edgar_atom_identity(self, payload: str, lookup: str) -> CompanyIdentity | None:
        try:
            root = ET.fromstring(payload)
        except ET.ParseError:
            return None

        cik = (root.findtext(".//{*}company-info/{*}cik") or "").strip()
        if not cik.isdigit():
            return None

        conformed_name = (root.findtext(".//{*}company-info/{*}conformed-name") or "").strip()
        ticker = lookup.upper()
        name = conformed_name or ticker
        return CompanyIdentity(cik=cik.zfill(10), ticker=ticker, name=name)

    def _parse_browse_edgar_html_identity(self, payload: str, lookup: str) -> CompanyIdentity | None:
        if "No matching Ticker Symbol." in payload:
            return None

        cik_match = re.search(r"CIK#?:\s*(\d{10})", payload)
        if cik_match is None:
            cik_match = re.search(r"CIK=(\d{10})", payload)
        if cik_match is None:
            return None

        soup = BeautifulSoup(payload, "html.parser")
        company_name_node = soup.select_one("span.companyName")
        company_name = company_name_node.get_text(" ", strip=True) if company_name_node else ""
        name = re.sub(r"\s+CIK#?:\s*\d{10}.*$", "", company_name).strip() if company_name else ""
        ticker = lookup.upper()

        return CompanyIdentity(cik=cik_match.group(1), ticker=ticker, name=name or ticker)

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
                acceptance_datetime=_parse_datetime_value(_value_at(arrays.get("acceptanceDateTime"), position)),
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

    def get_correspondence_filings(
        self,
        cik: str,
        submissions: dict[str, Any],
        *,
        filing_index: dict[str, FilingMetadata] | None = None,
    ) -> list[NormalizedCommentLetter]:
        scanned_index = filing_index or self.build_filing_index(submissions)
        rows: list[NormalizedCommentLetter] = []
        for metadata in scanned_index.values():
            if _base_form(metadata.form) != "CORRESP":
                continue
            description = (metadata.primary_doc_description or "").strip() or "SEC correspondence"
            rows.append(
                NormalizedCommentLetter(
                    accession_number=metadata.accession_number,
                    filing_date=metadata.filing_date,
                    description=description,
                    sec_url=_build_archive_filing_url(cik, metadata.accession_number, metadata.primary_document),
                )
            )

        rows.sort(key=lambda item: (item.filing_date or date.min, item.accession_number), reverse=True)
        return rows


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

        for metric, taxonomy_groups in SUPPLEMENTAL_CAPITAL_STRUCTURE_FACTS.items():
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
        self._collect_segment_supplemental_candidates(
            facts_root=facts_root,
            filing_index=filing_index,
            statements=statements,
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

    def _collect_segment_supplemental_candidates(
        self,
        facts_root: dict[str, Any],
        filing_index: dict[str, FilingMetadata],
        statements: dict[str, StatementAccumulator],
    ) -> None:
        for metric, taxonomy_groups in SEGMENT_SUPPLEMENTAL_TAGS.items():
            for taxonomy, tags in taxonomy_groups:
                taxonomy_root = facts_root.get(taxonomy, {})
                if not isinstance(taxonomy_root, dict):
                    continue
                for tag in tags:
                    fact_payload = taxonomy_root.get(tag, {})
                    for observation in _iter_monetary_observations(fact_payload):
                        dim = _pick_segment_dimension(observation.get("segment"))
                        if dim is None:
                            continue
                        accession_number = observation.get("accn")
                        if not accession_number:
                            continue
                        accumulator = statements.get(accession_number)
                        if accumulator is None:
                            continue
                        filing_metadata = filing_index.get(accession_number)
                        form = _base_form(observation.get("form") or (filing_metadata.form if filing_metadata else None))
                        if form not in SUPPORTED_FORMS:
                            continue
                        raw_value = observation.get("val")
                        if raw_value is None:
                            continue
                        period_end = _parse_date(observation.get("end")) or (filing_metadata.report_date if filing_metadata else None)
                        if period_end is None:
                            continue
                        key: tuple[date, str] = (period_end, dim["segment_id"])
                        entry = accumulator.segment_supplemental.setdefault(key, {})
                        if metric not in entry:
                            entry[metric] = _json_number(raw_value)

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
        for metric in SUPPLEMENTAL_CAPITAL_STRUCTURE_FACTS:
            data[metric] = None
        data["capex"] = None
        data["debt_issuance"] = None
        data["debt_repayment"] = None
        data["debt_changes"] = None
        data["free_cash_flow"] = None
        data["segment_breakdown"] = []
        selected_facts: dict[str, dict[str, Any]] = {}

        for metric, candidates in accumulator.metric_candidates.items():
            selected = _select_best_candidate(
                candidates=candidates,
                filing_type=filing_type,
                target_start=period_start,
                target_end=period_end,
                target_duration_days=target_duration_days,
            )
            data[metric] = selected.value if selected is not None else None
            if selected is not None:
                selected_facts[metric] = _candidate_fact_metadata(selected, source=accumulator.source)

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
            selected_facts["capex"] = _candidate_fact_metadata(capex_candidate, source=accumulator.source)
        if debt_issuance_candidate is not None or debt_repayment_candidate is not None:
            issuance_value = abs(debt_issuance_candidate.value) if debt_issuance_candidate is not None else 0
            repayment_value = abs(debt_repayment_candidate.value) if debt_repayment_candidate is not None else 0
            data["debt_issuance"] = _json_number(issuance_value) if debt_issuance_candidate is not None else None
            data["debt_repayment"] = _json_number(repayment_value) if debt_repayment_candidate is not None else None
            data["debt_changes"] = _json_number(issuance_value - repayment_value)
            if debt_issuance_candidate is not None:
                selected_facts["debt_issuance"] = _candidate_fact_metadata(debt_issuance_candidate, source=accumulator.source)
            if debt_repayment_candidate is not None:
                selected_facts["debt_repayment"] = _candidate_fact_metadata(debt_repayment_candidate, source=accumulator.source)
            selected_facts["debt_changes"] = {
                "issued": _candidate_fact_metadata(debt_issuance_candidate, source=accumulator.source) if debt_issuance_candidate is not None else None,
                "repaid": _candidate_fact_metadata(debt_repayment_candidate, source=accumulator.source) if debt_repayment_candidate is not None else None,
            }
        if data.get("operating_cash_flow") is not None and capex_candidate is not None:
            # Canonical free_cash_flow is defined as OCF - capex from filing facts.
            # This is a practical cash-flow proxy and may still reflect financing-related
            # interest effects present in reported operating cash flow.
            data["free_cash_flow"] = _json_number(data["operating_cash_flow"] - abs(capex_candidate.value))
            selected_facts["free_cash_flow"] = {
                "operating_cash_flow": selected_facts.get("operating_cash_flow"),
                "capex": selected_facts.get("capex"),
            }
        else:
            data["free_cash_flow"] = None

        if data.get("cash_and_short_term_investments") is None:
            cash = data.get("cash_and_cash_equivalents")
            short_term = data.get("short_term_investments")
            if cash is not None and short_term is not None:
                data["cash_and_short_term_investments"] = _json_number(float(cash) + float(short_term))

        data["segment_breakdown"] = _select_segment_breakdown(
            candidates=accumulator.segment_revenue_candidates,
            filing_type=filing_type,
            target_start=period_start,
            target_end=period_end,
            target_duration_days=target_duration_days,
            total_revenue=data.get("revenue"),
        )

        if data["segment_breakdown"] and period_end is not None:
            for segment in data["segment_breakdown"]:
                key: tuple[date, str] = (period_end, segment["segment_id"])
                supp = accumulator.segment_supplemental.get(key, {})
                segment.setdefault("operating_income", supp.get("operating_income"))
                segment.setdefault("assets", supp.get("assets"))

        if not any(value is not None for key, value in data.items() if key != "segment_breakdown"):
            return None

        return NormalizedStatement(
            accession_number=accumulator.accession_number,
            form=_normalize_form_text(accumulator.filing_type),
            filing_type=filing_type,
            filing_date=accumulator.filed_at,
            period_start=period_start,
            period_end=period_end,
            source=accumulator.source,
            filing_acceptance_at=accumulator.filing_acceptance_at,
            data=data,
            selected_facts=selected_facts,
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

    def _load_refresh_bootstrap_inputs(
        self,
        identifier: str,
        reporter: JobReporter,
    ) -> RefreshBootstrapInputs:
        company_identity = self.client.resolve_company(identifier)
        market_profile_executor: ThreadPoolExecutor | None = None
        market_profile_future: Future[MarketProfile] | None = None

        if not settings.strict_official_mode and getattr(settings, "refresh_aux_io_max_workers", 1) > 1:
            market_profile_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="refresh-market")
            market_profile_future = market_profile_executor.submit(self.market_data.get_market_profile, company_identity.ticker)

        try:
            submissions = self.client.get_submissions(company_identity.cik)
            reporter.step("filing", f"Fetching {_primary_supported_form(submissions)}...")
            filing_index = self.client.build_filing_index(submissions)
            companyfacts = self.client.get_companyfacts(company_identity.cik)
            financials_fingerprint = _build_financials_refresh_fingerprint(companyfacts, filing_index)
            sec_market_profile = resolve_sec_sic_profile(
                submissions.get("sic"),
                submissions.get("sicDescription") or company_identity.sector,
            )
            market_profile = self._resolve_market_profile(
                company_identity=company_identity,
                sec_market_profile=sec_market_profile,
                reporter=reporter,
                prefetched_market_profile=market_profile_future,
            )
            return RefreshBootstrapInputs(
                company_identity=company_identity,
                submissions=submissions,
                filing_index=filing_index,
                companyfacts=companyfacts,
                financials_fingerprint=financials_fingerprint,
                market_profile=market_profile,
            )
        finally:
            if market_profile_executor is not None:
                market_profile_executor.shutdown(wait=True)

    def _resolve_market_profile(
        self,
        *,
        company_identity: CompanyIdentity,
        sec_market_profile,
        reporter: JobReporter,
        prefetched_market_profile: Future[MarketProfile] | None = None,
    ) -> MarketProfile:
        try:
            if settings.strict_official_mode:
                reporter.step("market", "Using SEC SIC classification for market sector and industry.")
                return MarketProfile(
                    sector=sec_market_profile.market_sector,
                    industry=sec_market_profile.market_industry,
                )
            if prefetched_market_profile is not None:
                return prefetched_market_profile.result()
            return self.market_data.get_market_profile(company_identity.ticker)
        except Exception as exc:
            logger.exception("Market profile lookup failed for %s", company_identity.ticker)
            reporter.step("market", f"Market profile lookup failed: {exc}")
            return MarketProfile(
                sector=sec_market_profile.market_sector,
                industry=sec_market_profile.market_industry,
            )

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
        payload_version_hash = _build_filing_metadata_fingerprint(
            INSIDER_FILINGS_FINGERPRINT_VERSION,
            insider_filings,
        )

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
        _touch_company_insider_trades(
            session,
            company.id,
            checked_at,
            payload_version_hash=payload_version_hash,
        )
        return trades_written

    def _refresh_form144_filings(
        self,
        session: Session,
        company: Company,
        filing_index: dict[str, FilingMetadata],
        checked_at: datetime,
        reporter: JobReporter,
        *,
        force: bool = False,
    ) -> int:
        existing_accessions = _existing_form144_accessions(session, company.id)
        session.commit()
        form144_filings = [
            metadata
            for metadata in filing_index.values()
            if _base_form(metadata.form) == "144"
        ]
        form144_filings.sort(
            key=lambda metadata: (
                metadata.filing_date or date.min,
                metadata.accession_number,
            ),
            reverse=True,
        )
        form144_filings = form144_filings[: settings.sec_form4_max_filings_per_refresh]
        payload_version_hash = _build_filing_metadata_fingerprint(
            FORM144_FILINGS_FINGERPRINT_VERSION,
            form144_filings,
        )

        candidate_filings = form144_filings if force else [
            metadata for metadata in form144_filings if metadata.accession_number not in existing_accessions
        ]
        if candidate_filings:
            reporter.step("form144", f"Fetching {len(candidate_filings)} Form 144 filing(s)...")
        else:
            reporter.step("form144", "Checking cached Form 144 coverage...")

        normalized_filings: list[NormalizedForm144Filing] = []
        for metadata in candidate_filings:
            source_url, payload = _load_form144_document(self.client, company.cik, metadata)
            normalized_filings.extend(
                _parse_form144_filings(
                    payload=payload,
                    source_url=source_url,
                    filing_metadata=metadata,
                )
            )

        reporter.step("database", "Saving Form 144 filings to database...")
        filings_written = 0
        if normalized_filings:
            filings_written = _upsert_form144_filings(
                session=session,
                company=company,
                normalized_filings=normalized_filings,
                checked_at=checked_at,
            )
        _touch_company_form144_filings(
            session,
            company.id,
            checked_at,
            payload_version_hash=payload_version_hash,
        )
        return filings_written

    def _refresh_earnings_releases(
        self,
        session: Session,
        company: Company,
        filing_index: dict[str, FilingMetadata],
        checked_at: datetime,
        reporter: JobReporter,
        *,
        force: bool = False,
    ) -> int:
        from app.services.earnings_release import (
            collect_earnings_releases,
            is_earnings_release_filing_candidate,
            upsert_earnings_releases,
        )

        if force:
            session.execute(delete(EarningsRelease).where(EarningsRelease.company_id == company.id))
            session.flush()
            existing_accessions: set[str] = set()
        else:
            existing_accessions = _existing_earnings_release_accessions(session, company.id)
        session.commit()
        earnings_filings = [
            metadata
            for metadata in filing_index.values()
            if is_earnings_release_filing_candidate(metadata)
        ]
        earnings_filings.sort(
            key=lambda metadata: (
                metadata.filing_date or date.min,
                metadata.accession_number,
            ),
            reverse=True,
        )
        earnings_filings = earnings_filings[: settings.sec_form4_max_filings_per_refresh]
        payload_version_hash = _build_filing_metadata_fingerprint(
            EARNINGS_RELEASES_FINGERPRINT_VERSION,
            earnings_filings,
        )

        candidate_filings = earnings_filings if force else [
            metadata for metadata in earnings_filings if metadata.accession_number not in existing_accessions
        ]
        if candidate_filings:
            reporter.step("earnings", f"Fetching {len(candidate_filings)} earnings release filing(s)...")
        else:
            reporter.step("earnings", "Checking cached earnings release coverage...")

        normalized_releases = collect_earnings_releases(
            company.cik,
            {metadata.accession_number: metadata for metadata in candidate_filings},
            client=self.client,
        )

        reporter.step("database", "Saving earnings releases to database...")
        releases_written = 0
        if normalized_releases:
            releases_written = upsert_earnings_releases(
                session=session,
                company=company,
                releases=normalized_releases,
                checked_at=checked_at,
            )
        _touch_company_earnings_releases(
            session,
            company.id,
            checked_at,
            payload_version_hash=payload_version_hash,
        )
        return releases_written

    def refresh_statements(
        self,
        session: Session,
        company: Company,
        *,
        filing_index: dict[str, FilingMetadata],
        companyfacts: dict[str, Any],
        parsed_filing_insights: list[ParsedFilingInsight],
        checked_at: datetime,
        reporter: JobReporter,
        payload_version_hash: str | None = None,
    ) -> int:
        reporter.step("normalize", "Normalizing XBRL...")
        normalized_statements = self.normalizer.normalize(
            cik=company.cik,
            companyfacts=companyfacts,
            filing_index=filing_index,
        )
        regulated_financial_statements = []
        try:
            regulated_financial_statements = collect_regulated_financial_statements(company, sec_financials=normalized_statements)
        except Exception as exc:
            logger.exception("Unable to refresh regulated financial statements for %s", company.ticker)
            reporter.step("regulated", f"Regulated financial refresh unavailable: {exc}")
        self._populate_segment_breakdowns(normalized_statements, reporter)
        _attach_statement_reconciliations(normalized_statements, parsed_filing_insights, checked_at)

        reporter.step("database", "Saving to database...")
        statements_written = _upsert_statements(
            session=session,
            company=company,
            normalized_statements=normalized_statements,
            checked_at=checked_at,
        )
        if regulated_financial_statements:
            statements_written += _upsert_statements(
                session=session,
                company=company,
                normalized_statements=regulated_financial_statements,
                checked_at=checked_at,
                statement_type=BANK_REGULATORY_STATEMENT_TYPE,
            )
        _replace_financial_restatements(
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
        _replace_filing_risk_signals(
            session=session,
            company=company,
            parsed_insights=parsed_filing_insights,
            checked_at=checked_at,
            payload_version_hash=payload_version_hash,
        )
        _touch_company_statements(session, company.id, checked_at, payload_version_hash=payload_version_hash)
        precompute_core_models(session, company.id, reporter=reporter)
        return statements_written + parsed_statements_written

    def refresh_prices(
        self,
        session: Session,
        company: Company,
        *,
        checked_at: datetime,
        reporter: JobReporter,
        refresh_profile: bool = False,
        strict_message: str = "Strict official mode enabled; Yahoo price refresh skipped.",
        prefetched_price_history: PriceHistoryPrefetchResult | None = None,
    ) -> int:
        if settings.strict_official_mode:
            if refresh_profile:
                strict_profile = resolve_sec_sic_profile(None, company.sector)
                if strict_profile.market_sector:
                    company.market_sector = strict_profile.market_sector
                if strict_profile.market_industry:
                    company.market_industry = strict_profile.market_industry
            reporter.step("market", strict_message)
            return 0

        if refresh_profile:
            market_profile = self.market_data.get_market_profile(company.ticker)
            if market_profile.sector:
                company.market_sector = market_profile.sector
            if market_profile.industry:
                company.market_industry = market_profile.industry

        if prefetched_price_history is not None:
            incremental_start_date = prefetched_price_history.incremental_start_date
            existing_payload_hash = prefetched_price_history.existing_payload_hash
            reporter.step(
                "market",
                "Using prefetched price history tail..." if incremental_start_date is not None else "Using prefetched full price history...",
            )
            prefetch_error = prefetched_price_history.error
            if isinstance(prefetch_error, MarketDataUnavailableError):
                reporter.step("market", f"{prefetch_error} Marking prices checked without cached bars.")
                touch_company_price_history(
                    session,
                    company.id,
                    checked_at,
                    payload_version_hash=existing_payload_hash,
                    touch_rows=False,
                )
                return 0
            if prefetch_error is not None:
                raise prefetch_error
            price_bars = prefetched_price_history.price_bars or []
        else:
            try:
                latest_trade_date = get_company_latest_trade_date(session, company.id)
            except AttributeError:
                latest_trade_date = None
            incremental_start_date = None
            if latest_trade_date is not None:
                incremental_start_date = latest_trade_date - timedelta(days=settings.market_history_overlap_days)

            reporter.step(
                "market",
                "Fetching price history tail..." if incremental_start_date is not None else "Fetching full price history...",
            )
            existing_state = get_dataset_state(session, company.id, "prices")
            existing_payload_hash = existing_state.payload_version_hash if existing_state is not None else None
            try:
                price_bars = self.market_data.get_price_history(company.ticker, start_date=incremental_start_date)
            except MarketDataUnavailableError as exc:
                reporter.step("market", f"{exc} Marking prices checked without cached bars.")
                touch_company_price_history(
                    session,
                    company.id,
                    checked_at,
                    payload_version_hash=existing_payload_hash,
                    touch_rows=False,
                )
                return 0

        if not price_bars:
            reporter.step("market", f"No Yahoo price history returned for {company.ticker}; marking prices checked without cached bars.")
            touch_company_price_history(
                session,
                company.id,
                checked_at,
                payload_version_hash=existing_payload_hash,
                touch_rows=False,
            )
            return 0

        payload_version_hash = build_price_history_payload_hash(price_bars)
        if incremental_start_date is not None:
            stored_tail = get_company_price_history_tail(
                session,
                company.id,
                start_date=incremental_start_date,
            )
            if price_bar_windows_match(price_bars, stored_tail):
                reporter.step("market", "Price history tail unchanged; marking prices checked without rewriting bars.")
                touch_company_price_history(
                    session,
                    company.id,
                    checked_at,
                    payload_version_hash=payload_version_hash,
                    touch_rows=False,
                    invalidate_hot_cache=False,
                )
                return 0

        reporter.step("database", "Saving price history to database...")
        price_points_written = upsert_price_history(
            session=session,
            company=company,
            price_bars=price_bars,
            checked_at=checked_at,
        )
        touch_company_price_history(
            session,
            company.id,
            checked_at,
            payload_version_hash=payload_version_hash,
        )
        return price_points_written

    def _prefetch_price_history(
        self,
        *,
        ticker: str,
        incremental_start_date: date | None,
        existing_payload_hash: str | None,
    ) -> PriceHistoryPrefetchResult:
        try:
            price_bars = self.market_data.get_price_history(ticker, start_date=incremental_start_date)
            return PriceHistoryPrefetchResult(
                incremental_start_date=incremental_start_date,
                existing_payload_hash=existing_payload_hash,
                price_bars=price_bars,
            )
        except Exception as exc:
            return PriceHistoryPrefetchResult(
                incremental_start_date=incremental_start_date,
                existing_payload_hash=existing_payload_hash,
                error=exc,
            )

    def refresh_beneficial_ownership(
        self,
        session: Session,
        company: Company,
        *,
        filing_index: dict[str, FilingMetadata],
        checked_at: datetime,
        reporter: JobReporter,
        announce: bool = True,
    ) -> int:
        if announce:
            reporter.step("beneficial", "Caching beneficial ownership filings...")
        from app.services.beneficial_ownership import (  # local import avoids circular dependency
            collect_beneficial_ownership_reports,
            upsert_beneficial_ownership_reports,
        )

        reports = collect_beneficial_ownership_reports(company.cik, filing_index, client=self.client)
        return upsert_beneficial_ownership_reports(session, company, reports, checked_at=checked_at)

    def refresh_insiders(
        self,
        session: Session,
        company: Company,
        *,
        filing_index: dict[str, FilingMetadata],
        checked_at: datetime,
        reporter: JobReporter,
        force: bool = False,
    ) -> int:
        return self._refresh_insider_trades(
            session=session,
            company=company,
            filing_index=filing_index,
            checked_at=checked_at,
            reporter=reporter,
            force=force,
        )

    def refresh_form144(
        self,
        session: Session,
        company: Company,
        *,
        filing_index: dict[str, FilingMetadata],
        checked_at: datetime,
        reporter: JobReporter,
        force: bool = False,
    ) -> int:
        return self._refresh_form144_filings(
            session=session,
            company=company,
            filing_index=filing_index,
            checked_at=checked_at,
            reporter=reporter,
            force=force,
        )

    def refresh_institutional(
        self,
        session: Session,
        company: Company,
        *,
        checked_at: datetime,
        reporter: JobReporter,
        force: bool = False,
    ) -> int:
        return refresh_company_institutional_holdings(
            session=session,
            company=company,
            checked_at=checked_at,
            reporter=reporter,
            force=force,
        )

    def refresh_earnings(
        self,
        session: Session,
        company: Company,
        *,
        filing_index: dict[str, FilingMetadata],
        checked_at: datetime,
        reporter: JobReporter,
        force: bool = False,
    ) -> int:
        return self._refresh_earnings_releases(
            session=session,
            company=company,
            filing_index=filing_index,
            checked_at=checked_at,
            reporter=reporter,
            force=force,
        )

    def refresh_events(
        self,
        session: Session,
        company: Company,
        *,
        filing_index: dict[str, FilingMetadata],
        checked_at: datetime,
        reporter: JobReporter,
    ) -> int:
        reporter.step("events", "Caching 8-K filing events...")
        from app.services.eight_k_events import collect_filing_events, upsert_filing_events

        filing_events = collect_filing_events(company.cik, filing_index)
        return upsert_filing_events(
            session=session,
            company=company,
            events=filing_events,
            checked_at=checked_at,
        )

    def refresh_capital_markets(
        self,
        session: Session,
        company: Company,
        *,
        filing_index: dict[str, FilingMetadata],
        checked_at: datetime,
        reporter: JobReporter,
    ) -> int:
        reporter.step("capital", "Caching capital markets filings...")
        from app.services.capital_markets import collect_capital_markets_events, upsert_capital_markets_events

        capital_markets_events = collect_capital_markets_events(company.cik, filing_index)
        return upsert_capital_markets_events(
            session=session,
            company=company,
            events=capital_markets_events,
            checked_at=checked_at,
        )

    def refresh_comment_letters(
        self,
        session: Session,
        company: Company,
        *,
        submissions: dict[str, Any],
        filing_index: dict[str, FilingMetadata],
        checked_at: datetime,
        reporter: JobReporter,
        force: bool = False,
    ) -> int:
        reporter.step("corresp", "Caching SEC correspondence filings...")
        existing_accessions = _existing_comment_letter_accessions(session, company.id)
        session.commit()

        normalized_letters = self.client.get_correspondence_filings(
            company.cik,
            submissions,
            filing_index=filing_index,
        )
        payload_version_hash = build_payload_version_hash(
            version=COMMENT_LETTERS_FINGERPRINT_VERSION,
            payload=normalized_letters,
        )
        candidate_letters = normalized_letters if force else [
            letter for letter in normalized_letters if letter.accession_number not in existing_accessions
        ]

        reporter.step("database", "Saving SEC correspondence filings to database...")
        letters_written = 0
        if candidate_letters:
            letters_written = _upsert_comment_letters(
                session=session,
                company=company,
                comment_letters=candidate_letters,
                checked_at=checked_at,
            )
        _touch_company_comment_letters(
            session,
            company.id,
            checked_at,
            payload_version_hash=payload_version_hash,
        )
        return letters_written

    def _build_refresh_policy(
        self,
        session: Session,
        local_company: Company | None,
        checked_at: datetime,
        force: bool,
        *,
        refresh_insider_data: bool,
        refresh_institutional_data: bool,
        refresh_beneficial_ownership_data: bool,
    ) -> RefreshPolicy:
        latest_statement_checked = _latest_company_last_checked(session, local_company.id) if local_company else None
        latest_price_checked = get_company_price_last_checked(session, local_company.id) if local_company else None
        latest_insider_checked = _latest_insider_trade_last_checked(session, local_company) if local_company else None
        latest_form144_checked = _latest_form144_last_checked(session, local_company) if local_company else None
        latest_earnings_checked = _latest_earnings_last_checked(session, local_company) if local_company else None
        latest_institutional_checked = (
            get_company_institutional_holdings_last_checked(session, local_company) if local_company else None
        )
        latest_beneficial_checked = (
            _latest_beneficial_ownership_last_checked(session, local_company) if local_company else None
        )
        latest_filing_event_checked = _latest_filing_event_last_checked(session, local_company) if local_company else None
        latest_capital_markets_checked = _latest_capital_markets_last_checked(session, local_company) if local_company else None
        latest_comment_letter_checked = _latest_comment_letter_last_checked(session, local_company) if local_company else None
        has_segment_breakdown_key = (
            _latest_statement_has_segment_breakdown_key(session, local_company.id) if local_company else False
        )

        freshness_cutoff = checked_at - timedelta(hours=settings.freshness_window_hours)
        statements_fresh = latest_statement_checked is not None and latest_statement_checked >= freshness_cutoff
        prices_fresh = latest_price_checked is not None and latest_price_checked >= freshness_cutoff
        if settings.strict_official_mode:
            latest_price_checked = None
            prices_fresh = True
        insider_fresh = latest_insider_checked is not None and latest_insider_checked >= freshness_cutoff
        form144_fresh = latest_form144_checked is not None and latest_form144_checked >= freshness_cutoff
        earnings_fresh = latest_earnings_checked is not None and latest_earnings_checked >= freshness_cutoff
        institutional_fresh = latest_institutional_checked is not None and latest_institutional_checked >= freshness_cutoff
        beneficial_fresh = latest_beneficial_checked is not None and latest_beneficial_checked >= freshness_cutoff
        filings_fresh = latest_filing_event_checked is not None and latest_filing_event_checked >= freshness_cutoff
        capital_markets_fresh = latest_capital_markets_checked is not None and latest_capital_markets_checked >= freshness_cutoff
        comment_letters_fresh = latest_comment_letter_checked is not None and latest_comment_letter_checked >= freshness_cutoff

        relevant_last_checked_values = [
            latest_statement_checked,
            latest_price_checked,
            latest_earnings_checked,
            latest_filing_event_checked,
            latest_capital_markets_checked,
            latest_comment_letter_checked,
        ]
        if refresh_insider_data:
            relevant_last_checked_values.append(latest_insider_checked)
            relevant_last_checked_values.append(latest_form144_checked)
        if refresh_institutional_data:
            relevant_last_checked_values.append(latest_institutional_checked)
        if refresh_beneficial_ownership_data:
            relevant_last_checked_values.append(latest_beneficial_checked)

        return RefreshPolicy(
            company=local_company,
            force=force,
            refresh_insider_data=refresh_insider_data,
            refresh_institutional_data=refresh_institutional_data,
            refresh_beneficial_ownership_data=refresh_beneficial_ownership_data,
            statements_fresh=statements_fresh,
            prices_fresh=prices_fresh,
            insider_fresh=insider_fresh,
            form144_fresh=form144_fresh,
            earnings_fresh=earnings_fresh,
            institutional_fresh=institutional_fresh,
            beneficial_fresh=beneficial_fresh,
            filings_fresh=filings_fresh,
            capital_markets_fresh=capital_markets_fresh,
            comment_letters_fresh=comment_letters_fresh,
            has_segment_breakdown_key=has_segment_breakdown_key,
            relevant_last_checked_values=relevant_last_checked_values,
        )

    def _run_dataset_job(
        self,
        session: Session,
        company: Company,
        reporter: JobReporter,
        *,
        stage: str,
        label: str,
        job: Callable[[], int],
    ) -> DatasetRefreshOutcome:
        try:
            written = job()
            session.commit()
            return DatasetRefreshOutcome(written=written)
        except Exception as exc:
            session.rollback()
            logger.exception("%s refresh failed for %s", label, company.ticker)
            message = f"{label} refresh failed: {exc}"
            reporter.step(stage, message)
            return DatasetRefreshOutcome(error=message)

    def _refresh_cached_company(
        self,
        session: Session,
        identifier: str,
        checked_at: datetime,
        reporter: JobReporter,
        policy: RefreshPolicy,
    ) -> IngestionResult | None:
        local_company = policy.company
        if local_company is None:
            return None

        if policy.can_skip_sec_refresh():
            _refresh_company_brief_readiness_caches(
                session,
                local_company.id,
                checked_at,
                reporter,
                force=policy.force,
                include_capital_structure=True,
            )
            _refresh_company_dashboard_caches(
                session,
                local_company,
                checked_at,
                reporter,
                force=policy.force,
                include_derived_metrics=True,
                include_oil_scenario_overlay=True,
                include_earnings_models=True,
            )
            reporter.complete("Using fresh cached data.")
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
                earnings_releases_written=0,
                price_points_written=0,
                fetched_from_sec=False,
                last_checked=min(
                    value
                    for value in policy.relevant_last_checked_values
                    if value is not None
                ),
                detail="Freshness window still valid",
            )

        if policy.needs_segment_backfill():
            reporter.step("cache", "Cached filings need segment metadata backfill...")

        if policy.can_refresh_beneficial_only():
            session.commit()
            reporter.step("sec", "Checking SEC for new beneficial ownership filings...")
            submissions = self.client.get_submissions(local_company.cik)
            filing_index = self.client.build_filing_index(submissions)
            beneficial_ownership_written = self.refresh_beneficial_ownership(
                session=session,
                company=local_company,
                filing_index=filing_index,
                checked_at=checked_at,
                reporter=reporter,
                announce=False,
            )
            _refresh_company_brief_readiness_caches(session, local_company.id, checked_at, reporter, force=policy.force)
            _refresh_company_dashboard_caches(session, local_company, checked_at, reporter, force=policy.force)
            session.commit()
            reporter.complete("Refresh and compute complete.")
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

        if policy.can_refresh_earnings_only():
            session.commit()
            reporter.step("sec", "Checking SEC for new earnings releases...")
            submissions = self.client.get_submissions(local_company.cik)
            filing_index = self.client.build_filing_index(submissions)
            earnings_releases_written = self.refresh_earnings(
                session=session,
                company=local_company,
                filing_index=filing_index,
                checked_at=checked_at,
                reporter=reporter,
                force=policy.force,
            )
            _refresh_company_brief_readiness_caches(session, local_company.id, checked_at, reporter, force=policy.force)
            _refresh_company_dashboard_caches(
                session,
                local_company,
                checked_at,
                reporter,
                force=policy.force,
                include_earnings_models=True,
            )
            session.commit()
            reporter.complete("Refresh and compute complete.")
            return IngestionResult(
                identifier=identifier,
                company_id=local_company.id,
                cik=local_company.cik,
                ticker=local_company.ticker,
                status="fetched",
                statements_written=0,
                insider_trades_written=0,
                form144_filings_written=0,
                institutional_holdings_written=0,
                beneficial_ownership_written=0,
                earnings_releases_written=earnings_releases_written,
                price_points_written=0,
                fetched_from_sec=True,
                last_checked=checked_at,
                detail=(
                    f"Cached {earnings_releases_written} earnings release filings"
                    if earnings_releases_written
                    else "Checked earnings releases"
                ),
            )

        if policy.can_refresh_insiders_only():
            session.commit()
            reporter.step("sec", "Checking SEC for new Form 4/5 and Form 144 filings...")
            submissions = self.client.get_submissions(local_company.cik)
            filing_index = self.client.build_filing_index(submissions)
            insider_trades_written = self.refresh_insiders(
                session=session,
                company=local_company,
                filing_index=filing_index,
                checked_at=checked_at,
                reporter=reporter,
                force=policy.force,
            )
            form144_filings_written = self.refresh_form144(
                session=session,
                company=local_company,
                filing_index=filing_index,
                checked_at=checked_at,
                reporter=reporter,
                force=policy.force,
            )
            _refresh_company_brief_readiness_caches(session, local_company.id, checked_at, reporter, force=policy.force)
            _refresh_company_dashboard_caches(session, local_company, checked_at, reporter, force=policy.force)
            session.commit()
            reporter.complete("Refresh and compute complete.")
            return IngestionResult(
                identifier=identifier,
                company_id=local_company.id,
                cik=local_company.cik,
                ticker=local_company.ticker,
                status="fetched",
                statements_written=0,
                insider_trades_written=insider_trades_written,
                form144_filings_written=form144_filings_written,
                institutional_holdings_written=0,
                price_points_written=0,
                fetched_from_sec=True,
                last_checked=checked_at,
                detail=(
                    (
                        f"Cached {insider_trades_written} insider trades and {form144_filings_written} Form 144 filings"
                        if insider_trades_written or form144_filings_written
                        else "Checked Form 4/5 and Form 144 filings; no new insider activity records"
                    )
                ),
            )

        if policy.can_refresh_institutional_only():
            session.commit()
            institutional_holdings_written = self.refresh_institutional(
                session=session,
                company=local_company,
                checked_at=checked_at,
                reporter=reporter,
                force=policy.force,
            )
            _refresh_company_brief_readiness_caches(session, local_company.id, checked_at, reporter, force=policy.force)
            _refresh_company_dashboard_caches(session, local_company, checked_at, reporter, force=policy.force)
            session.commit()
            reporter.complete("Refresh and compute complete.")
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

        if policy.can_refresh_prices_only():
            session.commit()
            price_points_written = 0
            try:
                price_points_written = self.refresh_prices(
                    session=session,
                    company=local_company,
                    checked_at=checked_at,
                    reporter=reporter,
                    refresh_profile=True,
                    strict_message="Strict official mode enabled; Yahoo market data disabled.",
                )
            except Exception as exc:
                logger.exception("Market data refresh failed for %s", local_company.ticker)
                reporter.step("market", f"Market data refresh failed: {exc}")
                session.rollback()
            _refresh_company_brief_readiness_caches(
                session,
                local_company.id,
                checked_at,
                reporter,
                force=policy.force,
                include_capital_structure=True,
            )
            _refresh_company_dashboard_caches(
                session,
                local_company,
                checked_at,
                reporter,
                force=policy.force,
                include_derived_metrics=True,
                include_oil_scenario_overlay=True,
                include_earnings_models=True,
            )
            session.commit()
            reporter.complete("Refresh and compute complete.")
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

        if policy.can_refresh_filings_only():
            session.commit()
            reporter.step("sec", "Checking SEC for new 8-K filing events...")
            submissions = self.client.get_submissions(local_company.cik)
            filing_index = self.client.build_filing_index(submissions)
            filing_events_written = self.refresh_events(
                session=session,
                company=local_company,
                filing_index=filing_index,
                checked_at=checked_at,
                reporter=reporter,
            )
            _refresh_company_brief_readiness_caches(session, local_company.id, checked_at, reporter, force=policy.force)
            _refresh_company_dashboard_caches(session, local_company, checked_at, reporter, force=policy.force)
            session.commit()
            reporter.complete("Refresh and compute complete.")
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
                price_points_written=0,
                fetched_from_sec=True,
                last_checked=checked_at,
                detail=(
                    f"Cached {filing_events_written} filing event rows"
                    if filing_events_written
                    else "Checked 8-K filing events; no new entries"
                ),
            )

        if policy.can_refresh_capital_markets_only():
            session.commit()
            reporter.step("sec", "Checking SEC for new capital markets filings...")
            submissions = self.client.get_submissions(local_company.cik)
            filing_index = self.client.build_filing_index(submissions)
            capital_markets_written = self.refresh_capital_markets(
                session=session,
                company=local_company,
                filing_index=filing_index,
                checked_at=checked_at,
                reporter=reporter,
            )
            _refresh_company_brief_readiness_caches(session, local_company.id, checked_at, reporter, force=policy.force)
            _refresh_company_dashboard_caches(session, local_company, checked_at, reporter, force=policy.force)
            session.commit()
            reporter.complete("Refresh and compute complete.")
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
                price_points_written=0,
                fetched_from_sec=True,
                last_checked=checked_at,
                detail=(
                    f"Cached {capital_markets_written} capital markets rows"
                    if capital_markets_written
                    else "Checked capital markets filings; no new entries"
                ),
            )

        if policy.can_refresh_comment_letters_only():
            session.commit()
            reporter.step("sec", "Checking SEC for new correspondence filings...")
            submissions = self.client.get_submissions(local_company.cik)
            filing_index = self.client.build_filing_index(submissions)
            comment_letters_written = self.refresh_comment_letters(
                session=session,
                company=local_company,
                submissions=submissions,
                filing_index=filing_index,
                checked_at=checked_at,
                reporter=reporter,
                force=policy.force,
            )
            _refresh_company_brief_readiness_caches(session, local_company.id, checked_at, reporter, force=policy.force)
            _refresh_company_dashboard_caches(session, local_company, checked_at, reporter, force=policy.force)
            session.commit()
            reporter.complete("Refresh and compute complete.")
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
                price_points_written=0,
                fetched_from_sec=True,
                last_checked=checked_at,
                detail=(
                    f"Cached {comment_letters_written} SEC correspondence filings"
                    if comment_letters_written
                    else "Checked SEC correspondence filings; no new entries"
                ),
            )

        return None

    def _refresh_from_sec(
        self,
        identifier: str,
        checked_at: datetime,
        reporter: JobReporter,
        policy: RefreshPolicy,
    ) -> IngestionResult:
        reporter.step("sec", "Checking SEC for new filings...")
        bootstrap = self._load_refresh_bootstrap_inputs(identifier, reporter)
        company_identity = bootstrap.company_identity
        submissions = bootstrap.submissions
        filing_index = bootstrap.filing_index
        companyfacts = bootstrap.companyfacts
        financials_fingerprint = bootstrap.financials_fingerprint
        market_profile = bootstrap.market_profile

        enriched_identity = CompanyIdentity(
            cik=company_identity.cik,
            ticker=((submissions.get("tickers") or [company_identity.ticker])[0]),
            name=str(submissions.get("name") or company_identity.name),
            exchange=((submissions.get("exchanges") or [company_identity.exchange])[0]),
            sector=submissions.get("sicDescription") or company_identity.sector,
            market_sector=market_profile.sector,
            market_industry=market_profile.industry,
            sic=str(submissions.get("sic") or company_identity.sic or "").strip() or None,
        )

        get_engine()
        with SessionLocal() as session:
            company = _upsert_company(session, enriched_identity)
            price_prefetch_executor: ThreadPoolExecutor | None = None
            price_prefetch_future: Future[PriceHistoryPrefetchResult] | None = None
            prefetched_price_history: PriceHistoryPrefetchResult | None = None
            if (
                not settings.strict_official_mode
                and (policy.force or not policy.prices_fresh)
                and getattr(settings, "refresh_aux_io_max_workers", 1) > 1
            ):
                try:
                    latest_trade_date = get_company_latest_trade_date(session, company.id)
                except AttributeError:
                    latest_trade_date = None
                incremental_start_date = None
                if latest_trade_date is not None:
                    incremental_start_date = latest_trade_date - timedelta(days=settings.market_history_overlap_days)
                existing_state = get_dataset_state(session, company.id, "prices")
                existing_payload_hash = existing_state.payload_version_hash if existing_state is not None else None
                price_prefetch_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="refresh-price")
                price_prefetch_future = price_prefetch_executor.submit(
                    self._prefetch_price_history,
                    ticker=company.ticker,
                    incremental_start_date=incremental_start_date,
                    existing_payload_hash=existing_payload_hash,
                )

            statements_written = 0
            financials_state = get_dataset_state(session, company.id, "financials")
            filing_risk_signals_state = get_dataset_state(session, company.id, FILING_RISK_SIGNALS_DATASET)
            can_reuse_financials = (
                not policy.force
                and financials_state is not None
                and financials_state.payload_version_hash == financials_fingerprint
                and filing_risk_signals_state is not None
                and filing_risk_signals_state.payload_version_hash == financials_fingerprint
            )
            if can_reuse_financials:
                reporter.step("normalize", "SEC financial inputs unchanged; reusing cached normalized statements.")
                _touch_company_statements(
                    session,
                    company.id,
                    checked_at,
                    payload_version_hash=financials_fingerprint,
                    invalidate_hot_cache=False,
                )
                mark_dataset_checked(
                    session,
                    company.id,
                    FILING_RISK_SIGNALS_DATASET,
                    checked_at=checked_at,
                    success=True,
                    payload_version_hash=financials_fingerprint,
                )
            else:
                reporter.step("filing", "Parsing filing reports...")
                parsed_filing_insights = self.filing_parser.parse_financial_insights(
                    cik=company_identity.cik,
                    filing_index=filing_index,
                )
                statements_written = self.refresh_statements(
                    session=session,
                    company=company,
                    filing_index=filing_index,
                    companyfacts=companyfacts,
                    parsed_filing_insights=parsed_filing_insights,
                    checked_at=checked_at,
                    reporter=reporter,
                    payload_version_hash=financials_fingerprint,
                )
            session.commit()

            insider_outcome = DatasetRefreshOutcome()
            form144_outcome = DatasetRefreshOutcome()
            if policy.refresh_insider_data and (policy.force or not policy.effective_insider_fresh):
                insider_outcome = self._run_dataset_job(
                    session,
                    company,
                    reporter,
                    stage="insider",
                    label="Insider",
                    job=lambda: self.refresh_insiders(
                        session=session,
                        company=company,
                        filing_index=filing_index,
                        checked_at=checked_at,
                        reporter=reporter,
                        force=policy.force,
                    ),
                )
                form144_outcome = self._run_dataset_job(
                    session,
                    company,
                    reporter,
                    stage="form144",
                    label="Form 144",
                    job=lambda: self.refresh_form144(
                        session=session,
                        company=company,
                        filing_index=filing_index,
                        checked_at=checked_at,
                        reporter=reporter,
                        force=policy.force,
                    ),
                )

            institutional_outcome = DatasetRefreshOutcome()
            if policy.refresh_institutional_data and (policy.force or not policy.institutional_fresh):
                institutional_outcome = self._run_dataset_job(
                    session,
                    company,
                    reporter,
                    stage="13f",
                    label="Institutional holdings",
                    job=lambda: self.refresh_institutional(
                        session=session,
                        company=company,
                        checked_at=checked_at,
                        reporter=reporter,
                        force=policy.force,
                    ),
                )

            beneficial_outcome = DatasetRefreshOutcome()
            if policy.refresh_beneficial_ownership_data and (policy.force or not policy.beneficial_fresh):
                beneficial_outcome = self._run_dataset_job(
                    session,
                    company,
                    reporter,
                    stage="beneficial",
                    label="Beneficial ownership",
                    job=lambda: self.refresh_beneficial_ownership(
                        session=session,
                        company=company,
                        filing_index=filing_index,
                        checked_at=checked_at,
                        reporter=reporter,
                    ),
                )

            earnings_outcome = DatasetRefreshOutcome()
            if policy.force or not policy.earnings_fresh:
                earnings_outcome = self._run_dataset_job(
                    session,
                    company,
                    reporter,
                    stage="earnings",
                    label="Earnings",
                    job=lambda: self.refresh_earnings(
                        session=session,
                        company=company,
                        filing_index=filing_index,
                        checked_at=checked_at,
                        reporter=reporter,
                        force=policy.force,
                    ),
                )

            filing_events_outcome = self._run_dataset_job(
                session,
                company,
                reporter,
                stage="events",
                label="Filing events",
                job=lambda: self.refresh_events(
                    session=session,
                    company=company,
                    filing_index=filing_index,
                    checked_at=checked_at,
                    reporter=reporter,
                ),
            )

            capital_markets_outcome = self._run_dataset_job(
                session,
                company,
                reporter,
                stage="capital",
                label="Capital markets",
                job=lambda: self.refresh_capital_markets(
                    session=session,
                    company=company,
                    filing_index=filing_index,
                    checked_at=checked_at,
                    reporter=reporter,
                ),
            )

            comment_letters_outcome = self._run_dataset_job(
                session,
                company,
                reporter,
                stage="corresp",
                label="SEC correspondence",
                job=lambda: self.refresh_comment_letters(
                    session=session,
                    company=company,
                    submissions=submissions,
                    filing_index=filing_index,
                    checked_at=checked_at,
                    reporter=reporter,
                    force=policy.force,
                ),
            )

            price_outcome = DatasetRefreshOutcome()
            if policy.force or not policy.prices_fresh:
                if price_prefetch_future is not None:
                    prefetched_price_history = price_prefetch_future.result()
                price_outcome = self._run_dataset_job(
                    session,
                    company,
                    reporter,
                    stage="market",
                    label="Market data",
                    job=lambda: self.refresh_prices(
                        session=session,
                        company=company,
                        checked_at=checked_at,
                        reporter=reporter,
                        prefetched_price_history=prefetched_price_history,
                    ),
                )

            _refresh_company_brief_readiness_caches(
                session,
                company.id,
                checked_at,
                reporter,
                force=policy.force,
                include_capital_structure=True,
            )
            _refresh_company_dashboard_caches(
                session,
                company,
                checked_at,
                reporter,
                force=policy.force,
                include_derived_metrics=True,
                include_oil_scenario_overlay=True,
                include_earnings_models=True,
            )

            session.commit()
            reporter.complete("Refresh and compute complete.")

            detail_parts: list[str] = [f"Normalized {statements_written} filings"]
            if policy.refresh_insider_data and (policy.force or not policy.effective_insider_fresh):
                detail_parts.append(
                    insider_outcome.error
                    or (
                        f"Cached {insider_outcome.written} insider trades"
                        if insider_outcome.written
                        else "Checked Form 4/5 filings"
                    )
                )
                detail_parts.append(
                    form144_outcome.error
                    or (
                        f"Cached {form144_outcome.written} Form 144 planned sale filing rows"
                        if form144_outcome.written
                        else "Checked Form 144 filings"
                    )
                )
            if policy.refresh_institutional_data and (policy.force or not policy.institutional_fresh):
                detail_parts.append(
                    institutional_outcome.error
                    or (
                        f"Cached {institutional_outcome.written} institutional holdings snapshots"
                        if institutional_outcome.written
                        else "Checked 13F filings"
                    )
                )
            if policy.refresh_beneficial_ownership_data and (policy.force or not policy.beneficial_fresh):
                detail_parts.append(
                    beneficial_outcome.error
                    or (
                        f"Cached {beneficial_outcome.written} beneficial ownership filings"
                        if beneficial_outcome.written
                        else "Checked beneficial ownership filings"
                    )
                )
            if policy.force or not policy.earnings_fresh:
                detail_parts.append(
                    earnings_outcome.error
                    or (
                        f"Cached {earnings_outcome.written} earnings release rows"
                        if earnings_outcome.written
                        else "Checked earnings releases"
                    )
                )
            detail_parts.append(
                filing_events_outcome.error
                or (
                    f"Cached {filing_events_outcome.written} filing event rows"
                    if filing_events_outcome.written
                    else "Checked 8-K filing events"
                )
            )
            detail_parts.append(
                capital_markets_outcome.error
                or (
                    f"Cached {capital_markets_outcome.written} capital markets rows"
                    if capital_markets_outcome.written
                    else "Checked capital markets filings"
                )
            )
            detail_parts.append(
                comment_letters_outcome.error
                or (
                    f"Cached {comment_letters_outcome.written} SEC correspondence filings"
                    if comment_letters_outcome.written
                    else "Checked SEC correspondence filings"
                )
            )
            if policy.force or not policy.prices_fresh:
                detail_parts.append(
                    price_outcome.error or f"Cached {price_outcome.written} daily price bars"
                )

            if price_prefetch_executor is not None:
                price_prefetch_executor.shutdown(wait=True)

            return IngestionResult(
                identifier=identifier,
                company_id=company.id,
                cik=company.cik,
                ticker=company.ticker,
                status="fetched",
                statements_written=statements_written,
                insider_trades_written=insider_outcome.written,
                form144_filings_written=form144_outcome.written,
                institutional_holdings_written=institutional_outcome.written,
                beneficial_ownership_written=beneficial_outcome.written,
                earnings_releases_written=earnings_outcome.written,
                price_points_written=price_outcome.written,
                fetched_from_sec=True,
                last_checked=checked_at,
                detail="; ".join(detail_parts),
            )
        

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
            policy = self._build_refresh_policy(
                session,
                local_company,
                checked_at,
                force,
                refresh_insider_data=refresh_insider_data,
                refresh_institutional_data=refresh_institutional_data,
                refresh_beneficial_ownership_data=refresh_beneficial_ownership_data,
            )
            cached_result = self._refresh_cached_company(
                session=session,
                identifier=identifier,
                checked_at=checked_at,
                reporter=active_reporter,
                policy=policy,
            )
            if cached_result is not None:
                return cached_result

        return self._refresh_from_sec(
            identifier=identifier,
            checked_at=checked_at,
            reporter=active_reporter,
            policy=policy,
        )


def run_refresh_job(
    identifier: str,
    force: bool = False,
    job_id: str | None = None,
    *,
    claim_token: str | None = None,
    service: EdgarIngestionService | None = None,
) -> dict[str, Any]:
    active_service = service or EdgarIngestionService()
    owns_service = service is None
    reporter = JobReporter(job_id, claim_token=claim_token)
    emit_structured_log(
        logger,
        "refresh.job.start",
        identifier=identifier,
        force=force,
        job_id=job_id,
        trace_id=job_id,
    )
    try:
        result = active_service.refresh_company(identifier=identifier, force=force, reporter=reporter)
        get_engine()
        with SessionLocal() as session:
            company = _find_local_company(session, identifier)
            if company is not None and result.last_checked is not None:
                release_refresh_lock(
                    session,
                    company_id=company.id,
                    dataset="company_refresh",
                    checked_at=result.last_checked,
                )
                session.commit()
        payload = asdict(result)
        payload["last_checked"] = result.last_checked.isoformat() if result.last_checked else None
        payload["job_id"] = job_id
        emit_structured_log(
            logger,
            "refresh.job.complete",
            identifier=identifier,
            job_id=job_id,
            trace_id=job_id,
            ticker=result.ticker,
            company_id=result.company_id,
            status=result.status,
            statements_written=result.statements_written,
            insider_trades_written=result.insider_trades_written,
            form144_filings_written=result.form144_filings_written,
            institutional_holdings_written=result.institutional_holdings_written,
            beneficial_ownership_written=result.beneficial_ownership_written,
            earnings_releases_written=result.earnings_releases_written,
            price_points_written=result.price_points_written,
            fetched_from_sec=result.fetched_from_sec,
            last_checked=result.last_checked,
        )
        return payload
    except Exception as exc:
        get_engine()
        with SessionLocal() as session:
            company = _find_local_company(session, identifier)
            if company is not None:
                release_refresh_lock_failed(
                    session,
                    company_id=company.id,
                    dataset="company_refresh",
                    checked_at=datetime.now(timezone.utc),
                    error=str(exc),
                )
                session.commit()
        emit_structured_log(
            logger,
            "refresh.job.failed",
            level=logging.ERROR,
            identifier=identifier,
            job_id=job_id,
            trace_id=job_id,
            error=str(exc),
        )
        reporter.fail(str(exc))
        raise
    finally:
        if owns_service:
            active_service.close()


def _dataset_payload_hash(session: Session, company_id: int, dataset: str) -> str | None:
    state = get_dataset_state(session, company_id, dataset)
    if state is None:
        return None
    return state.payload_version_hash


def _filing_metadata_fingerprint_payload(metadata: FilingMetadata) -> dict[str, Any]:
    return {
        "accession_number": metadata.accession_number,
        "form": metadata.form,
        "filing_date": metadata.filing_date,
        "report_date": metadata.report_date,
        "acceptance_datetime": metadata.acceptance_datetime,
        "primary_document": metadata.primary_document,
        "primary_doc_description": metadata.primary_doc_description,
        "items": metadata.items,
    }


def _build_filing_metadata_fingerprint(version: str, filings: list[FilingMetadata]) -> str:
    return build_payload_version_hash(
        version=version,
        payload=[_filing_metadata_fingerprint_payload(metadata) for metadata in filings],
    )


def _mark_dataset_recompute_skipped(
    session: Session,
    *,
    company_id: int,
    dataset: str,
    checked_at: datetime,
    payload_version_hash: str,
) -> None:
    mark_dataset_checked(
        session,
        company_id,
        dataset,
        checked_at=checked_at,
        success=True,
        payload_version_hash=payload_version_hash,
        invalidate_hot_cache=False,
    )


def _build_derived_metrics_inputs_fingerprint(session: Session, company_id: int) -> str | None:
    financials_hash = _dataset_payload_hash(session, company_id, "financials")
    if financials_hash is None:
        return None

    payload: dict[str, Any] = {
        "formula_version": "sec_metrics_mart_v1",
        "financials": financials_hash,
        "strict_official_mode": settings.strict_official_mode,
    }
    if not settings.strict_official_mode:
        prices_hash = _dataset_payload_hash(session, company_id, "prices")
        if prices_hash is None:
            return None
        payload["prices"] = prices_hash

    return build_payload_version_hash(version=DERIVED_METRICS_INPUT_FINGERPRINT_VERSION, payload=payload)


def _build_capital_structure_inputs_fingerprint(session: Session, company_id: int) -> str | None:
    financials_hash = _dataset_payload_hash(session, company_id, "financials")
    if financials_hash is None:
        return None
    return build_payload_version_hash(
        version=CAPITAL_STRUCTURE_INPUT_FINGERPRINT_VERSION,
        payload={
            "formula_version": "capital_structure_v1",
            "financials": financials_hash,
        },
    )


def _build_earnings_models_inputs_fingerprint(session: Session, company_id: int) -> str | None:
    financials_hash = _dataset_payload_hash(session, company_id, "financials")
    earnings_hash = _dataset_payload_hash(session, company_id, "earnings")
    if financials_hash is None or earnings_hash is None:
        return None
    return build_payload_version_hash(
        version=EARNINGS_MODELS_INPUT_FINGERPRINT_VERSION,
        payload={
            "model_version": "sec_earnings_intel_v1",
            "financials": financials_hash,
            "earnings": earnings_hash,
        },
    )


def _build_company_research_brief_inputs_fingerprint(session: Session, company_id: int) -> str | None:
    company = session.get(Company, company_id)
    if company is None:
        return None

    dependency_hashes: dict[str, Any] = {
        "financials": _dataset_payload_hash(session, company_id, "financials"),
        "filings": _dataset_payload_hash(session, company_id, "filings"),
        "capital_markets": _dataset_payload_hash(session, company_id, "capital_markets"),
        "insiders": _dataset_payload_hash(session, company_id, "insiders"),
        "form144": _dataset_payload_hash(session, company_id, "form144"),
        "institutional": _dataset_payload_hash(session, company_id, "institutional"),
        "beneficial_ownership": _dataset_payload_hash(session, company_id, "beneficial_ownership"),
        "earnings": _dataset_payload_hash(session, company_id, "earnings"),
        "comment_letters": _dataset_payload_hash(session, company_id, "comment_letters"),
        "capital_structure": _dataset_payload_hash(session, company_id, "capital_structure"),
    }
    if not settings.strict_official_mode:
        dependency_hashes["prices"] = _dataset_payload_hash(session, company_id, "prices")

    if any(value is None for value in dependency_hashes.values()):
        return None

    return build_payload_version_hash(
        version=COMPANY_RESEARCH_BRIEF_INPUT_FINGERPRINT_VERSION,
        payload={
            "schema_version": "company_research_brief_v1",
            "company": {
                "ticker": company.ticker,
                "cik": company.cik,
                "name": company.name,
                "exchange": getattr(company, "exchange", None),
                "sector": company.sector,
                "market_sector": company.market_sector,
                "market_industry": company.market_industry,
                "sic": getattr(company, "sic", None),
            },
            "dependencies": dependency_hashes,
        },
    )


def _build_company_charts_dashboard_inputs_fingerprint(session: Session, company_id: int) -> str | None:
    company = session.get(Company, company_id)
    if company is None:
        return None

    dependency_hashes: dict[str, Any] = {
        "financials": _dataset_payload_hash(session, company_id, "financials"),
        "derived_metrics": _dataset_payload_hash(session, company_id, "derived_metrics"),
        "capital_structure": _dataset_payload_hash(session, company_id, "capital_structure"),
        "earnings_models": _dataset_payload_hash(session, company_id, "earnings_models"),
        "company_research_brief": _dataset_payload_hash(session, company_id, "company_research_brief"),
    }
    if any(value is None for value in dependency_hashes.values()):
        return None

    return build_payload_version_hash(
        version=CHARTS_DASHBOARD_INPUT_FINGERPRINT_VERSION,
        payload={
            "schema_version": "company_charts_dashboard_v9",
            "company": {
                "ticker": company.ticker,
                "cik": company.cik,
                "name": company.name,
                "sector": company.sector,
                "market_sector": company.market_sector,
                "market_industry": company.market_industry,
            },
            "dependencies": dependency_hashes,
        },
    )


def _refresh_company_brief_readiness_caches(
    session: Session,
    company_id: int,
    checked_at: datetime,
    reporter: JobReporter,
    *,
    force: bool = False,
    include_capital_structure: bool = False,
) -> None:
    # Warm the brief as soon as its actual dependencies are refreshed so first
    # company visits spend less time in snapshot-missing bootstrap states.
    if include_capital_structure:
        _refresh_capital_structure_cache(session, company_id, checked_at, reporter, force=force)
    _refresh_company_research_brief_cache(session, company_id, checked_at, reporter, force=force)


def _refresh_company_dashboard_caches(
    session: Session,
    company: Company,
    checked_at: datetime,
    reporter: JobReporter,
    *,
    force: bool = False,
    include_derived_metrics: bool = False,
    include_oil_scenario_overlay: bool = False,
    include_earnings_models: bool = False,
) -> None:
    if include_derived_metrics:
        _refresh_derived_metrics_cache(session, company.id, checked_at, reporter, force=force)
    if include_oil_scenario_overlay:
        _refresh_oil_scenario_overlay_cache(session, company, checked_at, reporter)
    if include_earnings_models:
        _refresh_earnings_model_cache(session, company.id, checked_at, reporter, force=force)
    _refresh_company_charts_dashboard_cache(session, company.id, checked_at, reporter, force=force)


def _refresh_derived_metrics_cache(
    session: Session,
    company_id: int,
    checked_at: datetime,
    reporter: JobReporter,
    *,
    force: bool = False,
) -> int:
    payload_version_hash = _build_derived_metrics_inputs_fingerprint(session, company_id)
    if (
        not force
        and payload_version_hash is not None
        and _dataset_payload_hash(session, company_id, "derived_metrics") == payload_version_hash
    ):
        reporter.step("metrics", "Skipping derived metrics mart recompute; dependent inputs are unchanged.")
        _mark_dataset_recompute_skipped(
            session,
            company_id=company_id,
            dataset="derived_metrics",
            checked_at=checked_at,
            payload_version_hash=payload_version_hash,
        )
        return 0

    reporter.step("metrics", "Recomputing derived metrics mart...")
    rows_written = recompute_and_persist_company_derived_metrics(
        session,
        company_id,
        checked_at=checked_at,
        payload_version_hash=payload_version_hash,
    )
    reporter.step("metrics", f"Updated {rows_written} derived metric rows")
    return rows_written


def _refresh_capital_structure_cache(
    session: Session,
    company_id: int,
    checked_at: datetime,
    reporter: JobReporter,
    *,
    force: bool = False,
) -> int:
    payload_version_hash = _build_capital_structure_inputs_fingerprint(session, company_id)
    if (
        not force
        and payload_version_hash is not None
        and _dataset_payload_hash(session, company_id, "capital_structure") == payload_version_hash
    ):
        reporter.step("capital_structure", "Skipping capital structure intelligence recompute; dependent inputs are unchanged.")
        _mark_dataset_recompute_skipped(
            session,
            company_id=company_id,
            dataset="capital_structure",
            checked_at=checked_at,
            payload_version_hash=payload_version_hash,
        )
        return 0

    reporter.step("capital_structure", "Recomputing capital structure intelligence cache...")
    rows_written = recompute_and_persist_company_capital_structure(
        session,
        company_id,
        checked_at=checked_at,
        payload_version_hash=payload_version_hash,
    )
    reporter.step("capital_structure", f"Updated {rows_written} capital structure rows")
    return rows_written


def _refresh_oil_scenario_overlay_cache(
    session: Session,
    company: Company,
    checked_at: datetime,
    reporter: JobReporter,
) -> int:
    reporter.step("oil_scenario_overlay", "Refreshing oil scenario overlay cache...")
    rows_written = refresh_company_oil_scenario_overlay(
        session,
        company,
        checked_at=checked_at,
        job_id=getattr(reporter, "job_id", None),
    )
    reporter.step("oil_scenario_overlay", f"Updated {rows_written} oil scenario overlay rows")
    return rows_written


def _refresh_earnings_model_cache(
    session: Session,
    company_id: int,
    checked_at: datetime,
    reporter: JobReporter,
    *,
    force: bool = False,
) -> int:
    payload_version_hash = _build_earnings_models_inputs_fingerprint(session, company_id)
    if (
        not force
        and payload_version_hash is not None
        and _dataset_payload_hash(session, company_id, "earnings_models") == payload_version_hash
    ):
        reporter.step("earnings_models", "Skipping SEC-heavy earnings model recompute; dependent inputs are unchanged.")
        _mark_dataset_recompute_skipped(
            session,
            company_id=company_id,
            dataset="earnings_models",
            checked_at=checked_at,
            payload_version_hash=payload_version_hash,
        )
        return 0

    reporter.step("earnings_models", "Recomputing SEC-heavy earnings model cache...")
    rows_written = recompute_and_persist_company_earnings_model_points(
        session,
        company_id,
        checked_at=checked_at,
        payload_version_hash=payload_version_hash,
    )
    reporter.step("earnings_models", f"Updated {rows_written} earnings model rows")
    return rows_written


def _refresh_company_research_brief_cache(
    session: Session,
    company_id: int,
    checked_at: datetime,
    reporter: JobReporter,
    *,
    force: bool = False,
) -> int:
    if not hasattr(session, "get"):
        return 0

    from app.services.company_research_brief import recompute_and_persist_company_research_brief

    payload_version_hash = _build_company_research_brief_inputs_fingerprint(session, company_id)
    if (
        not force
        and payload_version_hash is not None
        and _dataset_payload_hash(session, company_id, "company_research_brief") == payload_version_hash
    ):
        reporter.step("company_research_brief", "Skipping company research brief recompute; dependent inputs are unchanged.")
        _mark_dataset_recompute_skipped(
            session,
            company_id=company_id,
            dataset="company_research_brief",
            checked_at=checked_at,
            payload_version_hash=payload_version_hash,
        )
        return 0

    reporter.step("company_research_brief", "Recomputing company research brief cache...")
    payload = recompute_and_persist_company_research_brief(
        session,
        company_id,
        checked_at=checked_at,
        payload_version_hash=payload_version_hash,
    )
    reporter.step("company_research_brief", f"Updated {1 if payload is not None else 0} company research brief rows")
    return 1 if payload is not None else 0


def _refresh_company_charts_dashboard_cache(
    session: Session,
    company_id: int,
    checked_at: datetime,
    reporter: JobReporter,
    *,
    force: bool = False,
) -> int:
    if not hasattr(session, "get"):
        return 0

    from app.services.company_charts_dashboard import recompute_and_persist_company_charts_dashboard

    payload_version_hash = _build_company_charts_dashboard_inputs_fingerprint(session, company_id)
    if (
        not force
        and payload_version_hash is not None
        and _dataset_payload_hash(session, company_id, "charts_dashboard") == payload_version_hash
    ):
        reporter.step("charts_dashboard", "Skipping charts dashboard recompute; dependent inputs are unchanged.")
        _mark_dataset_recompute_skipped(
            session,
            company_id=company_id,
            dataset="charts_dashboard",
            checked_at=checked_at,
            payload_version_hash=payload_version_hash,
        )
        return 0

    reporter.step("charts_dashboard", "Recomputing charts dashboard cache...")
    payload = recompute_and_persist_company_charts_dashboard(
        session,
        company_id,
        checked_at=checked_at,
        payload_version_hash=payload_version_hash,
    )
    reporter.step("charts_dashboard", f"Updated {1 if payload is not None else 0} charts dashboard rows")
    return 1 if payload is not None else 0


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


def _existing_form144_accessions(session: Session, company_id: int) -> set[str]:
    statement = select(Form144Filing.accession_number).where(Form144Filing.company_id == company_id).distinct()
    return {value for value in session.execute(statement).scalars() if value}


def _existing_earnings_release_accessions(session: Session, company_id: int) -> set[str]:
    statement = select(EarningsRelease.accession_number).where(EarningsRelease.company_id == company_id).distinct()
    return {value for value in session.execute(statement).scalars() if value}


def _existing_comment_letter_accessions(session: Session, company_id: int) -> set[str]:
    statement = select(CommentLetter.accession_number).where(CommentLetter.company_id == company_id).distinct()
    return {value for value in session.execute(statement).scalars() if value}


def _latest_insider_trade_last_checked(session: Session, company: Company) -> datetime | None:
    state_last_checked, state_cache = cache_state_for_dataset(session, company.id, "insiders")
    if state_cache != "missing":
        return state_last_checked

    statement = select(func.max(InsiderTrade.last_checked)).where(InsiderTrade.company_id == company.id)
    last_checked = _normalize_datetime_value(session.execute(statement).scalar_one_or_none())
    if last_checked is not None:
        mark_dataset_checked(session, company.id, "insiders", checked_at=last_checked, success=True)
    return last_checked


def _latest_form144_last_checked(session: Session, company: Company) -> datetime | None:
    state_last_checked, state_cache = cache_state_for_dataset(session, company.id, "form144")
    if state_cache != "missing":
        return state_last_checked

    statement = select(func.max(Form144Filing.last_checked)).where(Form144Filing.company_id == company.id)
    last_checked = _normalize_datetime_value(session.execute(statement).scalar_one_or_none())
    if last_checked is not None:
        mark_dataset_checked(session, company.id, "form144", checked_at=last_checked, success=True)
    return last_checked


def _latest_earnings_last_checked(session: Session, company: Company) -> datetime | None:
    state_last_checked, state_cache = cache_state_for_dataset(session, company.id, "earnings")
    if state_cache != "missing":
        return state_last_checked

    statement = select(func.max(EarningsRelease.last_checked)).where(EarningsRelease.company_id == company.id)
    last_checked = _normalize_datetime_value(session.execute(statement).scalar_one_or_none())
    if last_checked is not None:
        mark_dataset_checked(session, company.id, "earnings", checked_at=last_checked, success=True)
    return last_checked


def _latest_beneficial_ownership_last_checked(session: Session, company: Company) -> datetime | None:
    state_last_checked, state_cache = cache_state_for_dataset(session, company.id, "beneficial_ownership")
    if state_cache != "missing":
        return state_last_checked

    statement = select(func.max(BeneficialOwnershipReport.last_checked)).where(
        BeneficialOwnershipReport.company_id == company.id
    )
    last_checked = _normalize_datetime_value(session.execute(statement).scalar_one_or_none())
    if last_checked is not None:
        mark_dataset_checked(session, company.id, "beneficial_ownership", checked_at=last_checked, success=True)
    return last_checked


def _latest_comment_letter_last_checked(session: Session, company: Company) -> datetime | None:
    state_last_checked, state_cache = cache_state_for_dataset(session, company.id, "comment_letters")
    if state_cache != "missing":
        return state_last_checked

    statement = select(func.max(CommentLetter.last_checked)).where(CommentLetter.company_id == company.id)
    last_checked = _normalize_datetime_value(session.execute(statement).scalar_one_or_none())
    if last_checked is not None:
        mark_dataset_checked(session, company.id, "comment_letters", checked_at=last_checked, success=True)
    return last_checked


def _latest_filing_event_last_checked(session: Session, company: Company) -> datetime | None:
    state_last_checked, state_cache = cache_state_for_dataset(session, company.id, "filings")
    if state_cache != "missing":
        return state_last_checked

    statement = select(func.max(FilingEvent.last_checked)).where(FilingEvent.company_id == company.id)
    last_checked = _normalize_datetime_value(session.execute(statement).scalar_one_or_none())
    if last_checked is not None:
        mark_dataset_checked(session, company.id, "filings", checked_at=last_checked, success=True)
    return last_checked


def _latest_capital_markets_last_checked(session: Session, company: Company) -> datetime | None:
    state_last_checked, state_cache = cache_state_for_dataset(session, company.id, "capital_markets")
    if state_cache != "missing":
        return state_last_checked

    statement = select(func.max(CapitalMarketsEvent.last_checked)).where(CapitalMarketsEvent.company_id == company.id)
    last_checked = _normalize_datetime_value(session.execute(statement).scalar_one_or_none())
    if last_checked is not None:
        mark_dataset_checked(session, company.id, "capital_markets", checked_at=last_checked, success=True)
    return last_checked


def _attach_statement_reconciliations(
    normalized_statements: list[NormalizedStatement],
    parsed_insights: list[ParsedFilingInsight],
    checked_at: datetime,
) -> None:
    parser_by_key: dict[tuple[str, date], ParsedFilingInsight] = {}
    for insight in parsed_insights:
        parser_by_key.setdefault((insight.filing_type, insight.period_end), insight)

    for statement in normalized_statements:
        parser_insight = parser_by_key.get((statement.filing_type, statement.period_end))
        statement.reconciliation = _build_statement_reconciliation(statement, parser_insight, checked_at)


def _build_statement_reconciliation(
    statement: NormalizedStatement,
    parser_insight: ParsedFilingInsight | None,
    checked_at: datetime,
) -> dict[str, Any]:
    provenance_sources = ["sec_companyfacts"]
    if statement.filing_type in RECONCILIATION_SUPPORTED_FORMS:
        provenance_sources.append("sec_edgar")

    if statement.filing_type not in RECONCILIATION_SUPPORTED_FORMS:
        return {
            "status": "unsupported_form",
            "as_of": statement.period_end,
            "last_refreshed_at": checked_at,
            "provenance_sources": provenance_sources,
            "confidence_score": None,
            "confidence_penalty": 0.0,
            "confidence_flags": ["filing_parser_unsupported_form"],
            "missing_field_flags": [],
            "matched_accession_number": None,
            "matched_filing_type": None,
            "matched_period_start": None,
            "matched_period_end": None,
            "matched_source": None,
            "disagreement_count": 0,
            "comparisons": [],
        }

    statement_data = statement.data or {}
    selected_facts = statement.selected_facts or {}
    comparisons: list[dict[str, Any]] = []
    confidence_flags: set[str] = set()
    missing_field_flags: set[str] = set()
    disagreement_count = 0
    total_penalty = 0.0

    if parser_insight is None:
        confidence_flags.add("filing_parser_statement_missing")
        missing_field_flags.add("filing_parser_statement_missing")
        for metric_key in RECONCILIATION_METRICS:
            companyfacts_value = statement_data.get(metric_key)
            if companyfacts_value is not None:
                missing_field_flags.add(f"{metric_key}_missing_in_filing_parser")
            comparisons.append(
                {
                    "metric_key": metric_key,
                    "status": "companyfacts_only" if companyfacts_value is not None else "unavailable",
                    "companyfacts_value": companyfacts_value,
                    "filing_parser_value": None,
                    "delta": None,
                    "relative_delta": None,
                    "confidence_penalty": 0.0,
                    "companyfacts_fact": selected_facts.get(metric_key),
                    "filing_parser_fact": None,
                }
            )

        return {
            "status": "parser_missing",
            "as_of": statement.period_end,
            "last_refreshed_at": checked_at,
            "provenance_sources": provenance_sources,
            "confidence_score": 0.65,
            "confidence_penalty": 0.35,
            "confidence_flags": sorted(confidence_flags),
            "missing_field_flags": sorted(missing_field_flags),
            "matched_accession_number": None,
            "matched_filing_type": None,
            "matched_period_start": None,
            "matched_period_end": None,
            "matched_source": None,
            "disagreement_count": 0,
            "comparisons": comparisons,
        }

    parser_data = parser_insight.data or {}
    for metric_key in RECONCILIATION_METRICS:
        companyfacts_value = statement_data.get(metric_key)
        parser_value = parser_data.get(metric_key)
        metric_penalty = 0.0
        delta: int | float | None = None
        relative_delta: float | None = None

        if companyfacts_value is None and parser_value is None:
            status = "unavailable"
            missing_field_flags.add(f"{metric_key}_missing_in_both_sources")
        elif companyfacts_value is None:
            status = "parser_only"
            metric_penalty = 0.12
            confidence_flags.add(f"{metric_key}_missing_in_companyfacts")
            missing_field_flags.add(f"{metric_key}_missing_in_companyfacts")
        elif parser_value is None:
            status = "companyfacts_only"
            metric_penalty = 0.12
            confidence_flags.add(f"{metric_key}_missing_in_filing_parser")
            missing_field_flags.add(f"{metric_key}_missing_in_filing_parser")
        else:
            delta = _metric_delta(companyfacts_value, parser_value)
            relative_delta = _absolute_relative_change(companyfacts_value, parser_value)
            if _reconciliation_values_match(companyfacts_value, parser_value):
                status = "match"
            else:
                status = "disagreement"
                disagreement_count += 1
                metric_penalty = _reconciliation_penalty(relative_delta)
                confidence_flags.add(f"{metric_key}_reconciliation_disagreement")

        total_penalty += metric_penalty
        comparisons.append(
            {
                "metric_key": metric_key,
                "status": status,
                "companyfacts_value": companyfacts_value,
                "filing_parser_value": parser_value,
                "delta": delta,
                "relative_delta": relative_delta,
                "confidence_penalty": round(metric_penalty, 4) if metric_penalty else 0.0,
                "companyfacts_fact": selected_facts.get(metric_key),
                "filing_parser_fact": _parser_fact_metadata(parser_insight, parser_value),
            }
        )

    confidence_penalty = round(min(total_penalty, 1.0), 4)
    confidence_score = round(max(0.0, 1.0 - confidence_penalty), 4)
    status = "matched" if disagreement_count == 0 and not confidence_flags else "disagreement"
    return {
        "status": status,
        "as_of": statement.period_end,
        "last_refreshed_at": checked_at,
        "provenance_sources": provenance_sources,
        "confidence_score": confidence_score,
        "confidence_penalty": confidence_penalty,
        "confidence_flags": sorted(confidence_flags),
        "missing_field_flags": sorted(missing_field_flags),
        "matched_accession_number": parser_insight.accession_number,
        "matched_filing_type": parser_insight.filing_type,
        "matched_period_start": parser_insight.period_start,
        "matched_period_end": parser_insight.period_end,
        "matched_source": parser_insight.source,
        "disagreement_count": disagreement_count,
        "comparisons": comparisons,
    }


def _parser_fact_metadata(
    parser_insight: ParsedFilingInsight,
    value: Any,
) -> dict[str, Any] | None:
    if value is None:
        return None
    return {
        "accession_number": parser_insight.accession_number,
        "form": parser_insight.filing_type,
        "taxonomy": None,
        "tag": None,
        "unit": None,
        "source": parser_insight.source,
        "filed_at": None,
        "period_start": parser_insight.period_start,
        "period_end": parser_insight.period_end,
        "value": value,
    }


def _absolute_relative_change(left_value: Any, right_value: Any) -> float | None:
    if not isinstance(left_value, (int, float)) or not isinstance(right_value, (int, float)):
        return None
    baseline = abs(float(left_value))
    if baseline == 0:
        return 0.0 if float(right_value) == 0 else 1.0
    return round(abs(float(right_value) - float(left_value)) / baseline, 4)


def _reconciliation_values_match(left_value: Any, right_value: Any) -> bool:
    if not isinstance(left_value, (int, float)) or not isinstance(right_value, (int, float)):
        return False
    if left_value == right_value:
        return True
    absolute_delta = abs(float(right_value) - float(left_value))
    if absolute_delta <= 1.0:
        return True
    relative_delta = _absolute_relative_change(left_value, right_value)
    return relative_delta is not None and relative_delta <= 0.02


def _reconciliation_penalty(relative_delta: float | None) -> float:
    if relative_delta is None:
        return 0.08
    if relative_delta >= 0.15:
        return 0.3
    if relative_delta >= 0.07:
        return 0.2
    if relative_delta >= 0.03:
        return 0.12
    return 0.05


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
            "sale_context": trade.sale_context,
            "plan_adoption_date": trade.plan_adoption_date,
            "plan_modification": trade.plan_modification,
            "plan_modification_date": trade.plan_modification_date,
            "plan_signal_confidence": trade.plan_signal_confidence,
            "plan_signal_provenance": trade.plan_signal_provenance,
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
            "sale_context": statement.excluded.sale_context,
            "plan_adoption_date": statement.excluded.plan_adoption_date,
            "plan_modification": statement.excluded.plan_modification,
            "plan_modification_date": statement.excluded.plan_modification_date,
            "plan_signal_confidence": statement.excluded.plan_signal_confidence,
            "plan_signal_provenance": statement.excluded.plan_signal_provenance,
            "source": statement.excluded.source,
            "last_updated": func.now(),
            "last_checked": statement.excluded.last_checked,
        },
    )
    session.execute(statement)
    return len(payload)


def _upsert_form144_filings(
    session: Session,
    company: Company,
    normalized_filings: list[NormalizedForm144Filing],
    checked_at: datetime,
) -> int:
    if not normalized_filings:
        return 0

    payload = [
        {
            "company_id": company.id,
            "accession_number": filing.accession_number,
            "form": filing.form,
            "filing_date": filing.filing_date,
            "report_date": filing.report_date,
            "transaction_index": filing.transaction_index,
            "filer_name": filing.filer_name,
            "relationship_to_issuer": filing.relationship_to_issuer,
            "issuer_name": filing.issuer_name,
            "security_title": filing.security_title,
            "planned_sale_date": filing.planned_sale_date,
            "shares_to_be_sold": filing.shares_to_be_sold,
            "aggregate_market_value": filing.aggregate_market_value,
            "shares_owned_after_sale": filing.shares_owned_after_sale,
            "broker_name": filing.broker_name,
            "source_url": filing.source_url,
            "summary": filing.summary,
            "last_checked": checked_at,
        }
        for filing in normalized_filings
    ]

    statement = insert(Form144Filing).values(payload)
    statement = statement.on_conflict_do_update(
        index_elements=["company_id", "accession_number", "transaction_index"],
        set_={
            "form": statement.excluded.form,
            "filing_date": statement.excluded.filing_date,
            "report_date": statement.excluded.report_date,
            "filer_name": statement.excluded.filer_name,
            "relationship_to_issuer": statement.excluded.relationship_to_issuer,
            "issuer_name": statement.excluded.issuer_name,
            "security_title": statement.excluded.security_title,
            "planned_sale_date": statement.excluded.planned_sale_date,
            "shares_to_be_sold": statement.excluded.shares_to_be_sold,
            "aggregate_market_value": statement.excluded.aggregate_market_value,
            "shares_owned_after_sale": statement.excluded.shares_owned_after_sale,
            "broker_name": statement.excluded.broker_name,
            "source_url": statement.excluded.source_url,
            "summary": statement.excluded.summary,
            "last_updated": func.now(),
            "last_checked": statement.excluded.last_checked,
        },
    )
    session.execute(statement)
    return len(payload)


def _upsert_comment_letters(
    session: Session,
    company: Company,
    comment_letters: list[NormalizedCommentLetter],
    checked_at: datetime,
) -> int:
    if not comment_letters:
        return 0

    payload = [
        {
            "company_id": company.id,
            "accession_number": letter.accession_number,
            "filing_date": letter.filing_date,
            "description": letter.description,
            "sec_url": letter.sec_url,
            "last_checked": checked_at,
        }
        for letter in comment_letters
    ]

    statement = insert(CommentLetter).values(payload)
    statement = statement.on_conflict_do_update(
        index_elements=["company_id", "accession_number"],
        set_={
            "filing_date": statement.excluded.filing_date,
            "description": statement.excluded.description,
            "sec_url": statement.excluded.sec_url,
            "last_updated": func.now(),
            "last_checked": statement.excluded.last_checked,
        },
    )
    session.execute(statement)
    return len(payload)


def _touch_company_insider_trades(
    session: Session,
    company_id: int,
    checked_at: datetime,
    *,
    payload_version_hash: str | None = None,
) -> None:
    session.execute(
        update(InsiderTrade)
        .where(InsiderTrade.company_id == company_id)
        .values(last_checked=checked_at)
    )
    mark_dataset_checked(
        session,
        company_id,
        "insiders",
        checked_at=checked_at,
        success=True,
        payload_version_hash=payload_version_hash,
        invalidate_hot_cache=True,
    )


def _touch_company_form144_filings(
    session: Session,
    company_id: int,
    checked_at: datetime,
    *,
    payload_version_hash: str | None = None,
) -> None:
    session.execute(
        update(Form144Filing)
        .where(Form144Filing.company_id == company_id)
        .values(last_checked=checked_at)
    )
    mark_dataset_checked(
        session,
        company_id,
        "form144",
        checked_at=checked_at,
        success=True,
        payload_version_hash=payload_version_hash,
        invalidate_hot_cache=True,
    )


def _touch_company_earnings_releases(
    session: Session,
    company_id: int,
    checked_at: datetime,
    *,
    payload_version_hash: str | None = None,
) -> None:
    session.execute(
        update(EarningsRelease)
        .where(EarningsRelease.company_id == company_id)
        .values(last_checked=checked_at)
    )
    mark_dataset_checked(
        session,
        company_id,
        "earnings",
        checked_at=checked_at,
        success=True,
        payload_version_hash=payload_version_hash,
        invalidate_hot_cache=True,
    )


def _touch_company_comment_letters(
    session: Session,
    company_id: int,
    checked_at: datetime,
    *,
    payload_version_hash: str | None = None,
) -> None:
    session.execute(
        update(CommentLetter)
        .where(CommentLetter.company_id == company_id)
        .values(last_checked=checked_at)
    )
    mark_dataset_checked(
        session,
        company_id,
        "comment_letters",
        checked_at=checked_at,
        success=True,
        payload_version_hash=payload_version_hash,
        invalidate_hot_cache=True,
    )


def _load_form144_document(client: EdgarClient, cik: str, filing_metadata: FilingMetadata) -> tuple[str, str]:
    accession = filing_metadata.accession_number
    primary_document = (filing_metadata.primary_document or "").strip()
    if primary_document:
        try:
            return client.get_filing_document_text(cik, accession, primary_document)
        except Exception:
            logger.exception("Unable to fetch Form 144 primary document for accession %s", accession)

    try:
        directory_index = client.get_filing_directory_index(cik, accession)
    except Exception:
        logger.exception("Unable to fetch Form 144 directory index for accession %s", accession)
        raise

    candidates: list[str] = []
    for item in directory_index.get("directory", {}).get("item", []) or []:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        if not name or "/" in name:
            continue
        lower_name = name.lower()
        if lower_name.endswith((".xml", ".htm", ".html", ".txt")):
            candidates.append(name)

    for name in sorted(set(candidates), key=lambda value: (0 if value.lower().endswith(".xml") else 1, len(value))):
        try:
            return client.get_filing_document_text(cik, accession, name)
        except Exception:
            continue

    raise ValueError(f"Unable to load Form 144 document for accession {accession}")


def _parse_form144_filings(
    *,
    payload: str,
    source_url: str,
    filing_metadata: FilingMetadata,
) -> list[NormalizedForm144Filing]:
    rows = _parse_form144_xml_rows(payload, source_url, filing_metadata)
    if rows:
        return rows
    fallback = _parse_form144_text_row(payload, source_url, filing_metadata)
    if fallback is None:
        return []
    return [fallback]


def _parse_form144_xml_rows(
    payload: str,
    source_url: str,
    filing_metadata: FilingMetadata,
) -> list[NormalizedForm144Filing]:
    try:
        root = ET.fromstring(payload)
    except ET.ParseError:
        return []

    filer_name = _xml_first_text(root, ["nameOfPersonForWhoseAccountTheSecuritiesAreToBeSold", "filerName", "name"])
    relationship = _xml_first_text(root, ["relationshipToIssuer", "personRelationshipToIssuer", "relationship"])
    issuer_name = _xml_first_text(root, ["issuerName", "nameOfIssuer"])
    security_title = _xml_first_text(root, ["titleOfTheClassOfSecuritiesToBeSold", "titleOfSecuritiesToBeSold", "securityTitle"])
    planned_sale_date = _parse_flexible_date(_xml_first_text(root, ["approximateDateOfSale", "dateOfSale", "dateOfTheSale"]))
    shares_to_be_sold = _parse_optional_float(
        _xml_first_text(root, ["numberOfSharesOrOtherUnitsToBeSold", "amountOfSecuritiesToBeSold", "numberOfSharesToBeSold"])
    )
    aggregate_market_value = _parse_optional_float(_xml_first_text(root, ["aggregateMarketValue", "marketValue"]))
    shares_owned_after_sale = _parse_optional_float(
        _xml_first_text(root, ["numberOfSharesOrOtherUnitsOutstanding", "sharesOwnedAfterSale", "amountOwnedAfterSale"])
    )
    broker_name = _xml_first_text(root, ["nameOfEachBrokerThroughWhomTheSecuritiesAreToBeOfferedOrSold", "brokerName"])

    summary = (
        f"Form 144 planned sale by {filer_name}."
        if filer_name
        else "Form 144 planned insider sale disclosure."
    )

    row = NormalizedForm144Filing(
        accession_number=filing_metadata.accession_number,
        form=_base_form(filing_metadata.form) or "144",
        filing_date=filing_metadata.filing_date,
        report_date=filing_metadata.report_date,
        transaction_index=0,
        filer_name=filer_name,
        relationship_to_issuer=relationship,
        issuer_name=issuer_name,
        security_title=security_title,
        planned_sale_date=planned_sale_date,
        shares_to_be_sold=shares_to_be_sold,
        aggregate_market_value=aggregate_market_value,
        shares_owned_after_sale=shares_owned_after_sale,
        broker_name=broker_name,
        source_url=source_url,
        summary=summary,
    )
    if not any([
        row.filer_name,
        row.issuer_name,
        row.security_title,
        row.planned_sale_date,
        row.shares_to_be_sold,
    ]):
        return []
    return [row]


def _parse_form144_text_row(
    payload: str,
    source_url: str,
    filing_metadata: FilingMetadata,
) -> NormalizedForm144Filing | None:
    plain = re.sub(r"<[^>]+>", "\n", payload)
    plain = re.sub(r"\r", "", plain)
    if not plain:
        return None

    filer_name = _regex_capture(plain, r"(?im)^\s*Name\s+of\s+Person\s+for\s+Whose\s+Account\s+the\s+Securities\s+Are\s+to\s+Be\s+Sold\s*[:\-]\s*(.+)$")
    relationship = _regex_capture(plain, r"(?im)^\s*Relationship\s+to\s+Issuer\s*[:\-]\s*(.+)$")
    issuer_name = _regex_capture(plain, r"(?im)^\s*Issuer\s+Name\s*[:\-]\s*(.+)$")
    security_title = _regex_capture(plain, r"(?im)^\s*Title\s+of\s+the\s+Class\s+of\s+Securities\s+to\s+be\s+Sold\s*[:\-]\s*(.+)$")
    planned_sale_date = _parse_flexible_date(
        _regex_capture(plain, r"(?im)^\s*Approximate\s+Date\s+of\s+Sale\s*[:\-]\s*([0-9]{1,2}/[0-9]{1,2}/[0-9]{4}|[0-9]{4}-[0-9]{2}-[0-9]{2})")
    )
    shares_to_be_sold = _parse_optional_amount(
        _regex_capture(plain, r"(?im)^\s*Number\s+of\s+Shares\s+or\s+Other\s+Units\s+to\s+Be\s+Sold\s*[:\-]\s*([$0-9,\.]+)")
    )
    aggregate_market_value = _parse_optional_amount(
        _regex_capture(plain, r"(?im)^\s*Aggregate\s+Market\s+Value\s*[:\-]\s*([$0-9,\.]+)")
    )

    if not any([filer_name, issuer_name, security_title, planned_sale_date, shares_to_be_sold]):
        return None

    return NormalizedForm144Filing(
        accession_number=filing_metadata.accession_number,
        form=_base_form(filing_metadata.form) or "144",
        filing_date=filing_metadata.filing_date,
        report_date=filing_metadata.report_date,
        transaction_index=0,
        filer_name=filer_name,
        relationship_to_issuer=relationship,
        issuer_name=issuer_name,
        security_title=security_title,
        planned_sale_date=planned_sale_date,
        shares_to_be_sold=shares_to_be_sold,
        aggregate_market_value=aggregate_market_value,
        shares_owned_after_sale=None,
        broker_name=None,
        source_url=source_url,
        summary=f"Form 144 planned sale by {filer_name}." if filer_name else "Form 144 planned insider sale disclosure.",
    )


def _xml_first_text(root: ET.Element, candidate_tags: list[str]) -> str | None:
    lowered_candidates = {tag.lower() for tag in candidate_tags}
    for node in root.iter():
        local_tag = node.tag.split("}")[-1].lower()
        if local_tag in lowered_candidates:
            text = _clean_text("".join(node.itertext()))
            if text:
                return text
    return None


def _regex_capture(value: str, pattern: str) -> str | None:
    match = re.search(pattern, value, flags=re.IGNORECASE)
    if not match:
        return None
    return _clean_text(match.group(1))


def _parse_flexible_date(value: Any) -> date | None:
    cleaned = _clean_text(value)
    if cleaned is None:
        return None
    try:
        return _parse_date(cleaned)
    except ValueError:
        pass
    match = re.fullmatch(r"(\d{1,2})/(\d{1,2})/(\d{4})", cleaned)
    if not match:
        return None
    month, day, year = int(match.group(1)), int(match.group(2)), int(match.group(3))
    try:
        return date(year, month, day)
    except ValueError:
        return None


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
            plan_signal = _extract_form4_plan_signal(
                footnote_ids=footnote_ids,
                footnotes=footnotes,
                action=_normalize_insider_action(transaction_code, acquired_disposed),
                document_10b5_1=document_10b5_1,
            )
            is_10b5_1 = plan_signal.is_10b5_1
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
                        sale_context=plan_signal.sale_context,
                        plan_adoption_date=plan_signal.plan_adoption_date,
                        plan_modification=plan_signal.plan_modification,
                        plan_modification_date=plan_signal.plan_modification_date,
                        plan_signal_confidence=plan_signal.plan_signal_confidence,
                        plan_signal_provenance=plan_signal.plan_signal_provenance,
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
        text = footnotes.get(footnote_id, "")
        normalized_text = re.sub(r"[^a-z0-9]+", "", text.lower())
        if "10b51" in normalized_text and not _text_negates_10b5_1(text):
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
        if "10b51" in compact and not _text_negates_10b5_1(text):
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


def _extract_form4_plan_signal(
    *,
    footnote_ids: set[str],
    footnotes: dict[str, str],
    action: str,
    document_10b5_1: bool,
) -> Form4PlanSignal:
    relevant_notes: list[tuple[str, str]] = []
    for footnote_id in sorted(footnote_ids):
        text = footnotes.get(footnote_id, "").strip()
        if text:
            relevant_notes.append((footnote_id, text))

    references_10b5_in_footnotes = any(_text_mentions_10b5_1(note) and not _text_negates_10b5_1(note) for _, note in relevant_notes)
    is_10b5_1 = bool(document_10b5_1 or references_10b5_in_footnotes)

    adoption_date: date | None = None
    plan_modification: str | None = None
    plan_modification_date: date | None = None
    has_explicit_planned = False
    has_explicit_discretionary = False
    provenance: list[str] = []

    if document_10b5_1:
        provenance.append("ownershipDocument.aff10b5One")

    for footnote_id, note in relevant_notes:
        normalized_note = note.lower()
        if _text_mentions_10b5_1(note) or any(keyword in normalized_note for keyword in ("trading plan", "adopted", "amended", "terminated")):
            provenance.append(f"footnote:{footnote_id}")

        if _is_explicit_discretionary_text(note):
            has_explicit_discretionary = True
        if _is_explicit_planned_text(note):
            has_explicit_planned = True

        if adoption_date is None:
            adoption_date = _extract_plan_adoption_date(note)

        note_modification, note_modification_date = _extract_plan_modification(note)
        if note_modification is not None:
            if plan_modification is None:
                plan_modification = note_modification
            elif plan_modification != note_modification:
                plan_modification = "amendment_or_termination"
            if plan_modification_date is None and note_modification_date is not None:
                plan_modification_date = note_modification_date

    sale_context: str | None = None
    if action == "sell":
        if has_explicit_discretionary:
            sale_context = "discretionary"
        elif is_10b5_1 or has_explicit_planned or adoption_date is not None:
            sale_context = "planned"
        elif footnote_ids:
            sale_context = "unknown"

    confidence: str | None = None
    if has_explicit_discretionary or has_explicit_planned:
        confidence = "high"
    elif is_10b5_1 and provenance:
        confidence = "medium"
    elif adoption_date is not None or plan_modification is not None:
        confidence = "low"

    return Form4PlanSignal(
        is_10b5_1=is_10b5_1,
        sale_context=sale_context,
        plan_adoption_date=adoption_date,
        plan_modification=plan_modification,
        plan_modification_date=plan_modification_date,
        plan_signal_confidence=confidence,
        plan_signal_provenance=provenance or None,
    )


def _text_mentions_10b5_1(value: str) -> bool:
    compact = re.sub(r"[^a-z0-9]+", "", value.lower())
    return "10b51" in compact


def _text_negates_10b5_1(value: str) -> bool:
    normalized = re.sub(r"\s+", " ", value.lower()).strip()
    return bool(
        re.search(r"\bnot\s+(?:pursuant\s+to|under|subject\s+to)\b[^\n\.;]{0,80}\b10b5\s*-?\s*1\b", normalized)
        or re.search(r"\boutside\s+(?:of\s+)?(?:a\s+)?(?:rule\s+)?10b5\s*-?\s*1\b", normalized)
    )


def _is_explicit_planned_text(value: str) -> bool:
    normalized = re.sub(r"\s+", " ", value.lower()).strip()
    if _text_negates_10b5_1(value):
        return False
    if re.search(r"\b(?:pursuant\s+to|under|in\s+accordance\s+with|subject\s+to)\b[^\n\.;]{0,120}\b10b5\s*-?\s*1\b", normalized):
        return True
    if _text_mentions_10b5_1(value) and "trading plan" in normalized:
        return True
    if _text_mentions_10b5_1(value) and re.search(r"\b(?:adopted|entered\s+into|established)\b", normalized):
        return True
    return False


def _is_explicit_discretionary_text(value: str) -> bool:
    normalized = re.sub(r"\s+", " ", value.lower()).strip()
    return bool(
        _text_negates_10b5_1(value)
        or re.search(r"\bdiscretionary\s+sale\b", normalized)
        or re.search(r"\bsale\s+was\s+discretionary\b", normalized)
    )


def _extract_plan_adoption_date(value: str) -> date | None:
    normalized = re.sub(r"\s+", " ", value.lower()).strip()
    if "plan" not in normalized:
        return None

    match = re.search(
        r"\b(?:adopted|entered\s+into|established)\b\s*(?:on\s*)?(?P<date>[A-Za-z]+\s+\d{1,2},?\s+\d{4}|\d{4}-\d{2}-\d{2}|\d{1,2}/\d{1,2}/\d{4})",
        value,
        flags=re.IGNORECASE,
    )
    if not match:
        return None
    return _parse_natural_language_date(match.group("date"))


def _extract_plan_modification(value: str) -> tuple[str | None, date | None]:
    normalized = re.sub(r"\s+", " ", value.lower()).strip()
    if "plan" not in normalized and not _text_mentions_10b5_1(value):
        return None, None

    has_amendment = bool(re.search(r"\b(?:amend|amended|modif(?:y|ied)|revise(?:d)?)\b", normalized))
    has_termination = bool(re.search(r"\b(?:terminate|terminated|cancel(?:led)?|ceased)\b", normalized))
    if not has_amendment and not has_termination:
        return None, None

    if has_amendment and has_termination:
        modification = "amendment_or_termination"
    elif has_amendment:
        modification = "amendment"
    else:
        modification = "termination"

    match = re.search(
        r"\b(?:amend(?:ed)?|modif(?:y|ied)|revise(?:d)?|terminate(?:d)?|cancel(?:led)?|ceased)\b\s*(?:on\s*)?(?P<date>[A-Za-z]+\s+\d{1,2},?\s+\d{4}|\d{4}-\d{2}-\d{2}|\d{1,2}/\d{1,2}/\d{4})",
        value,
        flags=re.IGNORECASE,
    )
    modification_date = _parse_natural_language_date(match.group("date")) if match else None
    return modification, modification_date


def _parse_natural_language_date(value: str | None) -> date | None:
    cleaned = _clean_text(value)
    if cleaned is None:
        return None

    iso_or_numeric = _parse_flexible_date(cleaned)
    if iso_or_numeric is not None:
        return iso_or_numeric

    normalized = re.sub(r"\b(\d{1,2})(st|nd|rd|th)\b", r"\1", cleaned, flags=re.IGNORECASE)
    for pattern in ("%B %d, %Y", "%b %d, %Y", "%B %d %Y", "%b %d %Y"):
        try:
            return datetime.strptime(normalized, pattern).date()
        except ValueError:
            continue
    return None


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


def _parse_optional_amount(value: Any) -> float | None:
    cleaned = _clean_text(value)
    if cleaned is None:
        return None
    normalized = cleaned.replace("$", "")
    return _parse_optional_float(normalized)


def _clean_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _retry_wait(retry_after: str | None, client_config: SecClientConfig, attempt: int) -> float:
    retry_after_seconds = _parse_retry_after_seconds(retry_after)
    if retry_after_seconds is not None:
        return min(max(retry_after_seconds, client_config.retry_backoff_seconds), client_config.max_retry_after_seconds)
    return min(client_config.retry_backoff_seconds * (2 ** attempt), client_config.max_retry_backoff_seconds)


def _parse_retry_after_seconds(retry_after: str | None) -> float | None:
    cleaned = str(retry_after or "").strip()
    if not cleaned:
        return None
    if cleaned.isdigit():
        return float(cleaned)
    try:
        retry_at = parsedate_to_datetime(cleaned)
    except (TypeError, ValueError, IndexError, OverflowError):
        return None
    if retry_at.tzinfo is None:
        retry_at = retry_at.replace(tzinfo=timezone.utc)
    return max(0.0, (retry_at - datetime.now(timezone.utc)).total_seconds())


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
    state_last_checked, state_cache = cache_state_for_dataset(session, company_id, "financials")
    if state_cache != "missing":
        return state_last_checked

    statement = select(func.max(FinancialStatement.last_checked)).where(
        FinancialStatement.company_id == company_id,
        FinancialStatement.statement_type == CANONICAL_STATEMENT_TYPE,
    )
    scanned = session.execute(statement).scalar_one_or_none()
    normalized = _normalize_datetime_value(scanned)
    if normalized is not None:
        mark_dataset_checked(session, company_id, "financials", checked_at=normalized, success=True)
    return scanned


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
    *,
    statement_type: str = CANONICAL_STATEMENT_TYPE,
) -> int:
    if not normalized_statements:
        return 0

    payload = [
        {
            "company_id": company.id,
            "period_start": statement.period_start,
            "period_end": statement.period_end,
            "filing_type": statement.filing_type,
            "statement_type": statement_type,
            "data": statement.data,
            "selected_facts": _json_ready(statement.selected_facts),
            "reconciliation": _json_ready(statement.reconciliation),
            "source": statement.source,
            "last_updated": checked_at,
            "filing_acceptance_at": statement.filing_acceptance_at,
            "fetch_timestamp": checked_at,
            "last_checked": checked_at,
        }
        for statement in normalized_statements
    ]

    statement = insert(FinancialStatement).values(payload)
    data_changed = or_(
        FinancialStatement.data.is_distinct_from(statement.excluded.data),
        FinancialStatement.selected_facts.is_distinct_from(statement.excluded.selected_facts),
        FinancialStatement.reconciliation.is_distinct_from(statement.excluded.reconciliation),
        FinancialStatement.filing_type.is_distinct_from(statement.excluded.filing_type),
    )
    statement = statement.on_conflict_do_update(
        constraint="uq_financial_statements_company_period_type_source",
        set_={
            "data": statement.excluded.data,
            "selected_facts": statement.excluded.selected_facts,
            "reconciliation": statement.excluded.reconciliation,
            "last_updated": case(
                (data_changed, statement.excluded.last_updated),
                else_=FinancialStatement.last_updated,
            ),
            "filing_acceptance_at": statement.excluded.filing_acceptance_at,
            "fetch_timestamp": statement.excluded.fetch_timestamp,
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
            "data": _json_ready(item.data),
            "selected_facts": {},
            "reconciliation": {},
            "source": item.source,
            "last_updated": checked_at,
            "fetch_timestamp": checked_at,
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
            "selected_facts": statement.excluded.selected_facts,
            "reconciliation": statement.excluded.reconciliation,
            "last_updated": case(
                (data_changed, statement.excluded.last_updated),
                else_=FinancialStatement.last_updated,
            ),
            "fetch_timestamp": statement.excluded.fetch_timestamp,
            "last_checked": statement.excluded.last_checked,
            "filing_type": statement.excluded.filing_type,
        },
    )
    session.execute(statement)
    return len(payload)


def _replace_financial_restatements(
    session: Session,
    company: Company,
    normalized_statements: list[NormalizedStatement],
    checked_at: datetime,
) -> int:
    session.execute(delete(FinancialRestatement).where(FinancialRestatement.company_id == company.id))

    payload = _build_financial_restatement_payloads(company.id, normalized_statements, checked_at)
    if not payload:
        return 0

    session.execute(insert(FinancialRestatement).values(payload))
    return len(payload)


def _replace_filing_risk_signals(
    session: Session,
    company: Company,
    parsed_insights: list[ParsedFilingInsight],
    checked_at: datetime,
    payload_version_hash: str | None = None,
) -> int:
    session.execute(delete(FilingRiskSignal).where(FilingRiskSignal.company_id == company.id))

    payload = _build_filing_risk_signal_payloads(company, parsed_insights, checked_at)
    if payload:
        session.execute(insert(FilingRiskSignal).values(payload))

    mark_dataset_checked(
        session,
        company.id,
        FILING_RISK_SIGNALS_DATASET,
        checked_at=checked_at,
        success=True,
        payload_version_hash=payload_version_hash,
    )
    return len(payload)


def _build_filing_risk_signal_payloads(
    company: Company,
    parsed_insights: list[ParsedFilingInsight],
    checked_at: datetime,
) -> list[dict[str, Any]]:
    payloads: list[dict[str, Any]] = []
    for item in parsed_insights:
        risk_signals = item.data.get("risk_signals") if isinstance(item.data, dict) else None
        if not isinstance(risk_signals, list):
            continue
        for match in risk_signals:
            if not isinstance(match, dict):
                continue
            signal_category = str(match.get("signal_category") or "").strip()
            matched_phrase = str(match.get("matched_phrase") or "").strip()
            context_snippet = str(match.get("context_snippet") or "").strip()
            if not signal_category or not matched_phrase or not context_snippet:
                continue
            payloads.append(
                {
                    "company_id": company.id,
                    "ticker": str(match.get("ticker") or company.ticker),
                    "cik": str(match.get("cik") or company.cik),
                    "accession_number": str(match.get("accession_number") or item.accession_number),
                    "form_type": str(match.get("form_type") or item.filing_type),
                    "filed_date": match.get("filed_date") or item.period_end,
                    "signal_category": signal_category,
                    "matched_phrase": matched_phrase[:255],
                    "context_snippet": context_snippet[:1000],
                    "confidence": str(match.get("confidence") or "medium"),
                    "severity": str(match.get("severity") or "medium"),
                    "source": str(match.get("source") or item.source),
                    "provenance": str(match.get("provenance") or "sec_filing_text"),
                    "last_updated": checked_at,
                    "last_checked": checked_at,
                }
            )
    return payloads


def _build_financial_restatement_payloads(
    company_id: int,
    normalized_statements: list[NormalizedStatement],
    checked_at: datetime,
) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, date, date], list[NormalizedStatement]] = {}
    for statement in normalized_statements:
        if statement.filing_type not in RESTATEMENT_TRACKED_FORMS:
            continue
        grouped.setdefault((statement.filing_type, statement.period_start, statement.period_end), []).append(statement)

    payloads: list[dict[str, Any]] = []
    for statements in grouped.values():
        ordered = sorted(statements, key=_normalized_statement_sort_key)
        previous: NormalizedStatement | None = None
        for current in ordered:
            is_amendment = _is_amended_form(current.form)
            normalized_changes = _build_normalized_data_changes(previous, current)
            companyfacts_changes = _build_companyfacts_changes(previous, current)
            changed_metric_keys = sorted(
                {
                    *(str(item.get("metric_key") or "") for item in normalized_changes),
                    *(
                        str(item.get("metric_key") or "")
                        for item in companyfacts_changes
                        if bool(item.get("value_changed"))
                    ),
                }
                - {""}
            )
            if previous is None and not is_amendment:
                previous = current
                continue
            if previous is not None and not is_amendment and not changed_metric_keys:
                previous = current
                continue

            payloads.append(
                {
                    "company_id": company_id,
                    "statement_type": CANONICAL_STATEMENT_TYPE,
                    "filing_type": current.filing_type,
                    "form": current.form,
                    "accession_number": current.accession_number,
                    "previous_accession_number": previous.accession_number if previous is not None else None,
                    "period_start": current.period_start,
                    "period_end": current.period_end,
                    "filing_date": current.filing_date,
                    "previous_filing_date": previous.filing_date if previous is not None else None,
                    "filing_acceptance_at": current.filing_acceptance_at,
                    "previous_filing_acceptance_at": previous.filing_acceptance_at if previous is not None else None,
                    "source": current.source,
                    "previous_source": previous.source if previous is not None else None,
                    "is_amendment": is_amendment,
                    "detection_kind": "amended_filing" if is_amendment else "companyfacts_revision",
                    "changed_metric_keys": changed_metric_keys,
                    "companyfacts_changes": _json_ready(companyfacts_changes),
                    "normalized_data_changes": _json_ready(normalized_changes),
                    "confidence_impact": _json_ready(_build_restatement_confidence_impact(
                        changed_metric_keys=changed_metric_keys,
                        normalized_changes=normalized_changes,
                        companyfacts_changes=companyfacts_changes,
                        is_amendment=is_amendment,
                    )),
                    "last_updated": checked_at,
                    "last_checked": checked_at,
                }
            )
            previous = current

    return payloads


def _build_normalized_data_changes(
    previous: NormalizedStatement | None,
    current: NormalizedStatement,
) -> list[dict[str, Any]]:
    if previous is None:
        return []

    changes: list[dict[str, Any]] = []
    previous_data = previous.data or {}
    current_data = current.data or {}
    for metric_key in sorted({*previous_data.keys(), *current_data.keys()} - {"segment_breakdown"}):
        previous_value = previous_data.get(metric_key)
        current_value = current_data.get(metric_key)
        if previous_value == current_value:
            continue
        if isinstance(previous_value, (dict, list)) or isinstance(current_value, (dict, list)):
            continue
        changes.append(
            {
                "metric_key": metric_key,
                "previous_value": previous_value,
                "current_value": current_value,
                "delta": _metric_delta(previous_value, current_value),
                "relative_change": _relative_change(previous_value, current_value),
                "direction": _change_direction(previous_value, current_value),
            }
        )
    return changes


def _build_companyfacts_changes(
    previous: NormalizedStatement | None,
    current: NormalizedStatement,
) -> list[dict[str, Any]]:
    previous_facts = previous.selected_facts if previous is not None else {}
    previous_data = previous.data if previous is not None else {}
    current_facts = current.selected_facts or {}
    changes: list[dict[str, Any]] = []
    for metric_key in sorted({*previous_facts.keys(), *current_facts.keys()}):
        previous_fact = previous_facts.get(metric_key)
        current_fact = current_facts.get(metric_key)
        if previous_fact == current_fact:
            continue
        changes.append(
            {
                "metric_key": metric_key,
                "previous_fact": previous_fact,
                "current_fact": current_fact,
                "value_changed": previous_data.get(metric_key) != (current.data or {}).get(metric_key),
            }
        )
    return changes


def _build_restatement_confidence_impact(
    *,
    changed_metric_keys: list[str],
    normalized_changes: list[dict[str, Any]],
    companyfacts_changes: list[dict[str, Any]],
    is_amendment: bool,
) -> dict[str, Any]:
    core_metrics = {"revenue", "operating_income", "net_income", "operating_cash_flow", "free_cash_flow", "eps"}
    flags = {"restatement_detected"}
    if is_amendment:
        flags.add("amended_sec_filing")
    if normalized_changes:
        flags.add("normalized_statement_changed")
    if companyfacts_changes:
        flags.add("companyfacts_observation_changed")
    if any(metric in core_metrics for metric in changed_metric_keys):
        flags.add("core_metric_changed")

    relative_moves = [
        abs(float(value))
        for value in (item.get("relative_change") for item in normalized_changes)
        if isinstance(value, (int, float))
    ]
    largest_relative_change = max(relative_moves, default=None)
    if largest_relative_change is not None and largest_relative_change >= 0.1:
        flags.add("material_metric_change")

    severity = "low"
    if "material_metric_change" in flags or {"revenue", "net_income", "eps"} & set(changed_metric_keys):
        severity = "high"
    elif normalized_changes or companyfacts_changes:
        severity = "medium"

    return {
        "severity": severity,
        "flags": sorted(flags),
        "largest_relative_change": largest_relative_change,
        "changed_metric_count": len(changed_metric_keys),
    }


def _normalized_statement_sort_key(statement: NormalizedStatement) -> tuple[datetime, date, str]:
    return (
        _normalized_statement_effective_at(statement),
        statement.period_end,
        statement.accession_number,
    )


def _normalized_statement_effective_at(statement: NormalizedStatement) -> datetime:
    if statement.filing_acceptance_at is not None:
        return statement.filing_acceptance_at
    if statement.filing_date is not None:
        return datetime.combine(statement.filing_date, datetime.max.time(), tzinfo=timezone.utc)
    return datetime.combine(statement.period_end, datetime.max.time(), tzinfo=timezone.utc)


def _candidate_fact_metadata(candidate: FactCandidate, *, source: str | None = None) -> dict[str, Any]:
    return {
        "accession_number": candidate.accession_number,
        "form": candidate.form,
        "taxonomy": candidate.taxonomy,
        "tag": candidate.tag,
        "unit": candidate.unit,
        "source": source,
        "filed_at": candidate.filed_at,
        "period_start": candidate.period_start,
        "period_end": candidate.period_end,
        "value": candidate.value,
    }


def _metric_delta(previous_value: Any, current_value: Any) -> int | float | None:
    if not isinstance(previous_value, (int, float)) or not isinstance(current_value, (int, float)):
        return None
    return _json_number(current_value - previous_value)


def _relative_change(previous_value: Any, current_value: Any) -> float | None:
    if not isinstance(previous_value, (int, float)) or not isinstance(current_value, (int, float)):
        return None
    if previous_value == 0:
        return None
    return float((current_value - previous_value) / abs(previous_value))


def _change_direction(previous_value: Any, current_value: Any) -> str:
    if previous_value is None and current_value is not None:
        return "added"
    if previous_value is not None and current_value is None:
        return "removed"
    if isinstance(previous_value, (int, float)) and isinstance(current_value, (int, float)):
        if current_value > previous_value:
            return "increase"
        if current_value < previous_value:
            return "decrease"
    return "changed"


def _touch_company_statements(
    session: Session,
    company_id: int,
    checked_at: datetime,
    *,
    payload_version_hash: str | None = None,
    invalidate_hot_cache: bool = True,
) -> None:
    statement = (
        update(FinancialStatement)
        .where(
            FinancialStatement.company_id == company_id,
            FinancialStatement.statement_type.in_((CANONICAL_STATEMENT_TYPE, BANK_REGULATORY_STATEMENT_TYPE)),
        )
        .values(last_checked=checked_at)
    )
    session.execute(statement)
    mark_dataset_checked(
        session,
        company_id,
        "financials",
        checked_at=checked_at,
        success=True,
        payload_version_hash=payload_version_hash,
        invalidate_hot_cache=invalidate_hot_cache,
    )


def _build_financials_refresh_fingerprint(
    companyfacts: dict[str, Any],
    filing_index: dict[str, FilingMetadata],
) -> str:
    payload = {
        "version": FINANCIALS_REFRESH_FINGERPRINT_VERSION,
        "companyfacts": companyfacts,
        "filings": [
            {
                "accession_number": metadata.accession_number,
                "form": metadata.form,
                "filing_date": metadata.filing_date.isoformat() if metadata.filing_date else None,
                "report_date": metadata.report_date.isoformat() if metadata.report_date else None,
                "acceptance_datetime": metadata.acceptance_datetime.isoformat() if metadata.acceptance_datetime else None,
                "primary_document": metadata.primary_document,
                "primary_doc_description": metadata.primary_doc_description,
            }
            for metadata in sorted(
                filing_index.values(),
                key=lambda item: (item.filing_date or date.min, item.accession_number),
                reverse=True,
            )
        ],
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()[:32]


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
        filing_acceptance_at=filing_metadata.acceptance_datetime if filing_metadata else None,
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
    form = _normalize_form_text(observation.get("form") or (filing_metadata.form if filing_metadata else None))
    if _base_form(form) not in SUPPORTED_FORMS:
        return None

    value = observation.get("val")
    if value is None:
        return None

    return FactCandidate(
        metric=metric,
        accession_number=accession_number,
        form=form,
        value=_json_number(value),
        unit=str(observation.get("unit") or "").strip() or None,
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
    form = _normalize_form_text(observation.get("form") or (filing_metadata.form if filing_metadata else None))
    if _base_form(form) not in SUPPORTED_FORMS:
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
    oi_by_period: dict[date, list[tuple[str, int | float]]] = {period_end: [] for period_end in header_dates}
    assets_by_period: dict[date, list[tuple[str, int | float]]] = {period_end: [] for period_end in header_dates}
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

        if current_segment is None:
            continue

        value_cells = cells[1 : 1 + len(header_dates)]

        if _is_revenue_metric_label(label):
            for index, cell in enumerate(value_cells):
                value = _parse_table_number(cell.get_text(" ", strip=True))
                if value is not None and value > 0:
                    segments_by_period[header_dates[index]].append((current_segment, value))
        elif _is_operating_income_metric_label(label):
            for index, cell in enumerate(value_cells):
                value = _parse_table_number(cell.get_text(" ", strip=True))
                if value is not None:
                    oi_by_period[header_dates[index]].append((current_segment, value))
        elif _is_asset_metric_label(label):
            for index, cell in enumerate(value_cells):
                value = _parse_table_number(cell.get_text(" ", strip=True))
                if value is not None and value > 0:
                    assets_by_period[header_dates[index]].append((current_segment, value))

    payload_by_period: dict[date, list[dict[str, Any]]] = {}
    for period_end, segment_rows in segments_by_period.items():
        deduped: dict[str, int | float] = {}
        for segment_name, value in segment_rows:
            if segment_name not in deduped or value > deduped[segment_name]:
                deduped[segment_name] = value

        if len(deduped) < 2:
            continue

        total_revenue = sum(deduped.values())

        oi_deduped: dict[str, int | float] = {}
        for segment_name, value in oi_by_period.get(period_end, []):
            if segment_name not in oi_deduped:
                oi_deduped[segment_name] = value

        assets_deduped: dict[str, int | float] = {}
        for segment_name, value in assets_by_period.get(period_end, []):
            if segment_name not in assets_deduped or value > assets_deduped[segment_name]:
                assets_deduped[segment_name] = value

        payload_by_period[period_end] = [
            {
                "segment_id": _normalize_identifier(segment_name),
                "segment_name": segment_name,
                "axis_key": axis_key,
                "axis_label": axis_label,
                "kind": kind,
                "revenue": _json_number(value),
                "share_of_revenue": _json_number(value / total_revenue) if total_revenue else None,
                "operating_income": _json_number(oi_deduped[segment_name]) if segment_name in oi_deduped else None,
                "assets": _json_number(assets_deduped[segment_name]) if segment_name in assets_deduped else None,
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


def _is_operating_income_metric_label(label: str) -> bool:
    normalized_label = _normalize_identifier(label)
    return normalized_label.startswith(
        (
            "operatingincome",
            "operatingprofit",
            "incomefromoperations",
            "earningsfromoperations",
            "segmentprofitloss",
            "segmentoperating",
            "profitlossfromsegment",
        )
    )


def _is_asset_metric_label(label: str) -> bool:
    normalized_label = _normalize_identifier(label)
    return normalized_label in {
        "assets",
        "totalassets",
        "longlivedassets",
        "noncurrentassets",
        "identifiableassets",
        "segmentassets",
    }


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
    if metric in {"shares_outstanding", "weighted_average_diluted_shares", "shares_issued", "shares_repurchased"}:
        return _iter_share_observations(fact_payload)
    return _iter_monetary_observations(fact_payload)


def _iter_monetary_observations(fact_payload: dict[str, Any]) -> list[dict[str, Any]]:
    if not isinstance(fact_payload, dict):
        return []

    units_root = fact_payload.get("units", {})
    if not isinstance(units_root, dict):
        return []

    observations: list[dict[str, Any]] = []
    preferred_units: list[str] = []
    if "USD" in units_root:
        preferred_units.append("USD")
    preferred_units.extend(unit for unit in units_root if unit.startswith("USD") and unit != "USD")
    preferred_units.extend(
        unit for unit in units_root if unit not in preferred_units and _looks_like_monetary_unit(unit)
    )
    for unit in preferred_units:
        unit_observations = units_root.get(unit)
        if not isinstance(unit_observations, list):
            continue
        observations.extend({**observation, "unit": unit} for observation in unit_observations if isinstance(observation, dict))

    return observations


def _looks_like_monetary_unit(unit: str) -> bool:
    normalized = str(unit or "").strip().upper()
    if not normalized or "/" in normalized:
        return False
    if "SHARE" in normalized or normalized in {"PURE", "RATE", "PERCENT", "PCT"}:
        return False
    return re.fullmatch(r"[A-Z]{3}", normalized) is not None


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
        observations.extend({**observation, "unit": unit} for observation in unit_observations if isinstance(observation, dict))

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
        observations.extend({**observation, "unit": unit} for observation in unit_observations if isinstance(observation, dict))

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


def _build_archive_filing_url(cik: str, accession_number: str, primary_document: str | None) -> str:
    accession_compact = accession_number.replace("-", "")
    numeric_cik = str(int(cik))
    if primary_document:
        return f"https://www.sec.gov/Archives/edgar/data/{numeric_cik}/{accession_compact}/{primary_document}"
    return f"https://www.sec.gov/Archives/edgar/data/{numeric_cik}/{accession_compact}/index.html"


def _parse_datetime_value(value: str | None) -> datetime | None:
    if not value:
        return None
    cleaned = value.strip()
    if not cleaned:
        return None
    normalized = cleaned.replace("Z", "+00:00")
    for pattern in ("%Y-%m-%dT%H:%M:%S%z", "%Y%m%d%H%M%S"):
        try:
            parsed = datetime.strptime(normalized, pattern)
        except ValueError:
            continue
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _item_tokens(value: str | None) -> set[str]:
    normalized = (value or "").replace(" ", "")
    return {token for token in normalized.split(",") if token}


def _normalize_form_text(value: str | None) -> str:
    return str(value or "").strip().upper()


def _is_amended_form(value: str | None) -> bool:
    normalized = _normalize_form_text(value)
    return normalized.endswith("/A") or normalized.endswith("-A")


def _base_form(value: str | None) -> str:
    normalized = _normalize_form_text(value)
    if not normalized:
        return ""
    if normalized.endswith("/A") or normalized.endswith("-A"):
        return normalized[:-2]
    return normalized.split("/")[0]


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


def _json_ready(value: Any) -> Any:
    if isinstance(value, datetime):
        normalized = value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)
        return normalized.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(key): _json_ready(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_ready(item) for item in value]
    if isinstance(value, tuple):
        return [_json_ready(item) for item in value]
    return value


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


if __name__ == "__main__":
    raise SystemExit(worker_main())
