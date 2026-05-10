# SEC Bulk Archive Ingestion

## Overview

The SEC bulk archive ingestion service provides idempotent, official-source-first import of SEC's bulk data archives:

- **companyfacts.zip**: Normalized XBRL financial facts data across all public companies
- **submissions.zip**: Filing submission metadata (forms, dates, accession numbers)

This service is designed for:
- **Bootstrapping** new company databases
- **Periodic bulk refreshes** of filing metadata
- **Archival ingestion** from SEC's historical bulk data

## When to Use Bulk Ingest vs Live SEC Fetches

### Use Bulk Ingest When:

1. **Initializing a new environment**: Load all historical SEC data at once from official archives
2. **Catching up after downtime**: Restore missing filing metadata without live API calls
3. **Offline ingestion**: Import pre-downloaded archives without external network calls
4. **Batch operations**: Bulk-import thousands of companies efficiently
5. **Testing/Development**: Load fixture data without external dependencies

### Use Live SEC Fetches When:

1. **Real-time updates**: Need the latest filings immediately after SEC publication
2. **Single company refresh**: Refreshing data for one or a few specific companies
3. **Incremental updates**: Regular scheduled updates for maintained companies
4. **Fresh fact data**: Need the latest XBRL facts parsed and stored
5. **Production workflows**: Live SEC API calls for production refresh orchestration

## Architecture

### BulkArchiveIngester Class

Manages idempotent ingestion of bulk archive data:

```python
from app.services.sec.bulk_ingest import BulkArchiveIngester
from app.db.session import SessionLocal

session = SessionLocal()
ingester = BulkArchiveIngester(session)

# Ingest companyfacts data
result = ingester.ingest_companyfacts("/path/to/companyfacts.zip")

# Ingest submissions metadata
result = ingester.ingest_submissions("/path/to/submissions.zip")
```

### Key Features

1. **Idempotent Upserts**: Re-ingesting the same archive produces identical results
2. **Official Data Only**: Uses SEC's authoritative bulk archives as the source
3. **Partial Failure Handling**: Continues processing if individual files encounter errors
4. **Audit Trail**: Tracks ingestion source and method via `bulk_import` dataset markers
5. **No Network Calls**: All data comes from local archive files

## Usage

### CLI Commands

Ingest company facts:
```bash
python -m app.services.sec.bulk_ingest --companyfacts /path/to/companyfacts.zip
```

Ingest submissions:
```bash
python -m app.services.sec.bulk_ingest --submissions /path/to/submissions.zip
```

Both archives at once:
```bash
python -m app.services.sec.bulk_ingest \
  --companyfacts /path/to/companyfacts.zip \
  --submissions /path/to/submissions.zip
```

Enable debug logging:
```bash
python -m app.services.sec.bulk_ingest \
  --submissions /path/to/submissions.zip \
  --log-level DEBUG
```

### Programmatic Usage

```python
from app.services.sec.bulk_ingest import BulkArchiveIngester
from app.db.session import SessionLocal

session = SessionLocal()
ingester = BulkArchiveIngester(session)

# Ingest company facts
stats = ingester.ingest_companyfacts("companyfacts.zip")
print(f"Processed {stats['files_processed']} files")
print(f"Success: {stats['success']}")

if stats['errors']:
    for error in stats['errors']:
        print(f"Error: {error}")
```

## Data Structures

### companyfacts.zip Format

Each JSON file contains:
```json
{
  "cik_str": 1018724,
  "entityName": "AMAZON COM INC",
  "facts": {
    "us-gaap": {
      "Assets": {
        "label": "Assets",
        "description": "...",
        "units": {
          "USD": [
            {
              "end": "2023-12-31",
              "val": 462099000000,
              "accn": "0001018724-24-000012",
              "fy": 2023,
              "fp": "FY",
              "form": "10-K",
              "filed": "2024-01-30"
            }
          ]
        }
      }
    }
  }
}
```

### submissions.zip Format

Each JSON file contains:
```json
{
  "cik_str": 1018724,
  "entityName": "AMAZON COM INC",
  "filings": {
    "recent": [
      {
        "accession": "0001018724-24-000012",
        "form": "10-K",
        "filingDate": "2024-01-30",
        "reportDate": "2023-12-31",
        "acceptanceDateTime": "2024-01-30T13:00:00"
      }
    ]
  }
}
```

## Ingestion Behavior

### Company Facts Ingestion

1. Reads JSON files from companyfacts.zip
2. Extracts CIK and company name
3. Updates existing company metadata if company already exists in database
4. Stores XBRL facts in normalized form
5. Continues processing if individual files fail

### Submissions Ingestion

1. Reads JSON files from submissions.zip
2. Extracts CIK and filing metadata
3. Creates company record if it doesn't exist (with placeholder ticker `CIK{cik}`)
4. Upserts filing events using PostgreSQL INSERT ... ON CONFLICT
5. Marks dataset as checked via refresh state tracking
6. Returns count of filings upserted

### Idempotency

- **Company Facts**: Updates existing company name if not set; no duplicates possible
- **Filing Events**: Uses unique constraint on `(company_id, accession_number, item_code)` to prevent duplicates
- **Re-ingestion**: Running the same ingest twice produces identical final database state

## Database Impact

### Tables Modified

- `companies`: Company name updates if not already set
- `filing_events`: Upserts filings via ON CONFLICT clauses
- `dataset_refresh_states`: Marks dataset as checked after completion

### Provenance Tracking

Each upserted filing is marked with:
- `item_code = "bulk_import"`: Indicates bulk archive source
- `category = "bulk_import"`: Classifies as bulk-imported data
- `source_url`: Links to SEC EDGAR search for the company
- `last_updated`: Timestamp of ingestion

## Error Handling

### Archive Errors

- Missing archive file → `FileNotFoundError` with clear path
- Corrupted ZIP → Exception with archive error message
- Invalid JSON → Warning log, continue to next file

### Data Errors

- Missing CIK in file → Warning log, skip file
- Invalid date format → Coerce to None, continue
- Duplicate accession → Update via ON CONFLICT, no error

### Partial Failures

- Individual file errors don't stop ingestion
- All errors collected and reported in statistics
- Overall `success` flag indicates if all files processed without error

## Performance Considerations

### Archive Size

- `companyfacts.zip`: ~600 MB (when uncompressed: ~2.5 GB)
- `submissions.zip`: ~100 MB (when uncompressed: ~500 MB)

### Processing Time

- Single-threaded ingestion: 5-30 minutes depending on server capacity
- Memory usage: Streams files from ZIP, does not load entire archive
- Database commits: Batch commits per company file

### Optimization Tips

1. **Disable indexes temporarily**: For large bulk ingests, temporarily disable non-PK indexes
2. **Increase batch size**: Modify session batch parameters in `_upsert_filing_events`
3. **Run off-peak**: Execute bulk ingests during low-traffic periods
4. **Use PostgreSQL connection pooling**: Optimize database connection overhead

## Testing

### Fixture Files

Minimal test archives are available in `tests/fixtures/sec_bulk_archives/`:
- `companyfacts_test.zip`: Single company (Amazon) with minimal facts
- `submissions_test.zip`: Single company with 2 filing events (10-K, 10-Q)

### Test Coverage

- Missing archive handling
- Statistics collection and reporting
- Company creation and updates
- Filing event upserts
- Idempotent re-ingestion
- Date parsing with missing values
- CLI argument parsing

### Running Tests

```bash
# All bulk ingest tests
pytest tests/test_sec_bulk_ingest.py -v

# Specific test class
pytest tests/test_sec_bulk_ingest.py::TestBulkSubmissionsIngestion -v

# With coverage
pytest tests/test_sec_bulk_ingest.py --cov=app.services.sec.bulk_ingest
```

## Integration with Live SEC Fetches

The bulk ingest service complements, but does not replace, live SEC fetching:

1. **Use bulk ingest for baseline**: Initialize database with complete filing history
2. **Use live fetches for updates**: Schedule regular refresh jobs for incremental updates
3. **No conflicts**: Both methods use identical database schemas and upsert logic
4. **Audit trail**: Data provenance remains clear via `bulk_import` markers

## Future Enhancements

Potential improvements:

1. **Parallel file processing**: Process multiple ZIP files concurrently
2. **Incremental ingestion**: Track ingested archive versions to avoid re-processing
3. **Fact normalization**: Parse and normalize XBRL facts into financial metrics
4. **Validation layer**: Validate data consistency and detect anomalies
5. **Archive verification**: Checksum verification against SEC's published manifests

## References

- [SEC EDGAR Data Feeds](https://www.sec.gov/sec-sys-web/list.shtml)
- [SEC EDGAR Bulk Data](https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&bulk=yes)
- [Companyfacts Documentation](https://www.sec.gov/Archives/edgar/full-index.html)
- [Submissions Documentation](https://www.sec.gov/Archives/edgar/submissions-index.html)
