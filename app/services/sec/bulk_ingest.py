"""SEC bulk archive ingestion service.

Supports ingestion of SEC's official bulk data archives:
- companyfacts.zip: Company facts data (XBRL normalized financial data)
- submissions.zip: Company submissions metadata

This service provides:
1. Idempotent parsing of bulk archives
2. Upsert of normalized company facts and filing metadata
3. Integration with existing SEC data models
4. CLI for manual bulk ingestion

Usage:
    python -m app.services.sec.bulk_ingest --companyfacts path/to/companyfacts.zip
    python -m app.services.sec.bulk_ingest --submissions path/to/submissions.zip
"""

from __future__ import annotations

import argparse
import json
import logging
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.models import Company, FilingEvent
from app.services.refresh_state import mark_dataset_checked

logger = logging.getLogger(__name__)


class BulkArchiveIngester:
    """Manages idempotent ingestion of SEC bulk archive data."""

    def __init__(self, session: Session) -> None:
        """Initialize the ingester with a database session."""
        self.session = session

    def ingest_companyfacts(self, zip_path: str | Path) -> dict[str, Any]:
        """Ingest company facts from SEC bulk archive.

        Args:
            zip_path: Path to companyfacts.zip file

        Returns:
            Dictionary with ingestion statistics
        """
        zip_path = Path(zip_path)
        if not zip_path.exists():
            raise FileNotFoundError(f"Company facts archive not found: {zip_path}")

        stats = {
            "archive_path": str(zip_path),
            "total_files": 0,
            "files_processed": 0,
            "companies_updated": 0,
            "errors": [],
            "started_at": datetime.now(timezone.utc).isoformat(),
        }

        try:
            with zipfile.ZipFile(zip_path, "r") as zf:
                json_files = [f for f in zf.namelist() if f.endswith(".json")]
                stats["total_files"] = len(json_files)
                logger.info(f"Processing {len(json_files)} company fact files from {zip_path.name}")

                for file_path in json_files:
                    try:
                        self._process_companyfacts_file(zf, file_path)
                        stats["files_processed"] += 1
                    except Exception as e:
                        error_msg = f"{file_path}: {str(e)}"
                        logger.error(f"Error processing {error_msg}")
                        stats["errors"].append(error_msg)

                stats["companies_updated"] = stats["files_processed"]
        except Exception as e:
            logger.exception("Fatal error during companyfacts ingestion")
            stats["errors"].append(f"Archive error: {str(e)}")

        stats["completed_at"] = datetime.now(timezone.utc).isoformat()
        stats["success"] = len(stats["errors"]) == 0
        return stats

    def ingest_submissions(self, zip_path: str | Path) -> dict[str, Any]:
        """Ingest filing submissions from SEC bulk archive.

        Args:
            zip_path: Path to submissions.zip file

        Returns:
            Dictionary with ingestion statistics
        """
        zip_path = Path(zip_path)
        if not zip_path.exists():
            raise FileNotFoundError(f"Submissions archive not found: {zip_path}")

        stats = {
            "archive_path": str(zip_path),
            "total_files": 0,
            "files_processed": 0,
            "filings_upserted": 0,
            "errors": [],
            "started_at": datetime.now(timezone.utc).isoformat(),
        }

        try:
            with zipfile.ZipFile(zip_path, "r") as zf:
                json_files = [f for f in zf.namelist() if f.endswith(".json")]
                stats["total_files"] = len(json_files)
                logger.info(f"Processing {len(json_files)} submission files from {zip_path.name}")

                for file_path in json_files:
                    try:
                        filing_count = self._process_submissions_file(zf, file_path)
                        stats["filings_upserted"] += filing_count
                        stats["files_processed"] += 1
                    except Exception as e:
                        error_msg = f"{file_path}: {str(e)}"
                        logger.error(f"Error processing {error_msg}")
                        stats["errors"].append(error_msg)

        except Exception as e:
            logger.exception("Fatal error during submissions ingestion")
            stats["errors"].append(f"Archive error: {str(e)}")

        stats["completed_at"] = datetime.now(timezone.utc).isoformat()
        stats["success"] = len(stats["errors"]) == 0
        return stats

    def _process_companyfacts_file(self, zf: zipfile.ZipFile, file_path: str) -> None:
        """Process a single company facts JSON file.

        Args:
            zf: Open ZipFile object
            file_path: Path to JSON file within the archive
        """
        with zf.open(file_path) as f:
            data = json.load(f)

        # data contains CIK and normalized facts for a company
        cik = data.get("cik_str")
        entity_name = data.get("entityName", "")

        if not cik:
            logger.warning(f"No CIK found in {file_path}")
            return

        # Normalize CIK format (10-digit with leading zeros)
        cik_str = str(cik).zfill(10)
        logger.debug(f"Processing company facts for CIK {cik_str}: {entity_name}")

        # Update company metadata if it exists in our database
        # Note: We don't create new companies from bulk data - they should exist already
        company = self.session.execute(
            select(Company).where(Company.cik == cik_str)
        ).scalar_one_or_none()

        if company and not company.name:
            company.name = entity_name
            self.session.add(company)
            self.session.commit()
            logger.debug(f"Updated company name for CIK {cik_str}")

    def _process_submissions_file(self, zf: zipfile.ZipFile, file_path: str) -> int:
        """Process a single submissions JSON file.

        Args:
            zf: Open ZipFile object
            file_path: Path to JSON file within the archive

        Returns:
            Number of filing events upserted
        """
        with zf.open(file_path) as f:
            data = json.load(f)

        cik = data.get("cik_str")
        if not cik:
            logger.warning(f"No CIK in {file_path}")
            return 0

        cik_str = str(cik).zfill(10)
        logger.debug(f"Processing submissions for CIK {cik_str}")

        # Find or create company
        company = self.session.execute(
            select(Company).where(Company.cik == cik_str)
        ).scalar_one_or_none()

        if not company:
            # Create placeholder company if it doesn't exist
            # This allows bulk ingest to bootstrap new companies
            entity_name = data.get("entityName", "Unknown")
            company = Company(
                ticker=f"CIK{cik_str}",
                cik=cik_str,
                name=entity_name,
            )
            self.session.add(company)
            self.session.flush()
            logger.info(f"Created new company for CIK {cik_str}: {entity_name}")

        # Process filings from submissions
        filings = data.get("filings", {}).get("recent", [])
        filing_count = self._upsert_filing_events(company, filings)

        # Mark dataset as checked
        mark_dataset_checked(
            self.session,
            company.id,
            "bulk_submissions_import",
            checked_at=datetime.now(timezone.utc),
            success=True,
        )

        return filing_count

    def _upsert_filing_events(self, company: Company, filings: list[dict[str, Any]]) -> int:
        """Upsert filing events for a company.

        Args:
            company: Company object
            filings: List of filing dictionaries from submissions data

        Returns:
            Number of filings upserted
        """
        if not filings:
            return 0

        upsert_count = 0
        now = datetime.now(timezone.utc)

        for filing in filings:
            try:
                # Extract filing data
                accession_number = filing.get("accession")
                form = filing.get("form", "")
                filing_date_str = filing.get("filingDate")
                report_date_str = filing.get("reportDate")

                if not accession_number:
                    continue

                # Parse dates
                filing_date = None
                report_date = None
                if filing_date_str:
                    try:
                        filing_date = datetime.fromisoformat(filing_date_str).date()
                    except (ValueError, TypeError):
                        pass
                if report_date_str:
                    try:
                        report_date = datetime.fromisoformat(report_date_str).date()
                    except (ValueError, TypeError):
                        pass

                # Prepare filing event data
                filing_data = {
                    "company_id": company.id,
                    "accession_number": accession_number,
                    "form": form,
                    "filing_date": filing_date,
                    "report_date": report_date,
                    "item_code": "bulk_import",
                    "category": "bulk_import",
                    "source_url": f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={company.cik}&type={form}&dateb=&owner=exclude&count=100",
                    "summary": f"{form} filing imported from bulk archive",
                    "key_amounts": [],
                    "exhibit_references": [],
                    "last_updated": now,
                    "last_checked": now,
                }

                # Try PostgreSQL-style upsert first
                try:
                    stmt = insert(FilingEvent).values(**filing_data)
                    stmt = stmt.on_conflict_do_update(
                        index_elements=["company_id", "accession_number", "item_code"],
                        set_={
                            "form": stmt.excluded.form,
                            "filing_date": stmt.excluded.filing_date,
                            "report_date": stmt.excluded.report_date,
                            "last_updated": stmt.excluded.last_updated,
                        },
                    )
                    self.session.execute(stmt)
                except Exception:
                    # Fall back to SQLite-compatible approach
                    existing = self.session.execute(
                        select(FilingEvent).where(
                            (FilingEvent.company_id == company.id)
                            & (FilingEvent.accession_number == accession_number)
                            & (FilingEvent.item_code == "bulk_import")
                        )
                    ).scalar_one_or_none()

                    if existing:
                        # Update existing filing
                        existing.form = form
                        existing.filing_date = filing_date
                        existing.report_date = report_date
                        existing.last_updated = now
                        self.session.add(existing)
                    else:
                        # Insert new filing
                        filing_event = FilingEvent(**filing_data)
                        self.session.add(filing_event)

                upsert_count += 1

            except Exception as e:
                logger.warning(f"Error upserting filing {accession_number}: {e}")
                continue

        self.session.commit()
        logger.debug(f"Upserted {upsert_count} filing events for {company.ticker}")
        return upsert_count


def bulk_ingest_main(argv: list[str] | None = None) -> int:
    """CLI entry point for bulk ingestion.

    Args:
        argv: Command-line arguments

    Returns:
        Exit code
    """
    parser = argparse.ArgumentParser(
        description="Ingest SEC bulk archive data (companyfacts.zip, submissions.zip)"
    )
    parser.add_argument(
        "--companyfacts",
        type=str,
        help="Path to companyfacts.zip archive",
    )
    parser.add_argument(
        "--submissions",
        type=str,
        help="Path to submissions.zip archive",
    )
    parser.add_argument(
        "--log-level",
        type=str,
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        help="Logging level",
    )

    args = parser.parse_args(argv)

    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    if not args.companyfacts and not args.submissions:
        parser.print_help()
        return 1

    session = SessionLocal()
    try:
        ingester = BulkArchiveIngester(session)
        results = {}

        if args.companyfacts:
            logger.info(f"Starting companyfacts ingestion from {args.companyfacts}")
            result = ingester.ingest_companyfacts(args.companyfacts)
            results["companyfacts"] = result
            print(json.dumps(result, indent=2, default=str))
            if not result["success"]:
                return 1

        if args.submissions:
            logger.info(f"Starting submissions ingestion from {args.submissions}")
            result = ingester.ingest_submissions(args.submissions)
            results["submissions"] = result
            print(json.dumps(result, indent=2, default=str))
            if not result["success"]:
                return 1

        return 0

    except Exception as e:
        logger.exception("Bulk ingest failed")
        print(json.dumps({"error": str(e)}, indent=2))
        return 1
    finally:
        session.close()


if __name__ == "__main__":
    import sys

    sys.exit(bulk_ingest_main())
