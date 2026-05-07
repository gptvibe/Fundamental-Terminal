# Agent Instructions

## Product and trust policy
- Fundamental Terminal is an official-source-first research workspace for U.S. public equities.
- The product is not a real-time trading cockpit, news firehose, generic market terminal, or investment-advice product.
- Preserve the SEC-first/public-data-first trust model for fundamentals, filings, ownership, governance, capital markets, and analytics derived from official data.
- Do not add unofficial scraped fundamentals feeds, paid/auth-gated vendor fundamentals APIs, or third-party fundamentals providers that hide SEC provenance.
- Yahoo Finance is allowed only as a clearly labeled fallback for price, volume, and market-profile context.
- When `STRICT_OFFICIAL_MODE=true`, suppress fallback-backed price or market-profile surfaces entirely; do not expose Yahoo-backed payloads or UI in that mode.
- Keep fallback disclosures explicit in API and UI surfaces whenever fallback inputs are present.
- Do not use investment advice, recommendation, or portfolio-management language.

## Research surface expectations
- `/company/[ticker]` is the default Research Brief, not a generic overview; preserve the six-section flow: snapshot, what changed, business quality, capital/risk, valuation, and monitor.
- Keep existing specialist routes intact and reachable. Route URLs stay stable unless the change explicitly includes an alias, redirect, or documented contract update.
- Build company research surfaces from persisted or cache-first endpoints whenever possible. Do not add request-path live fetches for core brief sections or related summary endpoints.
- New data surfaces need provenance before product exposure: use canonical source ids, keep official data dominant, and expose `provenance[]`, `source_mix`, freshness, and confidence cues where the contract calls for them.

## Architecture expectations
- Keep routers thin. Public route registration and frontend-facing schemas belong in `app/api/routers/` and `app/api/schemas/`.
- Keep orchestration, ingestion, normalization, persistence, analytics, and refresh policy in `app/services/`.
- Preserve `app.main` as the compatibility boundary for public API contracts and handler serialization.
- Services must not import `app/api/`; routers must not import services, database sessions, or model-engine helpers.
- If architecture boundaries change, update `docs/backend-architecture-boundaries.md` and `scripts/check_architecture_boundaries.py` together.

## Backend commands
- Setup:
  `pip install -r requirements-dev.txt`
  `docker compose up -d postgres redis`
  `alembic upgrade head`
- Lint:
  `python -m ruff check app/main.py app/api/routers app/api/schemas app/services scripts/check_architecture_boundaries.py --select F401,F821,F822,F823,E9`
- Tests:
  `python -m pytest`
- Migrations:
  `alembic upgrade head`
  `python scripts/check_migration_safety.py`
- Architecture guard:
  `python scripts/check_architecture_boundaries.py`
- Local run:
  `uvicorn app.main:app --reload`
  Set `DATABASE_URL`, `REDIS_URL`, `SEC_USER_AGENT`, and `MARKET_USER_AGENT` first.

## Frontend commands
- Install:
  `npm --prefix frontend install`
- Typecheck:
  `npm --prefix frontend run typecheck`
- Test:
  `npm --prefix frontend run test`
- Lint:
  `npm --prefix frontend run lint`
- Build:
  `npm --prefix frontend run build`
- E2E:
  `npm --prefix frontend run test:e2e`
- Performance audit:
  `npm --prefix frontend run audit:performance -- --ticker AAPL`
  Enable `PERFORMANCE_AUDIT_ENABLED=true` on the backend and `NEXT_PUBLIC_PERFORMANCE_AUDIT_ENABLED=true` on the frontend for local audits.

## Definition of done
- Backend API changes:
  Keep routers thin, keep orchestration in services, preserve route contracts, add or update deterministic tests, and run the architecture boundary guard when boundaries are touched.
- Frontend UI changes:
  Keep provenance/freshness/fallback disclosures intact, preserve stable route behavior, cover important state changes with tests, and finish with lint, typecheck, and production build passing.
- New dataset surfaces:
  Document provenance first, use canonical source ids, ship the full vertical slice from ingestion through persistence/API/UI/tests/docs, and keep official data dominant.
- AI features:
  Keep outputs grounded in persisted or documented inputs, avoid advice language, disclose fallback or derived status clearly, and do not bypass source-policy constraints.
- Performance changes:
  Prefer reducing request fan-out and payload weight on persisted reads, avoid adding live-fetch coupling, and verify with the local performance audit or benchmark tooling when relevant.
- Release changes:
  Keep frontend/backend compatibility intact, preserve matching Docker image tags, run or maintain deployment compatibility smoke checks, and update release docs or checks when the release flow changes.

## Release tagging policy
- When asked to tag releases, auto-increment the patch version by +0.0.1 from the latest `vX.Y.Z` tag unless explicitly instructed otherwise.
- Keep Git tags and Docker image tags aligned to the same version (e.g., `v1.0.3`, `backend-v1.0.3`, `frontend-v1.0.3`).
