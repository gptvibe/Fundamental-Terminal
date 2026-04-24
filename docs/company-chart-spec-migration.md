# Company Chart-Spec Migration Plan

## Objective

Move company charts to a versioned chart-spec artifact so one canonical state can power:

- web rendering
- image export
- OG cards
- future embeds

This keeps chart behavior consistent across surfaces and reduces duplicated view assembly logic.

## Versioned Contract

Current schema:

- `schema_version`: `company_chart_spec_v1`
- `payload_version`: `company_charts_dashboard_v9`

Main sections:

- top-level build and provenance metadata
- `outlook` (Growth Outlook)
- `studio` (Projection Studio)
- explicit card order arrays (`primary_card_order`, `secondary_card_order`, `comparison_card_order`, `detail_card_order`)

## Architecture Direction

1. Data/model outputs remain backend-generated and persisted.
2. Presentation layers consume `chart_spec` as the preferred source.
3. Legacy dashboard fields remain additive for endpoint compatibility.
4. Share/image/OG routes serialize from the same chart-spec-derived snapshot payload.

## Rollout Phases

### Phase 1: Additive contract (completed)

- Backend `CompanyChartsDashboardResponse` includes optional `chart_spec`.
- Model validation auto-populates `chart_spec` when absent.
- Existing response shape remains intact.

### Phase 2: Renderer preference (in progress)

- Frontend renderers prefer `chart_spec` values for outlook/studio summaries, ordering, and methodology labels.
- Fallback path rebuilds chart-spec from legacy payload fields when `chart_spec` is missing or malformed.

### Phase 3: Cross-surface unification (completed for current share paths)

- Share snapshot builders include `chart_spec` in stored payloads.
- Image export route renders from share snapshot payload.
- Share page metadata/OG cards use the same snapshot payload.

### Phase 4: Embed-readiness (next)

- Introduce embed-specific viewer components consuming `chart_spec` only.
- Add schema-version negotiation policy for future `company_chart_spec_v2` adoption.

## Backward Compatibility Policy

- `/api/companies/{ticker}/charts` keeps legacy fields and now includes additive `chart_spec`.
- Frontend chart-spec utilities rebuild from legacy fields if `chart_spec` is missing or invalid.
- Legacy persisted snapshots with hash-like payload versions are treated as stale and recomputed.

## Serialization and Deserialization

Frontend:

- `serializeCompanyChartsSpec(...)` emits JSON string artifacts.
- `deserializeCompanyChartsSpec(...)` now validates minimum required structure and rejects malformed payloads.

Backend:

- `serialize_company_charts_spec(...)` uses pydantic JSON-safe dump.
- `deserialize_company_charts_spec(...)` validates incoming dictionaries into typed payloads.

## Test Coverage

Backend tests:

- `tests/test_company_charts_spec.py`
- `tests/test_company_charts_route.py`
- `tests/test_company_charts_share_snapshots.py`

Frontend tests:

- `frontend/lib/chart-spec.test.ts`
- `frontend/components/company/charts-dashboard.test.ts`
- `frontend/components/company/projection-studio.test.tsx`
- `frontend/lib/chart-share.test.ts`
- `frontend/lib/api.routes.test.ts`

Newly added checks include malformed chart-spec deserialization and malformed chart-spec fallback rebuilding.

## Operational Notes

- Keep `schema_version` and rendering adapters explicit and centralized.
- Treat additive fields as non-breaking; avoid removing legacy fields until all consumers are confirmed migrated.
- For future schema upgrades, support at least one prior schema in frontend deserializers during transition.
