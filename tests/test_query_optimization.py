"""
Tests for query optimization refactoring.

Compares old Python-side filtering implementations with new SQL-based versions
to ensure correctness and performance improvements.
"""

from datetime import date, datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.models import (
    Company,
    DerivedMetricPoint,
    FinancialStatement,
    PriceHistory,
)
from app.services import cache_queries


@compiles(JSONB, "sqlite")
def _compile_jsonb_for_sqlite(_type, _compiler, **_kwargs):
    return "JSON"


@pytest.fixture
def db_session() -> Session:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    # DerivedMetricPoint uses PostgreSQL-specific jsonb defaults; swap them for SQLite DDL.
    derived_table = DerivedMetricPoint.__table__
    provenance_col = derived_table.c.provenance
    source_ids_col = derived_table.c.source_statement_ids
    quality_flags_col = derived_table.c.quality_flags
    original_defaults = (
        provenance_col.server_default,
        source_ids_col.server_default,
        quality_flags_col.server_default,
    )
    provenance_col.server_default = text("'{}'")
    source_ids_col.server_default = text("'[]'")
    quality_flags_col.server_default = text("'[]'")

    try:
        Base.metadata.create_all(
            engine,
            tables=[
                Company.__table__,
                PriceHistory.__table__,
                FinancialStatement.__table__,
                DerivedMetricPoint.__table__,
            ],
        )
    finally:
        provenance_col.server_default, source_ids_col.server_default, quality_flags_col.server_default = original_defaults

    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
    session = session_factory()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def test_company(db_session: Session) -> Company:
    """Create a test company."""
    company = Company(
        ticker="TEST",
        name="Test Company",
        cik="0000000001",
        sector="Technology",
        market_industry="Software",
    )
    db_session.add(company)
    db_session.flush()
    return company


@pytest.fixture
def price_history_data(db_session: Session, test_company: Company) -> list[PriceHistory]:
    """Create test price history data."""
    base_date = datetime(2026, 1, 1, tzinfo=timezone.utc)
    prices = []
    for i in range(100):
        trade_date = (base_date + timedelta(days=i)).date()
        price = PriceHistory(
            company_id=test_company.id,
            trade_date=trade_date,
            close=100.0 + i,
            volume=1000000,
            source="test",
            last_updated=base_date,
            fetch_timestamp=base_date,
            last_checked=base_date,
        )
        prices.append(price)
        db_session.add(price)
    db_session.flush()
    return prices


@pytest.fixture
def financial_statement_data(db_session: Session, test_company: Company) -> list[FinancialStatement]:
    """Create test financial statement data."""
    base_date = datetime(2026, 1, 1, tzinfo=timezone.utc)
    statements = []
    
    # Create annual statements for 3 years with different filing_acceptance_at times
    for year in range(2023, 2026):
        period_end = date(year, 12, 31)
        period_start = date(year, 1, 1)
        
        # Original filing
        stmt1 = FinancialStatement(
            company_id=test_company.id,
            period_start=period_start,
            period_end=period_end,
            filing_type="10-K",
            statement_type="canonical",
            data={"revenue": 1000000 * (year - 2022)},
            selected_facts={},
            reconciliation={},
            source="sec",
            last_updated=base_date + timedelta(days=year-2023),
            filing_acceptance_at=base_date + timedelta(days=year-2023),
            fetch_timestamp=base_date + timedelta(days=year-2023),
            last_checked=base_date + timedelta(days=year-2023),
        )
        statements.append(stmt1)
        db_session.add(stmt1)
        
        # Amendment with later filing_acceptance_at
        stmt2 = FinancialStatement(
            company_id=test_company.id,
            period_start=period_start,
            period_end=period_end,
            filing_type="10-K/A",
            statement_type="canonical",
            data={"revenue": 1000000 * (year - 2022) * 1.01},  # Amended value
            selected_facts={},
            reconciliation={},
            source="sec",
            last_updated=base_date + timedelta(days=year-2023+30),  # 30 days later
            filing_acceptance_at=base_date + timedelta(days=year-2023+30),
            fetch_timestamp=base_date + timedelta(days=year-2023+30),
            last_checked=base_date + timedelta(days=year-2023+30),
        )
        statements.append(stmt2)
        db_session.add(stmt2)
    
    db_session.flush()
    return statements


class TestPriceHistoryOptimization:
    """Tests for price history as_of filtering optimization."""

    def test_get_price_history_as_of_all_before_cutoff(
        self,
        db_session: Session,
        test_company: Company,
        price_history_data: list[PriceHistory],
    ) -> None:
        """Test fetching all price points before cutoff date."""
        as_of = datetime(2026, 2, 15, tzinfo=timezone.utc)
        
        # SQL-based version
        result = cache_queries.get_price_history_as_of(db_session, test_company.id, as_of)
        
        assert len(result) == 46  # Days from 1/1 to 2/15
        assert result[0].trade_date == date(2026, 1, 1)
        assert result[-1].trade_date == date(2026, 2, 15)

    def test_get_price_history_as_of_partial(
        self,
        db_session: Session,
        test_company: Company,
        price_history_data: list[PriceHistory],
    ) -> None:
        """Test fetching partial price history."""
        as_of = datetime(2026, 1, 20, tzinfo=timezone.utc)
        
        result = cache_queries.get_price_history_as_of(db_session, test_company.id, as_of)
        
        assert len(result) == 20
        assert result[-1].trade_date == date(2026, 1, 20)

    def test_get_latest_price_as_of(
        self,
        db_session: Session,
        test_company: Company,
        price_history_data: list[PriceHistory],
    ) -> None:
        """Test fetching the latest price point as of a date."""
        as_of = datetime(2026, 2, 15, tzinfo=timezone.utc)
        
        result = cache_queries.get_latest_price_as_of(db_session, test_company.id, as_of)
        
        assert result is not None
        assert result.trade_date == date(2026, 2, 15)
        assert result.close == pytest.approx(100.0 + 45)  # 45 days from 1/1

    def test_get_latest_price_as_of_no_data(
        self,
        db_session: Session,
    ) -> None:
        """Test fetching latest price when no data exists."""
        company = Company(
            ticker="EMPTY",
            name="Empty Company",
            cik="0000000002",
            sector="Technology",
            market_industry="Software",
        )
        db_session.add(company)
        db_session.flush()
        
        as_of = datetime(2026, 1, 1, tzinfo=timezone.utc)
        result = cache_queries.get_latest_price_as_of(db_session, company.id, as_of)
        
        assert result is None

    def test_python_filter_vs_sql_filter_consistency(
        self,
        db_session: Session,
        test_company: Company,
        price_history_data: list[PriceHistory],
    ) -> None:
        """Test that old Python filter and new SQL filter give same results."""
        as_of = datetime(2026, 2, 10, 23, 59, 59, 999999, tzinfo=timezone.utc)

        # Old Python-based approach
        python_result = cache_queries.filter_price_history_as_of(price_history_data, as_of)
        
        # New SQL-based approach
        sql_result = cache_queries.get_price_history_as_of(db_session, test_company.id, as_of)
        
        assert len(python_result) == len(sql_result)
        assert [p.trade_date for p in python_result] == [p.trade_date for p in sql_result]


class TestFinancialStatementOptimization:
    """Tests for financial statement as_of point-in-time filtering optimization."""

    def test_get_point_in_time_financials_basic(
        self,
        db_session: Session,
        test_company: Company,
        financial_statement_data: list[FinancialStatement],
    ) -> None:
        """Test fetching point-in-time financials."""
        # Query as_of before any amendments
        as_of = datetime(2026, 1, 15, tzinfo=timezone.utc)
        
        result = cache_queries.get_point_in_time_financials(
            db_session,
            test_company.id,
            "canonical",
            as_of,
        )
        
        # Should get the original filings (10-K) not the amendments (10-K/A)
        assert len(result) == 3  # One for each year
        assert all(stmt.filing_type == "10-K" for stmt in result)
        assert [stmt.period_end.year for stmt in result] == [2025, 2024, 2023]

    def test_get_point_in_time_financials_after_amendments(
        self,
        db_session: Session,
        test_company: Company,
        financial_statement_data: list[FinancialStatement],
    ) -> None:
        """Test fetching point-in-time financials after amendments."""
        # Query as_of after amendments are filed
        as_of = datetime(2026, 2, 15, tzinfo=timezone.utc)
        
        result = cache_queries.get_point_in_time_financials(
            db_session,
            test_company.id,
            "canonical",
            as_of,
        )
        
        # Point-in-time contract is one row per (period_end, filing_type), so both base and amendment survive.
        assert len(result) == 6
        assert {stmt.filing_type for stmt in result} == {"10-K", "10-K/A"}

    def test_get_point_in_time_financials_with_limit(
        self,
        db_session: Session,
        test_company: Company,
        financial_statement_data: list[FinancialStatement],
    ) -> None:
        """Test limit parameter for point-in-time financials."""
        as_of = datetime(2026, 2, 15, tzinfo=timezone.utc)
        
        result = cache_queries.get_point_in_time_financials(
            db_session,
            test_company.id,
            "canonical",
            as_of,
            limit=2,
        )
        
        assert len(result) == 2
        assert result[0].period_end.year == 2025  # Most recent first
        assert result[1].period_end.year == 2025

    def test_python_select_vs_sql_select_consistency(
        self,
        db_session: Session,
        test_company: Company,
        financial_statement_data: list[FinancialStatement],
    ) -> None:
        """Test that old Python select and new SQL select give same results."""
        as_of = datetime(2026, 2, 15, tzinfo=timezone.utc)
        
        # Old Python-based approach
        python_result = cache_queries.select_point_in_time_financials(
            financial_statement_data,
            as_of,
        )
        
        # New SQL-based approach
        sql_result = cache_queries.get_point_in_time_financials(
            db_session,
            test_company.id,
            "canonical",
            as_of,
        )
        
        assert len(python_result) == len(sql_result)
        assert {stmt.period_end for stmt in python_result} == {stmt.period_end for stmt in sql_result}
        assert {stmt.filing_type for stmt in python_result} == {stmt.filing_type for stmt in sql_result}


class TestDerivedMetricsOptimization:
    """Tests for derived metrics queries."""

    def test_get_company_derived_metric_points_limit(
        self,
        db_session: Session,
        test_company: Company,
    ) -> None:
        """Test that derived metrics query respects max_periods limit."""
        base_date = datetime(2026, 1, 1, tzinfo=timezone.utc)
        
        # Create 50 derived metric points
        for i in range(50):
            point = DerivedMetricPoint(
                company_id=test_company.id,
                period_start=date(2026, 1, 1),
                period_end=date(2026, 1, 1) + timedelta(days=i),
                period_type="quarterly",
                filing_type="10-Q",
                metric_key="revenue_growth",
                metric_value=float(i),
                metric_date=date(2026, 1, 1) + timedelta(days=i),
                provenance={},
                source_statement_ids=[],
                quality_flags=[],
                last_updated=base_date,
                last_checked=base_date,
            )
            db_session.add(point)
        db_session.flush()
        
        result = cache_queries.get_company_derived_metric_points(
            db_session,
            test_company.id,
            max_periods=12,
        )
        
        # Should get at most 24 points (max_periods * num_metrics)
        # but we only have one metric, so we get 12
        assert len(result) <= 12

    def test_get_company_derived_metric_points_with_period_type_filter(
        self,
        db_session: Session,
        test_company: Company,
    ) -> None:
        """Test filtering derived metrics by period_type."""
        base_date = datetime(2026, 1, 1, tzinfo=timezone.utc)
        
        # Create quarterly and annual metrics
        for i in range(10):
            for period_type in ["quarterly", "annual"]:
                point = DerivedMetricPoint(
                    company_id=test_company.id,
                    period_start=date(2026, 1, 1),
                    period_end=date(2026, 1, 1) + timedelta(days=i*90 if period_type == "annual" else i*30),
                    period_type=period_type,
                    filing_type="10-Q" if period_type == "quarterly" else "10-K",
                    metric_key="revenue_growth",
                    metric_value=float(i),
                    metric_date=date(2026, 1, 1) + timedelta(days=i*90 if period_type == "annual" else i*30),
                    provenance={},
                    source_statement_ids=[],
                    quality_flags=[],
                    last_updated=base_date,
                    last_checked=base_date,
                )
                db_session.add(point)
        db_session.flush()
        
        quarterly_result = cache_queries.get_company_derived_metric_points(
            db_session,
            test_company.id,
            period_type="quarterly",
            max_periods=24,
        )
        
        assert all(p.period_type == "quarterly" for p in quarterly_result)
        assert len(quarterly_result) > 0

    def test_batch_derived_metric_points_preserves_per_company_period_limits(
        self,
        db_session: Session,
        test_company: Company,
    ) -> None:
        """Batch metric loading should avoid per-company fan-out while preserving row grouping."""
        second_company = Company(
            ticker="BATCH",
            name="Batch Company",
            cik="0000000002",
            sector="Technology",
            market_industry="Software",
        )
        db_session.add(second_company)
        db_session.flush()
        base_date = datetime(2026, 1, 1, tzinfo=timezone.utc)

        for company in [test_company, second_company]:
            for i in range(4):
                for metric_key in ["revenue_growth", "operating_margin"]:
                    period_end = date(2026, 1, 1) + timedelta(days=i)
                    db_session.add(
                        DerivedMetricPoint(
                            company_id=company.id,
                            period_start=date(2026, 1, 1),
                            period_end=period_end,
                            period_type="ttm",
                            filing_type="TTM",
                            metric_key=metric_key,
                            metric_value=float(i),
                            metric_date=period_end,
                            provenance={},
                            source_statement_ids=[],
                            quality_flags=[],
                            last_updated=base_date,
                            last_checked=base_date,
                        )
                    )
        db_session.flush()

        result = cache_queries.get_company_derived_metric_points_by_company_ids(
            db_session,
            [test_company.id, second_company.id],
            period_type="ttm",
            max_periods=2,
        )

        assert set(result) == {test_company.id, second_company.id}
        assert {point.company_id for rows in result.values() for point in rows} == {test_company.id, second_company.id}
        assert all(len({point.period_end for point in rows}) == 2 for rows in result.values())
        assert all(len(rows) == 4 for rows in result.values())

    def test_batch_price_history_groups_by_company(
        self,
        db_session: Session,
        test_company: Company,
    ) -> None:
        second_company = Company(
            ticker="PRICEB",
            name="Price Batch Company",
            cik="0000000003",
            sector="Technology",
            market_industry="Software",
        )
        db_session.add(second_company)
        db_session.flush()
        base_date = datetime(2026, 1, 1, tzinfo=timezone.utc)

        for company in [test_company, second_company]:
            for i in range(3):
                db_session.add(
                    PriceHistory(
                        company_id=company.id,
                        trade_date=date(2026, 1, 1) + timedelta(days=i),
                        close=100.0 + i,
                        volume=1000 + i,
                        source="test",
                        last_updated=base_date,
                        fetch_timestamp=base_date,
                        last_checked=base_date,
                    )
                )
        db_session.flush()

        result = cache_queries.get_company_price_history_by_company_ids(
            db_session,
            [test_company.id, second_company.id],
        )

        assert [point.trade_date for point in result[test_company.id]] == [
            date(2026, 1, 1),
            date(2026, 1, 2),
            date(2026, 1, 3),
        ]
        assert len(result[second_company.id]) == 3


@pytest.mark.integration
class TestQueryPerformance:
    """Integration tests to verify query performance improvements."""

    def test_price_history_uses_index(
        self,
        db_session: Session,
        test_company: Company,
        price_history_data: list[PriceHistory],
    ) -> None:
        """Verify that price history queries use the optimized index."""
        as_of = datetime(2026, 2, 10, tzinfo=timezone.utc)
        
        # This should use ix_price_history_company_trade_date_desc
        result = cache_queries.get_latest_price_as_of(db_session, test_company.id, as_of)
        
        assert result is not None
        assert result.trade_date == date(2026, 2, 10)

    def test_financial_statements_uses_index(
        self,
        db_session: Session,
        test_company: Company,
        financial_statement_data: list[FinancialStatement],
    ) -> None:
        """Verify that financial statement queries use the optimized index."""
        as_of = datetime(2026, 2, 15, tzinfo=timezone.utc)
        
        # This should use ix_financial_statements_company_period_end_desc
        result = cache_queries.get_point_in_time_financials(
            db_session,
            test_company.id,
            "canonical",
            as_of,
        )
        
        assert len(result) == 6
        assert result[0].period_end == date(2025, 12, 31)
