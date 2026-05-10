"""Tests for SEC bulk archive ingestion service."""

from __future__ import annotations

import json
import tempfile
import zipfile
from datetime import date
from pathlib import Path

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from app.models import Company, FilingEvent
from app.services.sec.bulk_ingest import BulkArchiveIngester, bulk_ingest_main


def _create_test_db_session() -> Session:
    """Create an in-memory SQLite test database session."""
    from sqlalchemy import MetaData, Table, Column, Integer, String, Date, DateTime, ForeignKey, Text
    
    # Use SQLite in-memory database for fast tests
    engine = create_engine("sqlite:///:memory:")
    
    # Create only the tables we need for testing
    metadata = MetaData()
    
    companies = Table(
        'companies',
        metadata,
        Column('id', Integer, primary_key=True),
        Column('ticker', String(16), nullable=False, unique=True),
        Column('cik', String(20), nullable=False, unique=True),
        Column('name', String(255), nullable=False),
        Column('sector', String(100), nullable=True),
        Column('market_sector', String(100), nullable=True),
        Column('market_industry', String(150), nullable=True),
    )
    
    filing_events = Table(
        'filing_events',
        metadata,
        Column('id', Integer, primary_key=True),
        Column('company_id', Integer, ForeignKey('companies.id', ondelete='CASCADE'), nullable=False),
        Column('accession_number', String(32), nullable=False),
        Column('form', String(16), nullable=False),
        Column('filing_date', Date, nullable=True),
        Column('report_date', Date, nullable=True),
        Column('items', String(128), nullable=True),
        Column('item_code', String(16), nullable=False),
        Column('category', String(64), nullable=False),
        Column('primary_document', String(255), nullable=True),
        Column('primary_doc_description', String(500), nullable=True),
        Column('source_url', String(500), nullable=False),
        Column('summary', String(500), nullable=False),
        Column('key_amounts', String(512), nullable=False, default='[]'),  # JSON as string
        Column('exhibit_references', String(512), nullable=False, default='[]'),  # JSON as string
        Column('last_updated', DateTime, nullable=False),
        Column('last_checked', DateTime, nullable=False),
    )
    
    dataset_refresh_state = Table(
        'dataset_refresh_state',
        metadata,
        Column('id', Integer, primary_key=True),
        Column('company_id', Integer, ForeignKey('companies.id', ondelete='CASCADE'), nullable=False),
        Column('dataset', String(64), nullable=False),
        Column('last_checked', DateTime, nullable=False),
        Column('last_success', DateTime, nullable=True),
        Column('freshness_deadline', DateTime, nullable=True),
        Column('active_job_id', String(64), nullable=True),
        Column('failure_count', Integer, nullable=False, default=0),
        Column('last_error', Text, nullable=True),
        Column('payload_version_hash', String(64), nullable=True),
        Column('updated_at', DateTime, nullable=False),
    )
    
    metadata.create_all(engine)
    
    SessionLocal = sessionmaker(bind=engine)
    return SessionLocal()


@pytest.fixture
def sample_companyfacts_zip() -> Path:
    """Create a minimal companyfacts.zip for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir_path = Path(tmpdir)
        zip_path = tmpdir_path / "companyfacts_test.zip"

        # Create minimal company facts data
        companyfacts = {
            "cik_str": 1018724,
            "entityName": "AMAZON COM INC",
            "units": {
                "USD": [
                    {
                        "end": "2023-12-31",
                        "val": 575000000000,
                        "accn": "0001018724-24-000012",
                        "fy": 2023,
                        "fp": "FY",
                        "form": "10-K",
                        "filed": "2024-01-30",
                    }
                ]
            },
            "facts": {
                "us-gaap": {
                    "Assets": {
                        "label": "Assets",
                        "description": "Sum of the carrying amounts of all assets",
                        "units": {
                            "USD": [
                                {
                                    "end": "2023-12-31",
                                    "val": 462099000000,
                                    "accn": "0001018724-24-000012",
                                    "fy": 2023,
                                    "fp": "FY",
                                    "form": "10-K",
                                    "filed": "2024-01-30",
                                }
                            ]
                        },
                    },
                    "Revenues": {
                        "label": "Revenues",
                        "description": "Revenues",
                        "units": {
                            "USD": [
                                {
                                    "end": "2023-12-31",
                                    "val": 574785000000,
                                    "accn": "0001018724-24-000012",
                                    "fy": 2023,
                                    "fp": "FY",
                                    "form": "10-K",
                                    "filed": "2024-01-30",
                                }
                            ]
                        },
                    },
                }
            },
        }

        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("CIK0001018724.json", json.dumps(companyfacts))

        # Copy to fixtures directory
        output_path = Path(__file__).parent / "fixtures" / "sec_bulk_archives" / "companyfacts_test.zip"
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(zip_path, "rb") as src:
            with open(output_path, "wb") as dst:
                dst.write(src.read())

        yield output_path


@pytest.fixture
def sample_submissions_zip() -> Path:
    """Create a minimal submissions.zip for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir_path = Path(tmpdir)
        zip_path = tmpdir_path / "submissions_test.zip"

        # Create minimal submissions data
        submissions = {
            "cik_str": 1018724,
            "entityName": "AMAZON COM INC",
            "filings": {
                "recent": [
                    {
                        "accession": "0001018724-24-000012",
                        "form": "10-K",
                        "filingDate": "2024-01-30",
                        "reportDate": "2023-12-31",
                        "acceptanceDateTime": "2024-01-30T13:00:00",
                        "act": "34",
                        "fileNumber": "001-31092",
                        "filmNumber": "24000062",
                    },
                    {
                        "accession": "0001018724-23-000033",
                        "form": "10-Q",
                        "filingDate": "2023-10-27",
                        "reportDate": "2023-09-30",
                        "acceptanceDateTime": "2023-10-27T13:00:00",
                        "act": "34",
                        "fileNumber": "001-31092",
                        "filmNumber": "23021282",
                    },
                ]
            },
        }

        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("CIK0001018724.json", json.dumps(submissions))

        # Copy to fixtures directory
        output_path = Path(__file__).parent / "fixtures" / "sec_bulk_archives" / "submissions_test.zip"
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(zip_path, "rb") as src:
            with open(output_path, "wb") as dst:
                dst.write(src.read())

        yield output_path


@pytest.fixture
def db_session() -> Session:
    """Create a test database session."""
    return _create_test_db_session()


@pytest.fixture
def bulk_ingester(db_session: Session) -> BulkArchiveIngester:
    """Create a BulkArchiveIngester instance."""
    return BulkArchiveIngester(db_session)


class TestBulkCompanyFactsIngestion:
    """Test company facts bulk ingestion."""

    def test_ingest_companyfacts_missing_file(self, bulk_ingester: BulkArchiveIngester) -> None:
        """Test that missing archive raises FileNotFoundError."""
        with pytest.raises(FileNotFoundError):
            bulk_ingester.ingest_companyfacts("/nonexistent/path/companyfacts.zip")

    def test_ingest_companyfacts_returns_stats(
        self, bulk_ingester: BulkArchiveIngester, sample_companyfacts_zip: Path
    ) -> None:
        """Test that companyfacts ingestion returns statistics."""
        result = bulk_ingester.ingest_companyfacts(sample_companyfacts_zip)

        assert "archive_path" in result
        assert "total_files" in result
        assert "files_processed" in result
        assert "started_at" in result
        assert "completed_at" in result
        assert "success" in result
        assert result["success"] is True
        assert result["total_files"] == 1


class TestBulkSubmissionsIngestion:
    """Test submissions bulk ingestion."""

    def test_ingest_submissions_missing_file(self, bulk_ingester: BulkArchiveIngester) -> None:
        """Test that missing archive raises FileNotFoundError."""
        with pytest.raises(FileNotFoundError):
            bulk_ingester.ingest_submissions("/nonexistent/path/submissions.zip")

    def test_ingest_submissions_creates_company(
        self, db_session: Session, bulk_ingester: BulkArchiveIngester, sample_submissions_zip: Path
    ) -> None:
        """Test that submissions ingestion creates company if not exists."""
        # Verify company doesn't exist yet
        company = db_session.execute(
            select(Company).where(Company.cik == "0001018724")
        ).scalar_one_or_none()
        assert company is None

        result = bulk_ingester.ingest_submissions(sample_submissions_zip)
        assert result["success"] is True

        # Verify company was created
        company = db_session.execute(
            select(Company).where(Company.cik == "0001018724")
        ).scalar_one_or_none()
        assert company is not None
        assert company.name == "AMAZON COM INC"

    def test_ingest_submissions_upserts_filings(
        self, db_session: Session, bulk_ingester: BulkArchiveIngester, sample_submissions_zip: Path
    ) -> None:
        """Test that submissions ingestion creates filing events."""
        result = bulk_ingester.ingest_submissions(sample_submissions_zip)
        assert result["success"] is True
        assert result["filings_upserted"] == 2

        # Verify filings were created
        filings = db_session.execute(select(FilingEvent)).scalars().all()
        assert len(filings) == 2

        # Verify filing details
        filing_forms = {f.form for f in filings}
        assert "10-K" in filing_forms
        assert "10-Q" in filing_forms

    def test_ingest_submissions_idempotent(
        self, db_session: Session, bulk_ingester: BulkArchiveIngester, sample_submissions_zip: Path
    ) -> None:
        """Test that re-ingesting the same submissions is idempotent."""
        # First ingest
        result1 = bulk_ingester.ingest_submissions(sample_submissions_zip)
        assert result1["filings_upserted"] == 2

        # Second ingest
        result2 = bulk_ingester.ingest_submissions(sample_submissions_zip)
        assert result2["filings_upserted"] == 2

        # Verify only 2 filings exist (not 4)
        filings = db_session.execute(select(FilingEvent)).scalars().all()
        assert len(filings) == 2


class TestBulkIngestCLI:
    """Test the CLI interface for bulk ingestion."""

    def test_bulk_ingest_cli_no_args(self) -> None:
        """Test that CLI returns 1 when no arguments provided."""
        result = bulk_ingest_main([])
        assert result == 1

    def test_bulk_ingest_cli_help_exits(self) -> None:
        """Test that CLI help causes SystemExit."""
        with pytest.raises(SystemExit) as exc_info:
            bulk_ingest_main(["--help"])
        assert exc_info.value.code == 0


class TestSubmissionsFilingParsing:
    """Test the filing event parsing logic."""

    def test_filing_date_parsing(self, db_session: Session, bulk_ingester: BulkArchiveIngester) -> None:
        """Test that filing dates are parsed correctly."""
        # Create a test company
        company = Company(ticker="TEST", cik="0000000001", name="Test Company")
        db_session.add(company)
        db_session.flush()

        # Create test filings with dates
        filings = [
            {
                "accession": "0000000001-24-000001",
                "form": "10-K",
                "filingDate": "2024-01-30",
                "reportDate": "2023-12-31",
            }
        ]

        count = bulk_ingester._upsert_filing_events(company, filings)
        assert count == 1

        # Verify the filing was created with correct dates
        filing = db_session.execute(
            select(FilingEvent).where(FilingEvent.accession_number == "0000000001-24-000001")
        ).scalar_one_or_none()
        assert filing is not None
        assert filing.filing_date == date(2024, 1, 30)
        assert filing.report_date == date(2023, 12, 31)

    def test_filing_with_missing_dates(self, db_session: Session, bulk_ingester: BulkArchiveIngester) -> None:
        """Test that filings with missing dates are still created."""
        company = Company(ticker="TEST", cik="0000000001", name="Test Company")
        db_session.add(company)
        db_session.flush()

        filings = [
            {
                "accession": "0000000001-24-000001",
                "form": "10-K",
                "filingDate": None,
                "reportDate": None,
            }
        ]

        count = bulk_ingester._upsert_filing_events(company, filings)
        assert count == 1

        filing = db_session.execute(
            select(FilingEvent).where(FilingEvent.accession_number == "0000000001-24-000001")
        ).scalar_one_or_none()
        assert filing is not None
        assert filing.filing_date is None
        assert filing.report_date is None

    def test_filing_upsert_updates_existing(
        self, db_session: Session, bulk_ingester: BulkArchiveIngester
    ) -> None:
        """Test that upserting updates existing filings."""
        company = Company(ticker="TEST", cik="0000000001", name="Test Company")
        db_session.add(company)
        db_session.flush()

        # Create initial filing
        filings = [
            {
                "accession": "0000000001-24-000001",
                "form": "10-K",
                "filingDate": "2024-01-30",
                "reportDate": "2023-12-31",
            }
        ]
        bulk_ingester._upsert_filing_events(company, filings)

        # Upsert with updated form (different form type)
        filings = [
            {
                "accession": "0000000001-24-000001",
                "form": "10-Q",  # Changed from 10-K
                "filingDate": "2024-01-30",
                "reportDate": "2023-12-31",
            }
        ]
        bulk_ingester._upsert_filing_events(company, filings)

        # Verify only one filing exists and form was updated
        filings_in_db = db_session.execute(
            select(FilingEvent).where(FilingEvent.company_id == company.id)
        ).scalars().all()
        assert len(filings_in_db) == 1
        assert filings_in_db[0].form == "10-Q"
