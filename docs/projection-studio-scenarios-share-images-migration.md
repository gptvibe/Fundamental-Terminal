# Projection Studio Scenarios and Share Images Migration Plan

## Scope

This rollout adds durable Projection Studio scenarios and server-generated share images while preserving current charts behavior.

- Durable scenario persistence (public/private)
- Shareable studio scenario URLs
- Snapshot-backed social/share images for Growth Outlook and Projection Studio
- OG metadata for shared links

## Data Model Changes

Alembic revisions:

- 20260423_0037 adds company_charts_scenarios
- 20260423_0038 adds company_charts_share_snapshots

Tables:

- company_charts_scenarios
  - id, company_id, owner_key
  - name, visibility, source
  - schema_version, override_count, forecast_year, as_of
  - overrides JSONB, metrics JSONB
  - cloned_from_scenario_id
  - created_at, updated_at
- company_charts_share_snapshots
  - id, company_id, snapshot_hash
  - schema_version, mode, payload JSONB
  - created_at
  - unique key on company_id + snapshot_hash for dedupe

## API Contract Additions

Projection Studio scenarios:

- GET /api/companies/{ticker}/charts/scenarios
  - list visible scenarios for viewer
- POST /api/companies/{ticker}/charts/scenarios
  - create scenario
- GET /api/companies/{ticker}/charts/scenarios/{scenario_id}
  - fetch scenario by id
- POST /api/companies/{ticker}/charts/scenarios/{scenario_id}
  - update scenario
- POST /api/companies/{ticker}/charts/scenarios/{scenario_id}/clone
  - clone scenario

Share snapshots:

- POST /api/companies/{ticker}/charts/share-snapshots
  - create or dedupe snapshot
- GET /api/companies/{ticker}/charts/share-snapshots/{snapshot_id}
  - fetch snapshot record and payload

Viewer scoping:

- Device/user viewer identity is used to enforce private scenario access and editability.

## Frontend Behavior Changes

Charts page:

- Studio mode resolves when URL includes mode=studio or scenario=<id>.

Projection Studio:

- Keeps local save/compare UX.
- Syncs with backend scenarios when available.
- Adds actions: Save, Save As, Share Link, Duplicate.
- Loads URL scenario id and applies scenario overrides.
- Compare continues to work with saved scenarios.

Share actions:

- Adds Copy Image, Download PNG, Copy Link using snapshot records.
- Supports 1:1, 4:5, and 16:9 share-image layouts.

Share routes:

- /company/[ticker]/charts/share/[snapshotId]
- /company/[ticker]/charts/share/[snapshotId]/image?layout=square|portrait|landscape

## Snapshot Payload

Snapshot payload supports both modes and carries:

- ticker/company/title/as_of
- source/provenance/trust labels
- explicit actual_label and forecast_label
- embedded chart_spec for reproducible rendering
- mode-specific sections for outlook/studio metrics and chart data

## Backward Compatibility

- Existing /api/companies/{ticker}/charts and what-if flows remain available.
- Local scenario persistence remains functional if backend sync fails.
- Scenario and share routes are additive.

## Rollout Plan

1. Apply DB migrations.
2. Deploy backend routes/services/models.
3. Deploy frontend scenario sync and share actions.
4. Enable share links and image routes.
5. Monitor scenario create/update and share-image fetch error rates.

## Verification Checklist

Backend:

- scenario CRUD and clone endpoints return viewer-aware payloads
- private scenarios are access-controlled
- share snapshot create is idempotent by snapshot_hash

Frontend:

- Studio loads with scenario URL
- Save, Save As, Share Link, Duplicate actions work
- compare supports saved scenarios
- Copy Image, Download PNG, Copy Link work per layout
- OG metadata uses generated image URL

Testing:

- backend route and service tests for scenarios/share snapshots
- frontend tests for scenario UI/actions and share cards/routes
- snapshot tests for share-card rendering
