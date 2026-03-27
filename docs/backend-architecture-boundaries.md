# Backend Architecture Boundaries

## Goal
Keep the API composition layer thin, keep orchestration in backend services, and prevent product-facing response schemas from leaking back into service modules.

## Layering rules
1. `app/api/routers/`

- Routers register public endpoints only.
- Routers may import FastAPI or Starlette helpers plus response models from `app/api/schemas/`.
- Routers must not import `app/services/`, database sessions, model-engine helpers, or perform request-path orchestration directly.
- Route handlers remain on `app.main` as the compatibility surface for existing tests and monkeypatching.

2. `app/api/schemas/`

- Schemas define frontend-facing request and response shapes.
- These modules may compose other schema modules, but they should stay free of refresh orchestration or persistence logic.

3. `app/services/`

- Services own ingestion, normalization, persistence, analytics, and refresh orchestration.
- Services must not import `app/api/` modules or frontend-facing schemas.
- Services return domain objects, dataclasses, primitives, or backend DTOs that `app.main` serializes into API schemas.

4. `app.main`

- `app.main` is the compatibility boundary between service code and the public FastAPI surface.
- It wires router registration, handler helpers, schema serialization, and queue/SSE entrypoints without moving public routes.

## Refresh orchestration boundary
- `EdgarIngestionService.refresh_company` is a policy-driven orchestrator.
- Dataset-specific jobs live in explicit service methods such as `refresh_statements`, `refresh_prices`, `refresh_insiders`, `refresh_form144`, `refresh_institutional`, `refresh_beneficial_ownership`, `refresh_earnings`, `refresh_events`, and `refresh_capital_markets`.
- SSE progress and queue behavior continue to flow through `queue_company_refresh`, `run_refresh_job`, `JobReporter`, and `status_broker`.
- Optional dataset failures are isolated inside service orchestration so one dataset can fail without collapsing the full refresh result.

## Automated guard
- Standalone guard: `python scripts/check_architecture_boundaries.py`
- Pytest guard: `tests/test_architecture_boundaries.py`
- The guard currently enforces:
  - routers only import router-local dependencies and API schemas
  - services do not import `app.api` modules

## Change policy
- If a feature needs new orchestration, add it to a service module or a new service helper instead of a router.
- If a feature needs a new API payload, add it under `app/api/schemas/` and serialize it from `app.main`.
- If a boundary rule needs to change, update both the architecture doc and the automated guard in the same change.