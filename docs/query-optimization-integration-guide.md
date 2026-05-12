# Query Optimization Integration Guide

## Summary of Changes

This guide provides practical examples for integrating the optimized query functions into the codebase.

## Quick Reference: Before & After

### 1. Price History Filtering

#### Before (Python filtering)
```python
from app.services.cache_queries import get_company_price_history, filter_price_history_as_of

def get_price_for_report(session: Session, company_id: int, as_of: datetime) -> float | None:
    # Problem: Fetches potentially thousands of price points
    price_history = get_company_price_history(session, company_id)
    
    # Problem: Filters in Python
    filtered = filter_price_history_as_of(price_history, as_of)
    
    # Problem: Slices in Python
    latest = filtered[-1] if filtered else None
    return latest.close if latest else None
```

#### After (SQL filtering)
```python
from app.services.cache_queries import get_latest_price_as_of

def get_price_for_report(session: Session, company_id: int, as_of: datetime) -> float | None:
    # Solution: Fetches only one row from database
    latest = get_latest_price_as_of(session, company_id, as_of)
    return latest.close if latest else None
```

**Benefits:**
- Network: Reduces data transfer from 100-2000 rows to 1 row
- Memory: Eliminates need to hold full history in memory
- CPU: Delegates filtering to database query optimizer

---

### 2. Financial Statement Point-in-Time Selection

#### Before (Python point-in-time selection)
```python
from app.services.cache_queries import get_company_financials, select_point_in_time_financials

def get_latest_financial_snapshot(
    session: Session, 
    company_id: int, 
    as_of: datetime
) -> dict[str, FinancialStatement] | None:
    # Problem: Fetches potentially 100+ statements per company
    all_financials = get_company_financials(session, company_id)
    
    # Problem: Complex Python logic to select best statement per (period_end, filing_type)
    pit_financials = select_point_in_time_financials(all_financials, as_of)
    
    # Problem: Still need to restructure the results
    result = {}
    for stmt in pit_financials[:8]:  # Only use first 8 anyway
        result[stmt.period_end.isoformat()] = stmt
    
    return result if result else None
```

#### After (SQL point-in-time selection)
```python
from app.services.cache_queries import get_point_in_time_financials

def get_latest_financial_snapshot(
    session: Session, 
    company_id: int, 
    as_of: datetime
) -> dict[str, FinancialStatement] | None:
    # Solution: Fetches only the selected statements from database
    pit_financials = get_point_in_time_financials(
        session,
        company_id,
        "canonical",  # statement_type
        as_of,
        limit=8  # Get only what we need
    )
    
    # Solution: Window function ensures we already have the best statement per period
    result = {}
    for stmt in pit_financials:
        result[stmt.period_end.isoformat()] = stmt
    
    return result if result else None
```

**Benefits:**
- Network: Reduces data transfer by 80-90% (8 statements instead of 100+)
- Processing: Eliminates Python-side complex selection logic
- Clarity: Window function explicitly expresses intent

---

### 3. Activity Feed Building (Already Optimized)

#### Current Implementation (Optimal)
```python
from app.services.cache_queries import (
    get_company_filing_events,
    get_company_insider_trades,
    get_company_institutional_holdings,
)

def build_activity_feed(session: Session, company_id: int) -> list[ActivityFeedEntry]:
    # These queries already LIMIT at the database level
    filings = get_company_filing_events(session, company_id, limit=300)
    trades = get_company_insider_trades(session, company_id, limit=200)
    holdings = get_company_institutional_holdings(session, company_id, limit=200)
    
    entries = []
    
    # Slicing here is minimal overhead since we already LIMITED at DB
    for filing in filings[:40]:
        entries.append(ActivityFeedEntry(
            type="filing",
            date=filing.filing_date,
            # ...
        ))
    
    for trade in trades[:40]:
        entries.append(ActivityFeedEntry(
            type="insider",
            date=trade.filing_date,
            # ...
        ))
    
    # No changes needed - already optimal!
    return entries
```

**Status:** ✅ No optimization needed - already uses SQL LIMIT clauses

---

## Migration Checklist for Each Service

### app/services/company_research_brief.py

**Priority:** HIGH - This is a major caller

**Steps:**

1. **Update imports:**
   ```python
   # Remove old imports if transitioning completely
   # from app.services.cache_queries import filter_price_history_as_of, latest_price_as_of
   
   # Add new imports
   from app.services.cache_queries import (
       get_price_history_as_of,
       get_latest_price_as_of,
       get_point_in_time_financials,
   )
   ```

2. **Find/Replace Pattern 1 - Price history filtering:**
   ```python
   # OLD
   price_history = get_company_price_history(session, company_id)
   if as_of is not None:
       price_history = filter_price_history_as_of(price_history, as_of)
   price_last_checked, _price_cache_state = get_company_price_cache_status(session, company_id)
   latest_price = price_history[-1] if price_history else None
   
   # NEW
   latest_price = get_latest_price_as_of(session, company_id, as_of) if as_of else None
   price_last_checked, _price_cache_state = get_company_price_cache_status(session, company_id)
   ```

3. **Financial statements point-in-time:**
   ```python
   # OLD
   all_financials = get_company_financials(session, company_id)
   pit_financials = select_point_in_time_financials(all_financials, as_of)
   
   # NEW
   pit_financials = get_point_in_time_financials(
       session, company_id, "canonical", as_of, limit=20
   )
   ```

### app/services/model_evaluation.py

**Priority:** HIGH - Used in backtesting

**Pattern to update:**
```python
# OLD
current_price_row = latest_price_as_of(list(bundle.prices), as_of)

# NEW
current_price_row = get_latest_price_as_of(session, company_id, as_of)
```

### app/services/peer_comparison.py

**Priority:** MEDIUM

**Pattern:**
```python
# OLD
latest_price = latest_price_as_of(price_history, as_of)

# NEW
latest_price = get_latest_price_as_of(session, company_id, as_of)
```

### app/api/handlers/_shared.py

**Priority:** MEDIUM - API layer

**Pattern:**
```python
# OLD
price_history = get_company_price_history(session, company_id)
if as_of:
    filtered_price_history = filter_price_history_as_of(price_history, parsed_as_of)
latest = filtered_price_history[-1] if filtered_price_history else None

# NEW
latest = get_latest_price_as_of(session, company_id, parsed_as_of)
```

## Testing Your Changes

### Run All Optimization Tests
```bash
python -m pytest tests/test_query_optimization.py -v
```

### Run With Coverage
```bash
python -m pytest tests/test_query_optimization.py --cov=app.services.cache_queries
```

### Specific Test Classes
```bash
# Price history tests
python -m pytest tests/test_query_optimization.py::TestPriceHistoryOptimization -v

# Financial statement tests
python -m pytest tests/test_query_optimization.py::TestFinancialStatementOptimization -v

# Integration/performance tests
python -m pytest tests/test_query_optimization.py::TestQueryPerformance -v
```

## Verification Steps

### 1. Apply Migration
```bash
cd /path/to/Fundamental-Terminal
alembic upgrade head
```

Verify the indexes were created:
```sql
-- Connect to your database
psql -U postgres -d fundamental

-- Check price_history indexes
\d price_history

-- Verify the DESC index exists
SELECT * FROM pg_indexes WHERE tablename = 'price_history' AND indexname LIKE '%desc%';
```

### 2. Run Existing Tests
Ensure no regressions:
```bash
python -m pytest tests/ -x  # Stop on first failure
```

### 3. Performance Benchmarking

#### Before Optimization
```python
import time
from app.services.cache_queries import (
    get_company_price_history,
    filter_price_history_as_of
)

start = time.time()
for _ in range(100):
    prices = get_company_price_history(session, company_id)
    filtered = filter_price_history_as_of(prices, as_of)
    latest = filtered[-1] if filtered else None
elapsed_python = time.time() - start
print(f"Python filtering: {elapsed_python:.3f}s for 100 iterations")
```

#### After Optimization
```python
import time
from app.services.cache_queries import get_latest_price_as_of

start = time.time()
for _ in range(100):
    latest = get_latest_price_as_of(session, company_id, as_of)
elapsed_sql = time.time() - start
print(f"SQL filtering: {elapsed_sql:.3f}s for 100 iterations")

improvement = (elapsed_python - elapsed_sql) / elapsed_python * 100
print(f"Improvement: {improvement:.1f}%")
```

## Deployment Guide

### Pre-Deployment Checklist

- [ ] All tests pass: `python -m pytest tests/test_query_optimization.py`
- [ ] No regressions: `python -m pytest`
- [ ] Linting passes: `python -m ruff check app/services/cache_queries.py`
- [ ] Code review completed
- [ ] Performance metrics collected
- [ ] Database backup created
- [ ] Rollback plan documented

### Deployment Steps

1. **Database First (Low Risk)**
   ```bash
   # Apply migration in staging first
   alembic upgrade head
   # Indexes are added, old code still works
   ```

2. **Gradual Code Rollout**
   - Update one service at a time
   - Monitor logs for errors
   - Collect performance metrics
   - Roll back individual changes if needed

3. **Production Deployment**
   ```bash
   # 1. Apply database migration
   alembic upgrade head
   
   # 2. Update application code
   git merge feature/query-optimization
   
   # 3. Deploy application
   docker-compose up -d
   
   # 4. Monitor
   tail -f logs/application.log
   ```

### Rollback Plan

If issues occur:

1. **Code Rollback (Immediate)**
   ```bash
   git revert <commit-hash>
   docker-compose restart backend
   ```

2. **Database Rollback (Only if needed)**
   ```bash
   alembic downgrade <previous_version>
   ```
   The old Python functions will still work without new indexes (slightly slower but functional).

## FAQ

### Q: Do I need to update all callers immediately?

**A:** No. The old Python-based functions remain available. You can migrate services gradually. However, for best performance, prioritize:
1. `company_research_brief.py` (high traffic)
2. `model_evaluation.py` (high volume)
3. API handlers
4. Remaining services

### Q: Will my API responses change?

**A:** No. The new functions return the same object types and structure. The only difference is they come from the database via a more efficient query.

### Q: Can I use both old and new functions together?

**A:** Yes, you can have a mix. However, be careful not to mix cached data - i.e., don't filter cached data with new SQL functions or vice versa.

### Q: What if a query is still slow after optimization?

**A:** Check:
1. Is the index being used? (EXPLAIN ANALYZE in psql)
2. Are there table locks?
3. Is the result set still large?

### Q: How do I know if the index is being used?

**A:** In PostgreSQL:
```sql
EXPLAIN ANALYZE
SELECT * FROM price_history 
WHERE company_id = 1 
AND trade_date <= '2026-02-15'
ORDER BY trade_date DESC LIMIT 1;
```

Look for "Index Scan" instead of "Sequential Scan".

## Support

For issues or questions:
1. Check this document
2. Review test cases in `tests/test_query_optimization.py`
3. Check the detailed documentation: `docs/query-optimization-audit.md`
4. Review the migration file: `alembic/versions/20260512_0049_add_desc_ordering_indexes.py`
