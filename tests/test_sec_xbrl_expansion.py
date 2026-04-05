from __future__ import annotations

from datetime import date, datetime, timezone
from types import SimpleNamespace

import app.main as main_module
from app.services.sec_edgar import EdgarNormalizer, FilingMetadata


def test_edgar_normalizer_maps_new_xbrl_metrics():
    accn = "0000000000-26-000010"
    companyfacts = {
        "facts": {
            "us-gaap": {
                "Revenues": {
                    "units": {
                        "USD": [
                            {
                                "accn": accn,
                                "form": "10-K",
                                "start": "2025-01-01",
                                "end": "2025-12-31",
                                "filed": "2026-02-20",
                                "val": 1000,
                            }
                        ]
                    }
                },
                "SellingGeneralAndAdministrativeExpense": {
                    "units": {
                        "USD": [
                            {
                                "accn": accn,
                                "form": "10-K",
                                "start": "2025-01-01",
                                "end": "2025-12-31",
                                "filed": "2026-02-20",
                                "val": 120,
                            }
                        ]
                    }
                },
                "ResearchAndDevelopmentExpense": {
                    "units": {
                        "USD": [
                            {
                                "accn": accn,
                                "form": "10-K",
                                "start": "2025-01-01",
                                "end": "2025-12-31",
                                "filed": "2026-02-20",
                                "val": 80,
                            }
                        ]
                    }
                },
                "InterestExpense": {
                    "units": {
                        "USD": [
                            {
                                "accn": accn,
                                "form": "10-K",
                                "start": "2025-01-01",
                                "end": "2025-12-31",
                                "filed": "2026-02-20",
                                "val": 15,
                            }
                        ]
                    }
                },
                "IncomeTaxExpenseBenefit": {
                    "units": {
                        "USD": [
                            {
                                "accn": accn,
                                "form": "10-K",
                                "start": "2025-01-01",
                                "end": "2025-12-31",
                                "filed": "2026-02-20",
                                "val": 25,
                            }
                        ]
                    }
                },
                "InventoryNet": {
                    "units": {
                        "USD": [
                            {
                                "accn": accn,
                                "form": "10-K",
                                "end": "2025-12-31",
                                "filed": "2026-02-20",
                                "val": 40,
                            }
                        ]
                    }
                },
                "CashAndCashEquivalentsAtCarryingValue": {
                    "units": {
                        "USD": [
                            {
                                "accn": accn,
                                "form": "10-K",
                                "end": "2025-12-31",
                                "filed": "2026-02-20",
                                "val": 150,
                            }
                        ]
                    }
                },
                "ShortTermInvestments": {
                    "units": {
                        "USD": [
                            {
                                "accn": accn,
                                "form": "10-K",
                                "end": "2025-12-31",
                                "filed": "2026-02-20",
                                "val": 50,
                            }
                        ]
                    }
                },
                "AccountsReceivableNetCurrent": {
                    "units": {
                        "USD": [
                            {
                                "accn": accn,
                                "form": "10-K",
                                "end": "2025-12-31",
                                "filed": "2026-02-20",
                                "val": 60,
                            }
                        ]
                    }
                },
                "AccountsPayableCurrent": {
                    "units": {
                        "USD": [
                            {
                                "accn": accn,
                                "form": "10-K",
                                "end": "2025-12-31",
                                "filed": "2026-02-20",
                                "val": 55,
                            }
                        ]
                    }
                },
                "LongTermDebtCurrent": {
                    "units": {
                        "USD": [
                            {
                                "accn": accn,
                                "form": "10-K",
                                "end": "2025-12-31",
                                "filed": "2026-02-20",
                                "val": 75,
                            }
                        ]
                    }
                },
                "GoodwillAndIntangibleAssetsNet": {
                    "units": {
                        "USD": [
                            {
                                "accn": accn,
                                "form": "10-K",
                                "end": "2025-12-31",
                                "filed": "2026-02-20",
                                "val": 210,
                            }
                        ]
                    }
                },
                "LongTermDebt": {
                    "units": {
                        "USD": [
                            {
                                "accn": accn,
                                "form": "10-K",
                                "end": "2025-12-31",
                                "filed": "2026-02-20",
                                "val": 320,
                            }
                        ]
                    }
                },
                "StockholdersEquity": {
                    "units": {
                        "USD": [
                            {
                                "accn": accn,
                                "form": "10-K",
                                "end": "2025-12-31",
                                "filed": "2026-02-20",
                                "val": 1800,
                            }
                        ]
                    }
                },
                "OperatingLeaseLiability": {
                    "units": {
                        "USD": [
                            {
                                "accn": accn,
                                "form": "10-K",
                                "end": "2025-12-31",
                                "filed": "2026-02-20",
                                "val": 44,
                            }
                        ]
                    }
                },
                "DepreciationDepletionAndAmortization": {
                    "units": {
                        "USD": [
                            {
                                "accn": accn,
                                "form": "10-K",
                                "start": "2025-01-01",
                                "end": "2025-12-31",
                                "filed": "2026-02-20",
                                "val": 70,
                            }
                        ]
                    }
                },
                "ShareBasedCompensation": {
                    "units": {
                        "USD": [
                            {
                                "accn": accn,
                                "form": "10-K",
                                "start": "2025-01-01",
                                "end": "2025-12-31",
                                "filed": "2026-02-20",
                                "val": 33,
                            }
                        ]
                    }
                },
                "WeightedAverageNumberOfDilutedSharesOutstanding": {
                    "units": {
                        "shares": [
                            {
                                "accn": accn,
                                "form": "10-K",
                                "start": "2025-01-01",
                                "end": "2025-12-31",
                                "filed": "2026-02-20",
                                "val": 999,
                            }
                        ]
                    }
                },
            }
        }
    }
    filing_index = {
        accn: FilingMetadata(
            accession_number=accn,
            form="10-K",
            filing_date=date(2026, 2, 20),
            report_date=date(2025, 12, 31),
            primary_document="annual.htm",
        )
    }

    statements = EdgarNormalizer().normalize("0000123456", companyfacts, filing_index)

    assert len(statements) == 1
    data = statements[0].data
    assert data["sga"] == 120
    assert data["research_and_development"] == 80
    assert data["interest_expense"] == 15
    assert data["income_tax_expense"] == 25
    assert data["inventory"] == 40
    assert data["cash_and_cash_equivalents"] == 150
    assert data["short_term_investments"] == 50
    assert data["cash_and_short_term_investments"] == 200
    assert data["accounts_receivable"] == 60
    assert data["accounts_payable"] == 55
    assert data["goodwill_and_intangibles"] == 210
    assert data["current_debt"] == 75
    assert data["long_term_debt"] == 320
    assert data["stockholders_equity"] == 1800
    assert data["lease_liabilities"] == 44
    assert data["depreciation_and_amortization"] == 70
    assert data["stock_based_compensation"] == 33
    assert data["weighted_average_diluted_shares"] == 999


def test_serialize_financial_includes_expanded_fields():
    statement = SimpleNamespace(
        accession_number="0000000000-26-000010",
        filing_type="10-K",
        statement_type="canonical",
        period_start=date(2025, 1, 1),
        period_end=date(2025, 12, 31),
        source="https://www.sec.gov/Archives/edgar/data/123/accn/annual.htm",
        last_updated=datetime(2026, 2, 21, tzinfo=timezone.utc),
        last_checked=datetime(2026, 2, 21, tzinfo=timezone.utc),
        data={
            "revenue": 1000,
            "gross_profit": 500,
            "operating_income": 240,
            "net_income": 180,
            "total_assets": 3000,
            "current_assets": 900,
            "total_liabilities": 1200,
            "current_liabilities": 450,
            "retained_earnings": 600,
            "sga": 120,
            "research_and_development": 80,
            "interest_expense": 15,
            "income_tax_expense": 25,
            "inventory": 40,
            "cash_and_cash_equivalents": 150,
            "short_term_investments": 50,
            "cash_and_short_term_investments": 200,
            "accounts_receivable": 60,
            "accounts_payable": 55,
            "goodwill_and_intangibles": 210,
            "current_debt": 75,
            "long_term_debt": 320,
            "stockholders_equity": 1800,
            "lease_liabilities": 44,
            "operating_cash_flow": 310,
            "depreciation_and_amortization": 70,
            "capex": 90,
            "acquisitions": None,
            "debt_changes": -10,
            "stock_compensation": None,
            "buybacks": None,
            "dividends": None,
            "free_cash_flow": 220,
            "eps": 4.2,
            "shares_outstanding": 120,
            "stock_based_compensation": 33,
            "weighted_average_diluted_shares": 999,
            "segment_breakdown": [],
        },
    )

    payload = main_module._serialize_financial(statement)

    assert payload.sga == 120
    assert payload.research_and_development == 80
    assert payload.interest_expense == 15
    assert payload.income_tax_expense == 25
    assert payload.inventory == 40
    assert payload.cash_and_cash_equivalents == 150
    assert payload.short_term_investments == 50
    assert payload.cash_and_short_term_investments == 200
    assert payload.accounts_receivable == 60
    assert payload.accounts_payable == 55
    assert payload.goodwill_and_intangibles == 210
    assert payload.current_debt == 75
    assert payload.long_term_debt == 320
    assert payload.stockholders_equity == 1800
    assert payload.lease_liabilities == 44
    assert payload.depreciation_and_amortization == 70
    assert payload.stock_based_compensation == 33
    assert payload.weighted_average_diluted_shares == 999


def test_edgar_normalizer_maps_capital_structure_supplemental_facts():
    accn = "0000000000-26-000020"
    companyfacts = {
        "facts": {
            "us-gaap": {
                "LongTermDebtCurrent": {"units": {"USD": [{"accn": accn, "form": "10-K", "end": "2025-12-31", "filed": "2026-02-20", "val": 30}]}},
                "LongTermDebt": {"units": {"USD": [{"accn": accn, "form": "10-K", "end": "2025-12-31", "filed": "2026-02-20", "val": 70}]}},
                "ProceedsFromIssuanceOfLongTermDebt": {"units": {"USD": [{"accn": accn, "form": "10-K", "start": "2025-01-01", "end": "2025-12-31", "filed": "2026-02-20", "val": 20}]}},
                "RepaymentsOfLongTermDebt": {"units": {"USD": [{"accn": accn, "form": "10-K", "start": "2025-01-01", "end": "2025-12-31", "filed": "2026-02-20", "val": -8}]}},
                "CommonStockSharesIssued": {"units": {"shares": [{"accn": accn, "form": "10-K", "start": "2025-01-01", "end": "2025-12-31", "filed": "2026-02-20", "val": 5}]}},
                "CommonStockSharesRepurchased": {"units": {"shares": [{"accn": accn, "form": "10-K", "start": "2025-01-01", "end": "2025-12-31", "filed": "2026-02-20", "val": 2}]}},
                "LongTermDebtMaturitiesRepaymentsOfPrincipalInNextTwelveMonths": {"units": {"USD": [{"accn": accn, "form": "10-K", "end": "2025-12-31", "filed": "2026-02-20", "val": 10}]}},
                "LongTermDebtMaturitiesRepaymentsOfPrincipalThereafter": {"units": {"USD": [{"accn": accn, "form": "10-K", "end": "2025-12-31", "filed": "2026-02-20", "val": 20}]}},
                "OperatingLeaseLiabilityPaymentsDueNextTwelveMonths": {"units": {"USD": [{"accn": accn, "form": "10-K", "end": "2025-12-31", "filed": "2026-02-20", "val": 3}]}},
                "OperatingLeaseLiabilityPaymentsDueThereafter": {"units": {"USD": [{"accn": accn, "form": "10-K", "end": "2025-12-31", "filed": "2026-02-20", "val": 6}]}},
            }
        }
    }
    filing_index = {
        accn: FilingMetadata(
            accession_number=accn,
            form="10-K",
            filing_date=date(2026, 2, 20),
            report_date=date(2025, 12, 31),
            primary_document="annual.htm",
        )
    }

    statements = EdgarNormalizer().normalize("0000123456", companyfacts, filing_index)

    assert len(statements) == 1
    data = statements[0].data
    assert data["current_debt"] == 30
    assert data["long_term_debt"] == 70
    assert data["debt_issuance"] == 20
    assert data["debt_repayment"] == 8
    assert data["debt_changes"] == 12
    assert data["shares_issued"] == 5
    assert data["shares_repurchased"] == 2
    assert data["debt_maturity_due_next_twelve_months"] == 10
    assert data["debt_maturity_due_thereafter"] == 20
    assert data["lease_due_next_twelve_months"] == 3
    assert data["lease_due_thereafter"] == 6


def test_edgar_normalizer_maps_non_usd_monetary_units():
    accn = "0000000000-26-000021"
    companyfacts = {
        "facts": {
            "us-gaap": {
                "RevenueFromContractWithCustomerExcludingAssessedTax": {
                    "units": {
                        "EUR": [
                            {
                                "accn": accn,
                                "form": "20-F",
                                "start": "2025-01-01",
                                "end": "2025-12-31",
                                "filed": "2026-02-20",
                                "val": 32667,
                            }
                        ]
                    }
                },
                "OperatingIncomeLoss": {
                    "units": {
                        "EUR": [
                            {
                                "accn": accn,
                                "form": "20-F",
                                "start": "2025-01-01",
                                "end": "2025-12-31",
                                "filed": "2026-02-20",
                                "val": 11301,
                            }
                        ]
                    }
                },
                "NetIncomeLoss": {
                    "units": {
                        "EUR": [
                            {
                                "accn": accn,
                                "form": "20-F",
                                "start": "2025-01-01",
                                "end": "2025-12-31",
                                "filed": "2026-02-20",
                                "val": 9571,
                            }
                        ]
                    }
                },
                "NetCashProvidedByUsedInOperatingActivities": {
                    "units": {
                        "EUR": [
                            {
                                "accn": accn,
                                "form": "20-F",
                                "start": "2025-01-01",
                                "end": "2025-12-31",
                                "filed": "2026-02-20",
                                "val": 12658,
                            }
                        ]
                    }
                },
                "PaymentsToAcquirePropertyPlantAndEquipment": {
                    "units": {
                        "EUR": [
                            {
                                "accn": accn,
                                "form": "20-F",
                                "start": "2025-01-01",
                                "end": "2025-12-31",
                                "filed": "2026-02-20",
                                "val": -3778,
                            }
                        ]
                    }
                },
            }
        }
    }
    filing_index = {
        accn: FilingMetadata(
            accession_number=accn,
            form="20-F",
            filing_date=date(2026, 2, 20),
            report_date=date(2025, 12, 31),
            primary_document="annual.htm",
        )
    }

    statements = EdgarNormalizer().normalize("0000123456", companyfacts, filing_index)

    assert len(statements) == 1
    data = statements[0].data
    assert data["revenue"] == 32667
    assert data["operating_income"] == 11301
    assert data["net_income"] == 9571
    assert data["operating_cash_flow"] == 12658
    assert data["capex"] == 3778
    assert data["free_cash_flow"] == 8880


def test_serialize_capital_structure_snapshot_includes_new_sections():
    snapshot = SimpleNamespace(
        accession_number="0000000000-26-000020",
        filing_type="10-K",
        statement_type="canonical_xbrl",
        period_start=date(2025, 1, 1),
        period_end=date(2025, 12, 31),
        source="https://data.sec.gov/api/xbrl/companyfacts/CIK0000123456.json",
        filing_acceptance_at=datetime(2026, 2, 20, tzinfo=timezone.utc),
        last_updated=datetime(2026, 3, 21, tzinfo=timezone.utc),
        last_checked=datetime(2026, 3, 22, tzinfo=timezone.utc),
        data={
            "summary": {"total_debt": 100, "gross_shareholder_payout": 17},
            "debt_maturity_ladder": {"buckets": [{"bucket_key": "debt_maturity_due_next_twelve_months", "label": "Next 12 months", "amount": 10}], "meta": {"confidence_score": 1}},
            "lease_obligations": {"buckets": [], "meta": {"confidence_score": 0}},
            "debt_rollforward": {"debt_issued": 20, "debt_repaid": 8, "net_debt_change": 12, "meta": {"confidence_score": 1}},
            "interest_burden": {"interest_to_average_debt": 0.04, "meta": {"confidence_score": 1}},
            "capital_returns": {"dividends": 5, "share_repurchases": 12, "meta": {"confidence_score": 1}},
            "net_dilution_bridge": {"shares_issued": 5, "shares_repurchased": 2, "meta": {"confidence_score": 1}},
        },
        provenance={"formula_version": "capital_structure_v1", "official_source_id": "sec_companyfacts"},
        quality_flags=["debt_maturity_ladder_partial"],
        confidence_score=0.75,
    )

    payload = main_module._serialize_capital_structure_snapshot(snapshot)

    assert payload.summary.total_debt == 100
    assert payload.debt_rollforward.debt_issued == 20
    assert payload.capital_returns.share_repurchases == 12
    assert payload.net_dilution_bridge.shares_repurchased == 2
    assert payload.provenance_details["official_source_id"] == "sec_companyfacts"
