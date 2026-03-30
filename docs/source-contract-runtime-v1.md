# Source Contract Runtime v1

## Purpose

The source policy is now enforced through a manifest-backed endpoint source contract.

This runtime layer does three things:

1. Defines a shared, typed contract for every user-visible endpoint.
2. Attaches that contract to the FastAPI route as OpenAPI metadata.
3. Fails runtime, startup, and CI when a user-visible endpoint violates the declared contract.

The goal is enforcement, not payload churn. Existing endpoint payloads stay unchanged unless a separate feature requires expansion.

## Files

- `app/api/source_contracts.py`
- `app/api/endpoint_source_contract_manifest.py`
- `tests/test_endpoint_source_contract_manifest.py`

## Contract Shape

Each user-visible endpoint resolves to a `SourceContract` with these fields:

- `allowed_source_ids`
- `fallback_permitted`
- `strict_official_behavior`
- `confidence_penalty_rules`
- `ui_disclosure_requirements`

The contract model validates that every declared `allowed_source_id` exists in the central source registry.

It also rejects contracts that declare commercial or manual fallback sources while `fallback_permitted=false`.

## Runtime Attachment

Routers no longer call `router.add_api_route(...)` directly for user-visible surfaces.

They call `add_user_visible_route(...)`, which:

1. Resolves the route's contract from `USER_VISIBLE_ENDPOINT_SOURCE_CONTRACTS`.
2. Serializes it into route-level OpenAPI metadata under `x-ft-source-contract-v1`.
3. Registers the route.

Internal/system routes use `add_internal_route(...)` instead and are excluded from source-contract coverage.

Current excluded routes:

- `GET /health`
- `GET /api/internal/cache-metrics`

Everything else under `/api/` that is user-visible is expected to carry a contract.

## Enforcement

Enforcement happens in two places.

### App startup

`register_routers(...)` calls `ensure_user_visible_routes_have_source_contracts(app)` after all routers are included.

Startup fails if any of these conditions are true:

- a user-visible route exists without a manifest entry
- a manifest entry exists for a route that is no longer registered
- a registered route is missing the manifest-backed `x-ft-source-contract-v1` metadata

### Response runtime

`add_user_visible_route(...)` wraps each registered endpoint with a source-contract payload validator.

At runtime, the wrapper inspects response payloads that expose `provenance` and `source_mix` and rejects them when:

- an undeclared source id appears in the payload
- fallback sources appear on a route whose contract does not permit fallback
- strict-official-mode payloads still expose commercial fallback sources on routes that declare `drop_commercial_fallback_inputs`

That keeps the manifest from becoming documentation-only drift.

### CI

`tests/test_endpoint_source_contract_manifest.py` verifies both:

- the manifest covers the exact set of registered user-visible routes
- each registered user-visible route publishes the expected serialized contract metadata

That makes missing contracts a deterministic test failure in CI.

## Contract Semantics

### `allowed_source_ids`

This is the explicit allowlist for source ids that may back the endpoint.

The list can include:

- official/public upstream ids such as `sec_edgar`, `sec_companyfacts`, `us_treasury_daily_par_yield_curve`
- approved official fallback ids such as `us_treasury_fiscaldata`
- internal derived ids such as `ft_model_engine`, `ft_peer_comparison`, `ft_activity_overview`
- labeled commercial fallback ids such as `yahoo_finance` where the product policy allows them

### `fallback_permitted`

This signals whether the endpoint contract allows fallback behavior at all.

That includes two different cases:

- approved official fallback paths
- labeled commercial fallback paths

It does not imply that the fallback is always active. It only means the endpoint is allowed to use one.

### `strict_official_behavior`

`strict_official_behavior` is one of:

- `not_applicable`
- `official_only`
- `drop_commercial_fallback_inputs`

`drop_commercial_fallback_inputs` is the important product-control setting for price-sensitive surfaces. In strict official mode, those surfaces must suppress Yahoo-backed data and tell the UI why sections are missing.

### `confidence_penalty_rules`

These are route-level policy rules that explain which conditions should lower user trust in the payload.

Examples:

- persisted inputs are stale or missing
- analytics are derived from upstream official inputs and inherit upstream quality flags
- a commercial fallback contributed to the response
- strict official mode removed fallback-backed sections

### `ui_disclosure_requirements`

These are route-level disclosure requirements the frontend can rely on when deciding what to badge, banner, or explain.

Examples:

- official/public-only note
- derived analytics note
- commercial fallback badge
- strict official mode banner
- synthetic fixture banner for regression-only model evaluation runs

## Adding a New User-Visible Endpoint

When adding a new user-visible route:

1. Add its contract to `USER_VISIBLE_ENDPOINT_SOURCE_CONTRACTS`.
2. Register the route through `add_user_visible_route(...)`.
3. Keep the handler in `app.main` if the route is part of the compatibility boundary.
4. Update or add tests only if the public route inventory changes.

If you skip step 1 or step 2, startup and CI will fail.

## Non-goals

- This manifest does not replace response-level provenance payloads.
- This manifest does not broaden the product beyond the current SEC-first workflow.
- This manifest does not authorize live request-path fetches where the product already prefers persisted slices.

It is a runtime guardrail that turns the documented source policy into an enforceable backend contract.