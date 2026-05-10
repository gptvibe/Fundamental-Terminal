# Watchlist Alerts Feature Implementation

## Overview
Added a non-AI alert system for watchlist companies that detects and tracks various SEC filing events and conditions. Alerts are deterministic, source-linked, and prevent duplicate notifications through deduplication logic.

## Architecture

### Backend Components

#### 1. Database Model
- **File**: `app/models/watchlist_alert.py`
- **Purpose**: WatchlistAlert model stores alert state with deduplication keys
- **Fields**:
  - `id`: Primary key
  - `company_id`: Foreign key to Company (with CASCADE delete)
  - `alert_type`: Classification (10-K, 10-Q, 8-K, proxy, form-4, amendment, late-filing, stale-data)
  - `source_filing_accession`: Links to specific filing (nullable)
  - `source_filing_form`: Form type of source filing
  - `created_at`: Timestamp of alert creation
  - `dismissed_at`: When user dismissed the alert

#### 2. Migration
- **File**: `alembic/versions/20260510_0048_add_watchlist_alerts.py`
- **Purpose**: Creates watchlist_alerts table with proper indexes and constraints
- **Constraints**:
  - Unique constraint on (company_id, alert_type, source_filing_accession) for deduplication
  - Foreign key constraint with CASCADE delete on company_id
  - Indexes on company_id, company_id+created_at, company_id+alert_type for query performance

#### 3. Alert Detection Service
- **File**: `app/services/watchlist_alerts.py`
- **Functions**:
  - `detect_and_create_alerts(session, company_id)`: Main alert detection logic
    - Detects recent filings (10-K, 10-Q, 8-K, proxy, Form 4)
    - Detects amended filings (10-K/A, 10-Q/A, 8-K/A, etc.)
    - Detects late filing notices (NT 10-K, NT 10-Q, etc.)
    - Detects stale source data (30+ days without refresh)
    - Returns only newly created alerts (existing ones skipped via deduplication)
  - `dismiss_alert(session, alert_id)`: Marks alert as dismissed
  - `get_active_alerts(session, company_id, alert_types)`: Retrieves active alerts with optional type filtering
  - Helper functions for querying different filing types

#### 4. API Schemas
- **File**: `app/api/schemas/workspace.py` (additions)
- **New Types**:
  - `WatchlistAlertPayload`: Individual alert with all details
  - `WatchlistAlertsResponse`: Response containing alerts list and summary counts

#### 5. Handler
- **File**: `app/api/handlers/workspace.py` (addition)
- **Function**: `watchlist_alerts(payload, alert_types, session)`
  - Accepts watchlist summary request with tickers
  - Supports optional alert type filtering via query parameter
  - Orchestrates alert detection and retrieval
  - Returns alerts sorted by creation date (newest first)
  - Includes telemetry logging

#### 6. Router
- **File**: `app/api/routers/workspace.py` (modification)
- **Route**: `POST /api/watchlist/alerts`
- **Response**: WatchlistAlertsResponse with alerts for specified tickers

#### 7. Backend Tests
- **File**: `tests/test_watchlist_alerts.py`
- **Test Coverage**:
  - `test_detect_new_10k_alert`: Verifies 10-K detection
  - `test_alert_deduplication`: Ensures duplicate alerts aren't created
  - `test_dismiss_alert`: Validates dismissal functionality
  - `test_alert_filtering_by_type`: Tests type filtering
  - `test_detect_amended_filing`: Validates amended filing detection
  - `test_watchlist_alerts_endpoint`: Endpoint integration test (skipped - requires full setup)

### Frontend Components

#### 1. TypeScript Types
- **File**: `frontend/lib/types.ts` (additions)
- **New Types**:
  - `WatchlistAlertPayload`: Single alert interface
  - `WatchlistAlertsResponse`: API response interface

#### 2. API Client
- **File**: `frontend/lib/api/watchlist.ts` (addition)
- **Function**: `getWatchlistAlerts(tickers, alertTypes)`
  - Makes POST request to `/watchlist/alerts`
  - Accepts optional alert type filters as query parameters
  - Returns typed WatchlistAlertsResponse

#### 3. UI Component
- **File**: `frontend/components/watchlist/watchlist-alerts-list.tsx`
- **Features**:
  - Display alerts with emoji icons for visual distinction
  - Alert type filtering with click-to-toggle buttons
  - Sorting options: Most Recent, Oldest First, By Importance, By Ticker
  - Show Mode: Unread or All alerts
  - Color-coded alert types based on importance
  - Empty state handling
  - Loading skeleton display
  - Error state handling
  - Summary footer with alert count
  - Responsive layout

#### 4. Badge Component
- **Function**: `WatchlistAlertsBadge(count)`
- **Purpose**: Shows notification badge with alert count
- **Behavior**: Shows "9+" for counts > 9

#### 5. Frontend Tests
- **File**: `frontend/components/watchlist/watchlist-alerts-list.test.tsx`
- **Test Coverage**:
  - Component rendering
  - Alert type filtering (toggle on/off)
  - Sort order changes
  - Unread/All mode switching
  - API integration
  - Error handling
  - Loading states
  - Badge display

### Supporting Changes

#### 1. Company Model Update
- **File**: `app/models/company.py`
- **Changes**: Added `watchlist_alerts` relationship for reverse navigation

#### 2. Shared Handler Imports
- **File**: `app/api/handlers/_shared.py`
- **Changes**:
  - Added Company to model imports
  - Added WatchlistAlertPayload and WatchlistAlertsResponse to schema imports

## Alert Types and Semantics

### Alert Classifications
1. **10-K**: Annual report filed (priority: 1)
2. **10-Q**: Quarterly report filed (priority: 1)
3. **8-K**: Current report for material events (priority: 4)
4. **proxy**: Proxy statement filed (priority: 1)
5. **form-4**: Insider transaction filed (priority: 2)
6. **amendment**: Previously filed document amended (priority: 3)
7. **late-filing**: Late filing notice (NT forms) (priority: 5)
8. **stale-data**: Source data hasn't been refreshed (priority: 0)

### Deduplication Strategy
- Unique constraint on (company_id, alert_type, source_filing_accession)
- Prevents duplicate alerts for the same event
- Only newly created alerts returned by detection function
- Dismissed alerts excluded from active alerts query

### Freshness Thresholds
- Filing data considered stale after 30 days without refresh
- Insider data considered stale after 30 days
- Proxy data considered stale after 60 days

## Trust Model
- All alerts source-linked to official SEC filings
- Deduplication prevents alert fatigue
- No recommendation or advice language
- Deterministic detection based on observable filing events
- Users can dismiss alerts without affecting system

## API Constraints
- Maximum 50 tickers per request
- Returns 422 Unprocessable Content if limit exceeded
- Query parameters for alert type filtering
- POST method for potential future batch dismissal support

## Testing Strategy

### Backend Tests
- Unit tests for alert detection logic
- Deduplication validation
- Filtering by type
- Dismissal functionality
- Amendment detection

### Frontend Tests
- Component rendering
- User interactions (filtering, sorting)
- API integration mocking
- Error and loading states
- Badge logic

## Architecture Compliance
✓ Routers are thin (just route registration)
✓ Services contain orchestration logic (watchlist_alerts.py)
✓ Models in app/models/
✓ Schemas in app/api/schemas/
✓ Handlers use _shared imports
✓ Services don't import app/api/
✓ Routers don't import services directly
✓ Frontend components use API client
✓ Proper separation of concerns maintained

## Future Enhancement Opportunities
1. Batch dismissal of alerts
2. User-configurable alert preferences
3. Email/webhook notifications for critical alerts
4. Alert history and archival
5. Related news/context integration
6. Machine learning for anomaly detection (while maintaining source linkage)
7. Alert reasoning/explainability endpoints
